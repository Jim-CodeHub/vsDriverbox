# -*- coding: utf-8 -*-
"""analyze_drift_decompose.py — 把横向位移分解成"线性剪切"+"残差"。

线性剪切很可能就是布面真实的歪斜（扫描忠实记录，属正确行为）；
残差（偏离直线的部分）才是引擎的摆放误差。
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
ROW = 417


def natural_key(p):
    return int(re.search(r'(\d+)', os.path.basename(p)).group(1))


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
    profs = []
    for p in files:
        img = np.asarray(Image.open(p))
        if img.ndim == 3:
            img = img.mean(axis=2)
        pr = img[ROW, :].astype(np.float64)
        profs.append(pr - pr.mean())
        del img

    ref = profs[0]
    shifts, corrs = [], []
    for pr in profs:
        d, c = xcorr_shift(ref, pr)
        shifts.append(d)
        corrs.append(c)
    shifts = np.array(shifts)
    corrs = np.array(corrs)
    ok = corrs > 0.5
    idx = np.where(ok)[0]
    print(f'可用带: {idx.min()}..{idx.max()}  共 {len(idx)} 条（相关度>0.5）')

    x = idx.astype(float)
    y = shifts[ok]
    A = np.vstack([x, np.ones(len(x))]).T
    slope, inter = np.linalg.lstsq(A, y, rcond=None)[0]
    fit = slope * x + inter
    res = y - fit

    print(f'\n=== 线性剪切部分 ===')
    print(f'  斜率 = {slope:+.3f} px/带 = {slope / PX_PER_MM:+.4f} mm/带')
    ang = np.degrees(np.arctan(slope / 834.0))
    print(f'  剪切角 = {ang:+.4f}°   （每带行进 834 px 对应横移 {slope:.2f} px）')
    print(f'  外推 2 m(27 带) = {slope * 27 / PX_PER_MM:+.2f} mm')

    print(f'\n=== 残差（引擎摆放误差）===')
    print(f'  std = {res.std():.2f} px = {res.std() / PX_PER_MM:.3f} mm')
    print(f'  max |残差| = {np.abs(res).max():.2f} px = {np.abs(res).max() / PX_PER_MM:.3f} mm')
    print(f'  逐带残差(px): ' + ' '.join(f'{v:+.1f}' for v in res))

    inc = np.diff(y)
    print(f'\n=== 相邻带接缝错位 ===')
    print(f'  mean {inc.mean():+.2f} px = {inc.mean() / PX_PER_MM:+.3f} mm')
    print(f'  std  {inc.std():.2f} px = {inc.std() / PX_PER_MM:.3f} mm')
    print(f'  min {inc.min():+.2f}  max {inc.max():+.2f} px')


if __name__ == '__main__':
    main()
