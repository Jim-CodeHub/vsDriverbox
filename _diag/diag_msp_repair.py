# -*- coding: utf-8 -*-
"""diag_msp_repair.py — 插桩打印 strip 0 的 MSP 修复值与各 strip 的摆放数值。"""
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

_orig_paste = S.StreamingStitcher._paste


def _patched_paste(self, record, image):
    row = int(record["canvas_y"])
    h = image.shape[0]
    print(f'   [_paste] strip {record["index"]}: row={row} h={h} '
          f'buffer_h={self._buffer.shape[0]} dir={record["direction"]} '
          f'msp={record["original_msp"]:.1f} std_msp={record["standard_msp"]:.1f} '
          f'raw_y_nom={record["raw_y_nominal"]:.1f}')
    return _orig_paste(self, record, image)


S.StreamingStitcher._paste = _patched_paste


def run(tag, msp_override):
    print(f'\n===== {tag} =====')
    recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
    rt = StreamRealtime(TRUE_YAML, FALSE_YAML, log_cb=lambda m: None, **KW)
    n = 0
    for i, r in enumerate(recs):
        info = r['Info']
        img = np.array(Image.open(os.path.join(DATA_DIR, r['ImagePath'])))
        msp = msp_override.get(i, float(info['MotionStartPoint'])) if msp_override else float(info['MotionStartPoint'])
        try:
            out = rt.feed_frame(img, float(info['Step']), bool(info['Direction']), msp)
        except Exception as exc:
            print(f'   !! frame {i}: {type(exc).__name__}: {exc}')
            return
        n += len(out)
        del img
    print(f'   通过: {n} 带')


if __name__ == '__main__':
    run('A) 数据集原始 MSP', None)
    run('B) 现场日志 MSP', FIELD_MSP)
