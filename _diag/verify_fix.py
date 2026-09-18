# -*- coding: utf-8 -*-
"""verify_fix.py — 用文件里的真实 Y_MARGIN 默认值做最终验证。"""
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

FILE_Y_MARGIN = S.Y_MARGIN      # 必须在任何覆盖之前抓取
print('文件里的 Y_MARGIN =', FILE_Y_MARGIN)


def run(msp_override, y_margin=None):
    S.Y_MARGIN = FILE_Y_MARGIN if y_margin is None else y_margin
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    rt = StreamRealtime(TRUE_YAML, FALSE_YAML, log_cb=lambda m: None, **KW)
    bands, err = [], None
    for i, r in enumerate(recs):
        inf = r['Info']
        img = np.array(Image.open(os.path.join(DATA_DIR, r['ImagePath'])))
        msp = msp_override.get(i, float(inf['MotionStartPoint'])) if msp_override else float(inf['MotionStartPoint'])
        try:
            out = rt.feed_frame(img, float(inf['Step']), bool(inf['Direction']), msp)
        except Exception as exc:
            err = f'{type(exc).__name__}: {exc}'
            break
        bands.extend(out)
        del img
    return bands, err


# 基线：强制回退成旧值再现一次
base, e0 = run(None, 4096)
print(f'基线 (Y_MARGIN=4096, 数据集): {len(base)} 带, err={e0}')

# 现状：文件默认值
cur_file = FILE_Y_MARGIN
a, e1 = run(None)
print(f'现状 (Y_MARGIN={cur_file}, 数据集): {len(a)} 带, err={e1}')
if a and base:
    print('  与基线带内容逐字节相同:',
          all(np.array_equal(x, y) and s == t for (x, s), (y, t) in zip(base, a)))
    print(f'  带形状 {a[0][0].shape}, y_step {sorted(set(s for _, s in a))}')

b, e2 = run(FIELD_MSP, cur_file)
print(f'现状 (Y_MARGIN={cur_file}, 现场 MSP): {len(b)} 带, err={e2}')
if b:
    print(f'  带形状 {b[0][0].shape}, y_step {sorted(set(s for _, s in b))}')

print('\n结论:', 'PASS' if (a and b and not e1 and not e2) else 'FAIL')
