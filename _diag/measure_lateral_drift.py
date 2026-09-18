# -*- coding: utf-8 -*-
"""measure_lateral_drift.py — 量测输出带序列的横向（宽度轴）漂移。

gray_tar/k.tif 是本次 2 米跑的输出带，每条 834(行数=行进) x 21259(列数=幅宽)。
"朝右偏" = 内容沿列方向平移。做法：
  1. 每带取列剖面（沿行求均值）-> 长度 21259 的一维信号
  2. 与第 0 带的剖面做互相关，抛物线插值取亚像素峰值 -> 该带相对第 0 带的横向位移
  3. 同时算相邻带之间的增量位移
  4. 对位移-带号做线性拟合 -> px/带，换算成 mm
"""
import os
import sys
import re

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', 'gray_tar')
PX_PER_MM = 300 / 25.4          # 11.811 px/mm


def natural_key(p):
    return int(re.search(r'(\d+)', os.path.basename(p)).group(1))


def col_profile(path, r0=200, r1=634):
    img = np.asarray(Image.open(path))
    if img.ndim == 3:
        img = img.mean(axis=2)
    band = img[r0:r1, :].astype(np.float64)
    prof = band.mean(axis=0)
    prof -= prof.mean()
    return prof


def xcorr_shift(a, b, max_shift=200):
    """返回 b 相对 a 的位移 d（b(x) ~= a(x - d)），以及峰值归一化相关系数。"""
    n = len(a)
    A = np.fft.rfft(a, 2 * n)
    B = np.fft.rfft(b, 2 * n)
    cc = np.fft.irfft(B * np.conj(A), 2 * n)
    cc = np.concatenate([cc[-max_shift:], cc[:max_shift + 1]])
    lags = np.arange(-max_shift, max_shift + 1)
    k = int(np.argmax(np.abs(cc)))
    peak = cc[k]
    # 抛物线亚像素插值
    d = lags[k]
    if 0 < k < len(cc) - 1:
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]
        denom = (y0 - 2 * y1 + y2)
        if denom != 0:
            delta = 0.5 * (y0 - y2) / denom
            d = lags[k] + delta
    norm = np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9
    return float(d), float(abs(peak) / norm)


def main():
    files = sorted(
        [os.path.join(DATA, f) for f in os.listdir(DATA) if f.lower().endswith('.tif')],
        key=natural_key)
    print(f'共 {len(files)} 条带')
    shape = np.asarray(Image.open(files[0])).shape
    print(f'单带尺寸: {shape}  (行=行进 {shape[0]}, 列=幅宽 {shape[1]})')

    profs = []
    for p in files:
        profs.append(col_profile(p))
    print('剖面计算完成\n')

    ref = profs[0]
    print(f'{"带":>4} {"相对第0带位移(px)":>18} {"mm":>8} {"相关度":>8} {"相邻增量(px)":>14}')
    shifts, corrs = [], []
    for k, pr in enumerate(profs):
        d, c = xcorr_shift(ref, pr)
        shifts.append(d)
        corrs.append(c)
        inc = d - shifts[k - 1] if k > 0 else 0.0
        print(f'{k:>4} {d:>18.2f} {d / PX_PER_MM:>8.3f} {c:>8.3f} {inc:>14.2f}')

    shifts = np.array(shifts)
    corrs = np.array(corrs)
    k = np.arange(len(shifts))
    # 线性拟合（剔除相关度过低、不可信的点）
    ok = corrs > 0.5
    print(f'\n可信点数(相关度>0.5): {ok.sum()} / {len(ok)}')
    if ok.sum() >= 3:
        A = np.vstack([k[ok], np.ones(ok.sum())]).T
        slope, inter = np.linalg.lstsq(A, shifts[ok], rcond=None)[0]
        pred = slope * k[ok] + inter
        ss_res = ((shifts[ok] - pred) ** 2).sum()
        ss_tot = ((shifts[ok] - shifts[ok].mean()) ** 2).sum()
        r2 = 1 - ss_res / (ss_tot + 1e-9)
        print(f'线性拟合: 位移 = {slope:+.4f} px/带  x  +  {inter:+.2f} px   (R²={r2:.3f})')
        print(f'  => 每带漂移 {slope / PX_PER_MM:+.4f} mm')
        print(f'  => 全程 {len(shifts)} 带累积 {shifts[-1]:+.2f} px = {shifts[-1] / PX_PER_MM:+.3f} mm')
        print(f'  => 按拟合斜率推算 2 m(约27带): {slope * len(shifts) / PX_PER_MM:+.3f} mm')

    incs = np.diff(shifts)
    print(f'\n相邻带增量: mean {incs.mean():+.3f} px  std {incs.std():.3f}  '
          f'min {incs.min():+.2f}  max {incs.max():+.2f}')
    print(f'  => 每带平均 {incs.mean() / PX_PER_MM:+.4f} mm')


if __name__ == '__main__':
    main()
