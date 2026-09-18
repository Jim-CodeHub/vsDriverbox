# -*- coding: utf-8 -*-
"""repro_y_margin.py — 复现现场 "strip 1 needs rows ... outside the y margin"。

对照两组 MotionStartPoint 喂同一批图像：
  A) 数据集原始 MSP        （validate_rt 验证过的基线，应通过）
  B) 现场日志里的 MSP      （整体 +~499880 单位，应复现崩溃）
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

DATA_DIR = os.path.join(ROOT, 'testdata', '20260903', 'stitch')
TRUE_YAML = os.path.join(ROOT, 'testdata', '20260903', 'calib', '4_final_calib.yaml')
FALSE_YAML = os.path.join(ROOT, 'testdata', '20260903', 'calib', '5_final_calib.yaml')

# validate_rt.py 里 20260903 case 的参数（现场 stream_* 缺省同源）
KW = dict(
    d_step_x=846.0527400801201, x_offset_false=5.2406, seam_inset=384,
    canvas_start=8000, canvas_width=21259, hold_pix=300,
    x_base_L=2461080, x_base_R=29191669, x_invert=788,
)

# 现场日志 20260912_143029.log 的 MSP（strip 顺序 = Direction True/False/True/False/True）
FIELD_MSP = {
    0: 0.0,
    1: 29761010.7421875,
    2: 2961140.13671875,
    3: 29691389.16015625,
    4: 2961390.0756835938,
}

try:
    import fastcore
    fastcore.install(use_gpu=False, no_diag=True)
except Exception as exc:
    print('[warn] fastcore:', exc)

from drivers.camera.StreamRealtime import StreamRealtime


def run(tag, msp_override):
    print(f'\n===== {tag} =====')
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    rt = StreamRealtime(TRUE_YAML, FALSE_YAML, log_cb=lambda m: print('  [rt]', m), **KW)
    bands = []
    for i, r in enumerate(recs):
        info = r['Info']
        img = np.array(Image.open(os.path.join(DATA_DIR, r['ImagePath'])))
        msp = msp_override.get(i, float(info['MotionStartPoint'])) if msp_override else float(info['MotionStartPoint'])
        try:
            out = rt.feed_frame(img, float(info['Step']), bool(info['Direction']), msp)
        except Exception as exc:
            print(f'  !! frame {i} 抛异常: {type(exc).__name__}: {exc}')
            return None
        for b, ys in out:
            bands.append((b, ys))
        del img
    print(f'  结果: {len(bands)} 带, 形状 {bands[0][0].shape if bands else None}, '
          f'y_step {sorted(set(ys for _, ys in bands))}')
    return bands


def main():
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    print('=== 数据集 20260903 的 Info ===')
    for i, r in enumerate(recs):
        inf = r['Info']
        f = FIELD_MSP.get(i)
        delta = f'  现场={f:,.2f}  差={f - float(inf["MotionStartPoint"]):+,.1f}' if f is not None else ''
        print(f'  [{i}] Step={inf["Step"]:.4f} dir={inf["Direction"]} MSP={inf["MotionStartPoint"]:,.2f}{delta}')

    run('A) 数据集原始 MSP（基线，预期通过）', None)
    run('B) 现场日志 MSP（预期复现崩溃）', FIELD_MSP)


if __name__ == '__main__':
    main()
