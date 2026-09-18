# -*- coding: utf-8 -*-
"""20260627 批次：旧拼接器（Camera.ImageStitch，项目默认参数）两组对照。

A) 出厂 v6 标定对（calib/4_registered + 3_hflip_registered）
B) 本批 v7 标定对（testdata/20260627/calib/4_final + 3_final）
均为 seam_refine=True（现场默认），画布/基准/偏移全部用项目默认值。
产物存 testdata/out/，日志行存 _diag 供漂移分析。
"""
import os
import sys
import time
import re

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from drivers.camera.Camera import Camera

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', '20260627', 'stitch')
OUT = os.path.join(ROOT, 'testdata', 'out')

CASES = [
    ('A_oldcalib', r'calib\4_registered_calib.yaml', r'calib\3_hflip_registered_calib.yaml'),
    ('B_newcalib', os.path.join('testdata', '20260627', 'calib', '4_final_calib.yaml'),
                   os.path.join('testdata', '20260627', 'calib', '3_final_calib.yaml')),
]

for name, yt, yf in CASES:
    lines = []

    def log(msg, _lines=lines):
        _lines.append(str(msg))

    st = Camera.ImageStitch(
        x_base_L=2461790, x_base_R=29057700, x_invert=629,
        canvas_start=7906, canvas_width=21259, DPI=300, hold_pix=500,
        YamlPath=yt, YamlPathFalse=yf,
        log_cb=log, cal_sel='new', seam_refine=True)
    ok = st.load_calib_yaml()
    print('==== %s  calib load: %s' % (name, ok))
    if not ok:
        for l in lines:
            print('  |', l)
        continue
    t0 = time.perf_counter()
    canvas = st.stitch_from_json(DATA, 'LocalImageInfos.json')
    dt = time.perf_counter() - t0
    p = os.path.join(OUT, '20260627_oldstitcher_%s.tif' % name)
    Image.fromarray(canvas).save(p, compression='tiff_lzw')
    print('  canvas %s in %.1fs -> %s' % (canvas.shape, dt, p))
    # 摆放轨迹（shift 爬升 = 闭环在追漂移）
    shifts = []
    for l in lines:
        m = re.search(r'seam dx=(\S+) src=(\S+) applied=(\S+) shift=([+-]?\d+)', l)
        if m:
            shifts.append(int(m.group(4)))
    print('  seam log 行数 %d, shift 末值 %+d, shift 轨迹前20: %s' %
          (len(shifts), shifts[-1] if shifts else 0, shifts[:20]))
    open(os.path.join(ROOT, '_diag', 'oldstitcher_%s_log.txt' % name), 'w',
         encoding='utf-8').write('\n'.join(lines))
