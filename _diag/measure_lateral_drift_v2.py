# -*- coding: utf-8 -*-
"""measure_lateral_drift_v2.py — 交叉验证横向漂移（单行剖面 + 多个行位置）。

v1 用 434 行的均值剖面，可能被行进方向的亮度变化污染。v2 改成：
  - 取单行（3 个位置：上/中/下）分别测
  - 三个位置结果一致才说明是真横向漂移
  - 同时给出相邻带的接缝错位（累积漂移的微分）
"""
import os
import sys
import re

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', 'gray_tar')
PX_PER_MM = 300 / 25.4
ROWS = [120, 417, 714]          # 上 / 中 / 下


def natural_key(p):
    return int(re.search(r'(\d+)', os.path.basename(p)).group(1))


def row_profile(img, r):
    p = img[r, :].astype(np.float64)
    p = p - p.mean()
    return p


def xcorr_shift(a, b, max_shift=300):
    n = len(a)
    A = np.fft.rfft(a, 2 * n)
    B = np.fft.rfft(b, 2 * n)
    cc = np.fft.irfft(B * np.conj(A), 2 * n)
    cc = np.concatenate([cc[-max_shift:], cc[:max_shift + 1]])
    lags = np.arange(-max_shift, max_shift + 1)
    k = int(np.argmax(cc))
    d = float(lags[k])
    if 0 < k < len(cc) - 1:
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            d += 0.5 * (y0 - y2) / den
    norm = np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9
    return d, float(cc[k] / norm)


def main():
    files = sorted(
        [os.path.join(DATA, f) for f in os.listdir(DATA) if f.lower().endswith('.tif')],
        key=natural_key)
    print(f'共 {len(files)} 条带\n')

    # 逐带读一次，同时取三个行剖面，避免重复 IO
    profs = {r: [] for r in ROWS}
    for p in files:
        img = np.asarray(Image.open(p))
        if img.ndim == 3:
            img = img.mean(axis=2)
        for r in ROWS:
            profs[r].append(row_profile(img, r))
        del img

    for r in ROWS:
        P = profs[r]
        ref = P[0]
        shifts, corrs = [], []
        for k, pr in enumerate(P):
            d, c = xcorr_shift(ref, pr)
            shifts.append(d)
            corrs.append(c)
        shifts = np.array(shifts)
        corrs = np.array(corrs)
        ok = corrs > 0.5
        kk = np.arange(len(shifts))
        line = ''
        if ok.sum() >= 3:
            A = np.vstack([kk[ok], np.ones(ok.sum())]).T
            slope, inter = np.linalg.lstsq(A, shifts[ok], rcond=None)[0]
            line = (f'斜率 {slope:+.3f} px/带 = {slope / PX_PER_MM:+.4f} mm/带；'
                    f'可信带 {ok.sum()}/{len(ok)}；末带累积 {shifts[ok][-1]:+.1f} px'
                    f' = {shifts[ok][-1] / PX_PER_MM:+.2f} mm')
        print(f'--- 第 {r} 行剖面 ---')
        print('  位移:', ' '.join(f'{s:+.1f}' for s in shifts[:12]))
        print('       ', ' '.join(f'{s:+.1f}' for s in shifts[12:]))
        print('  相关:', ' '.join(f'{c:.2f}' for c in corrs[:12]))
        print('       ', ' '.join(f'{c:.2f}' for c in corrs[12:]))
        print(f'  {line}\n')


if __name__ == '__main__':
    main()
