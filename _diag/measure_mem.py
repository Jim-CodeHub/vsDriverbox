# -*- coding: utf-8 -*-
"""measure_mem.py — 长卷回放，实测 Y_MARGIN 加大后 buffer 的内存占用。

采样 StreamRealtime 内部 _buffer 的形状/字节数，以及进程 RSS。
目的：把 Y_MARGIN 4096->8192 的代价从"估算"变成"实测"。
"""
import os
import sys
import json
import time

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, 'testdata', '20260627', 'stitch')
TRUE_YAML = os.path.join(ROOT, 'testdata', '20260627', 'calib', '4_final_calib.yaml')
FALSE_YAML = os.path.join(ROOT, 'testdata', '20260627', 'calib', '3_final_calib.yaml')

# 20260627 旧机器参数（validate_rt.py 的旧机器 case）
KW = dict(
    d_step_x=847.965622809793, x_offset_false=2.908141050525, seam_inset=256,
    canvas_start=7906, canvas_width=21259, hold_pix=500,
    x_base_L=2461790, x_base_R=29057700, x_invert=629,
)

try:
    import fastcore
    fastcore.install(use_gpu=False, no_diag=True)
except Exception:
    pass

try:
    import psutil
    _proc = psutil.Process()
except Exception:
    psutil = None
    _proc = None

import stitch_stream_final as S
from drivers.camera.StreamRealtime import StreamRealtime

FILE_Y_MARGIN = S.Y_MARGIN


def rss_mb():
    if _proc is None:
        return float('nan')
    return _proc.memory_info().rss / 1024 / 1024


def run(y_margin, tag):
    S.Y_MARGIN = y_margin
    print(f'\n===== {tag} (Y_MARGIN={y_margin}) =====')
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    rt = StreamRealtime(TRUE_YAML, FALSE_YAML, log_cb=lambda m: None, **KW)
    samples = []
    n_bands = 0
    t0 = time.time()
    for i, r in enumerate(recs):
        inf = r['Info']
        img = np.array(Image.open(os.path.join(DATA_DIR, r['ImagePath'])))
        try:
            out = rt.feed_frame(img, float(inf['Step']), bool(inf['Direction']),
                                float(inf['MotionStartPoint']))
        except Exception as exc:
            print(f'  !! frame {i}: {type(exc).__name__}: {exc}')
            return None
        n_bands += len(out)
        del img
        buf = rt._stitcher._buffer if rt._stitcher else None
        if buf is not None:
            samples.append((i, buf.shape[0], buf.shape[1], buf.nbytes / 1024 / 1024, rss_mb()))
        if (i % 10 == 0 or i == len(recs) - 1) and samples:
            h, w, mb = samples[-1][1], samples[-1][2], samples[-1][3]
            print(f'  frame {i:>3}: buffer {h} x {w} = {mb:7.1f} MB   RSS {rss_mb():7.1f} MB')
        elif i % 10 == 0:
            print(f'  frame {i:>3}: buffer 尚未建立（MSP 积压期）   RSS {rss_mb():7.1f} MB')
    print(f'  带数 {n_bands}, 耗时 {time.time()-t0:.0f}s')
    if samples:
        peak = max(samples, key=lambda s: s[3])
        last = samples[-1]
        print(f'  buffer 峰值: frame {peak[0]}  {peak[1]}x{peak[2]} = {peak[3]:.1f} MB')
        print(f'  收尾:        {last[1]}x{last[2]} = {last[3]:.1f} MB  (列数是否稳定)')
    return samples


def main():
    print('文件默认 Y_MARGIN =', FILE_Y_MARGIN)
    a = run(FILE_Y_MARGIN, '现状(新)')
    b = run(4096, '对照(旧)')
    if a and b:
        pa = max(a, key=lambda s: s[3])
        pb = max(b, key=lambda s: s[3])
        print('\n===== 实测差值 =====')
        print(f'  buffer 峰值: {pb[3]:.1f} MB (旧) -> {pa[3]:.1f} MB (新)  '
              f'差 {pa[3]-pb[3]:+.1f} MB')
        print(f'  峰值列数:    {pb[2]} (旧) vs {pa[2]} (新)')
        print(f'  RSS 峰值:    {pb[4]:.1f} MB (旧) -> {pa[4]:.1f} MB (新)  '
              f'差 {pa[4]-pb[4]:+.1f} MB')


if __name__ == '__main__':
    main()
