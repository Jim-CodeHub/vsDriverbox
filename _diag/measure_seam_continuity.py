# -*- coding: utf-8 -*-
"""measure_seam_continuity.py — 量测真正的接缝对齐误差。

第 k 带的底边（最后 34 行）与第 k+1 带的顶边（最前 34 行）在行进方向上是
紧挨着的，若引擎摆放正确，两者沿幅宽方向的剖面应当重合（错位≈0）。
这个错位才是引擎的真实对齐误差（前面量到的 6.9 px/带 是剪切量，不是误差）。
"""
import os
import re

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', 'gray_tar')
PX_PER_MM = 300 / 25.4
EDGE = 34


def natural_key(p):
    return int(re.search(r'(\d+)', os.path.basename(p)).group(1))


def edge_profile(img, top):
    seg = img[:EDGE, :] if top else img[-EDGE:, :]
    pr = seg.astype(np.float64).mean(axis=0)
    return pr - pr.mean()


def xcorr_shift(a, b, max_shift=120):
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
    bots, tops = [], []
    for p in files:
        img = np.asarray(Image.open(p))
        if img.ndim == 3:
            img = img.mean(axis=2)
        bots.append(edge_profile(img, top=False))
        tops.append(edge_profile(img, top=True))
        del img

    print(f'{"缝":>4} {"k底->k+1顶(px)":>18} {"mm":>8} {"相关度":>8}')
    offs, corrs = [], []
    for k in range(len(files) - 1):
        d, c = xcorr_shift(bots[k], tops[k + 1])
        offs.append(d)
        corrs.append(c)
        print(f'{k:>4} {d:>18.2f} {d / PX_PER_MM:>8.3f} {c:>8.3f}')

    offs = np.array(offs)
    corrs = np.array(corrs)
    ok = corrs > 0.5
    print(f'\n可信缝: {ok.sum()}/{len(ok)}')
    if ok.sum():
        v = offs[ok]
        print(f'  接缝错位 mean {v.mean():+.2f} px = {v.mean() / PX_PER_MM:+.3f} mm')
        print(f'            std  {v.std():.2f} px = {v.std() / PX_PER_MM:.3f} mm')
        print(f'            |max| {np.abs(v).max():.2f} px = '
              f'{np.abs(v).max() / PX_PER_MM:.3f} mm')


if __name__ == '__main__':
    main()
