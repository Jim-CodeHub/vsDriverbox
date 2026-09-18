# -*- coding: utf-8 -*-
"""从拼接结果画布中切出每条接缝附近的放大图，垂直堆叠成一张图供目视检查。

接缝位置：每条条带贡献 834 行，接缝在 834, 1668, ..., 5838 行处。
"""
import os
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CANVAS = os.path.join(ROOT, 'testdata', 'out', 'canvas_v7_newcalib_refine.png')
OUT = os.path.join(ROOT, 'testdata', 'out', 'seam_zoom_montage.png')

c = np.array(Image.open(CANVAS))
H, W = c.shape
print('canvas', c.shape)

FWD = 834
HALF = 80          # 接缝上下各取的行数
COL0, COL1 = 9000, 15000   # 展示的列窗口（画布中部）

rows = []
for k in range(1, 8):
    y = k * FWD
    y0, y1 = max(0, y - HALF), min(H, y + HALF)
    crop = c[y0:y1, COL0:COL1]
    rows.append(crop)
    print('seam %d at row %d: crop %s' % (k, y, crop.shape))

m = np.vstack(rows)
# 归一化到 8bit 便于查看
if m.dtype != np.uint8:
    lo, hi = np.percentile(m, 1), np.percentile(m, 99)
    m8 = np.clip((m.astype(np.float32) - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
else:
    m8 = m
Image.fromarray(m8).save(OUT)
print('saved', OUT, m8.shape)
