# -*- coding: utf-8 -*-
"""test_y_margin_fix.py — 验证加大 Y_MARGIN 是否既能修好现场、又不改变摆放结果。

Y_MARGIN 只决定 buffer 上下各留多少填充：canvas_y = raw_y - _y_of_row0，
而 _y_of_row0 = raw_y0 - Y_MARGIN。所以加大 Y_MARGIN 只是把所有 canvas_y
整体上移同一个量，条带之间的相对关系（也就是缝质量）不应改变。

验证两件事：
  1) 数据集(A) 在 Y_MARGIN=4096 / 8192 下产出的带应逐字节相同  -> 改动无害
  2) 现场(B) 在加大后的 Y_MARGIN 下应不再崩溃
"""
import os
import sys
import json

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, 'testdata', '20260903', 'stitch')
TRUE_YAML = os.path.join(ROOT, 'testdata', '20260903', 'calib', '4_final_calib.yaml')
FALSE_YAML = os.path.join(ROOT, 'testdata', '20260903', 'calib', '5_final_calib.yaml')

KW = dict(
    d_step_x=846.0527400801201, x_offset_false=5.2406, seam_inset=384,
    canvas_start=8000, canvas_width=21259, hold_pix=300,
    x_base_L=2461080, x_base_R=29191669, x_invert=788,
)
FIELD_MSP = {0: 0.0, 1: 29761010.7421875, 2: 2961140.13671875,
             3: 29691389.16015625, 4: 2961390.0756835938}

try:
    import fastcore
    fastcore.install(use_gpu=False, no_diag=True)
except Exception:
    pass

import stitch_stream_final as S
from drivers.camera.StreamRealtime import StreamRealtime


def run(msp_override, y_margin):
    S.Y_MARGIN = int(y_margin)
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    rt = StreamRealtime(TRUE_YAML, FALSE_YAML, log_cb=lambda m: None, **KW)
    bands, err = [], None
    for i, r in enumerate(recs):
        info = r['Info']
        img = np.array(Image.open(os.path.join(DATA_DIR, r['ImagePath'])))
        msp = msp_override.get(i, float(info['MotionStartPoint'])) if msp_override else float(info['MotionStartPoint'])
        try:
            out = rt.feed_frame(img, float(info['Step']), bool(info['Direction']), msp)
        except Exception as exc:
            err = f'{type(exc).__name__}: {exc}'
            break
        bands.extend(out)
        del img
    return bands, err


def main():
    print('--- 1) 无害性：数据集在两种 Y_MARGIN 下的带是否逐字节相同 ---')
    a1, e1 = run(None, 4096)
    a2, e2 = run(None, 8192)
    print(f'  Y_MARGIN=4096: {len(a1)} 带, err={e1}')
    print(f'  Y_MARGIN=8192: {len(a2)} 带, err={e2}')
    if a1 and a2 and len(a1) == len(a2):
        same = all(np.array_equal(b1, b2) and y1 == y2
                   for (b1, y1), (b2, y2) in zip(a1, a2))
        print(f'  带内容逐字节相同: {same}')
    else:
        print('  !! 带数不同，无法比较')

    print('\n--- 2) 修复性：现场 MSP 在不同 Y_MARGIN 下是否通过 ---')
    for m in (4096, 6144, 8192):
        b, err = run(FIELD_MSP, m)
        status = f'{len(b)} 带' if not err else f'崩溃 -> {err[:70]}'
        print(f'  Y_MARGIN={m}: {status}')

    print('\n--- 3) 内存代价 ---')
    for m in (4096, 6144, 8192):
        h = 30785 + 2 * m
        print(f'  Y_MARGIN={m}: buffer 高 {h} 行'
              f'（按滚动裁剪后约 9000 列估算 ≈ {h * 9000 / 1024 / 1024:.0f} MB）')


if __name__ == '__main__':
    main()
