# -*- coding: utf-8 -*-
"""朝向判定实验 2：不预设 fresh/probe 带位置，直接用模板匹配在相邻条带间
搜索同一织物内容的位置，得到 (dy, dx) 与响应。

判定规则（带高 600px，步进 834px）：
  dy ≈ -834 (即 -104 @x8)  -> 两条带行序一致（标准，fabric 随行号增）
  dy ≈ +834 (+104 @x8)     -> 两条带行序一致（反转）
  无峰                      -> 行序不一致（一条翻一条不翻）或列镜像
dx 给出两向在配准网格上的系统差。
"""
import os, sys, json
import numpy as np
import cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from drivers.camera import Charuco

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', 'stitch')
PT = Charuco.Calibration.from_yaml(os.path.join(ROOT, 'testdata', 'calib', '4_final_calib.yaml'))
PF = Charuco.Calibration.from_yaml(os.path.join(ROOT, 'testdata', 'calib', '5_final_calib.yaml'))

infos = json.load(open(os.path.join(DATA, 'LocalImageInfos.json'), encoding='utf-8'))
DIRS = [bool(it['Info']['Direction']) for it in infos]
raw = [np.array(Image.open(os.path.join(DATA, it['ImagePath']))) for it in infos]

PRE = {
    'asis':  lambda a: a,
    'hflip': lambda a: a[:, ::-1],
    'vflip': lambda a: a[::-1, :],
    'hvflip': lambda a: a[::-1, ::-1],
}
S = 8  # downsample

def rect_ds(preT, preF):
    R = []
    for i, d in enumerate(DIRS):
        im = PRE[preT](raw[i]) if d else PRE[preF](raw[i])
        r = Charuco.calibration(im, PT if d else PF)
        R.append(r[::S, ::S].astype(np.float32))
    return R

def match(R_prev, R_cur, r0=900, r1=1500, c0=9000, c1=21000):
    """在 R_cur 中找 R_prev 的 [r0:r1, c0:c1] 带。返回 (dy, dx, peak)。"""
    tpl = R_prev[r0 // S:r1 // S, c0 // S:c1 // S].copy()
    tpl -= tpl.mean()
    res = cv2.matchTemplate(R_cur, tpl, cv2.TM_CCOEFF_NORMED)
    _, peak, _, loc = cv2.minMaxLoc(res)
    dy = loc[1] - r0 // S
    dx = loc[0] - c0 // S
    return dy * S, dx * S, peak

print('=== T=asis, F=hflip（生产路径） ===')
R = rect_ds('asis', 'hflip')
for k in range(1, 8):
    dy, dx, pk = match(R[k - 1], R[k])
    print(f'pair {k-1}->{k} ({"T" if DIRS[k-1] else "F"}->{"T" if DIRS[k] else "F"}): dy={dy:+5d} dx={dx:+6d} peak={pk:.3f}')

print('\n=== T=asis, F=asis ===')
R = rect_ds('asis', 'asis')
for k in range(1, 8):
    dy, dx, pk = match(R[k - 1], R[k])
    print(f'pair {k-1}->{k}: dy={dy:+5d} dx={dx:+6d} peak={pk:.3f}')

print('\n=== T=vflip, F=hvflip（T、F 都再翻 180°） ===')
R = rect_ds('vflip', 'hvflip')
for k in range(1, 8):
    dy, dx, pk = match(R[k - 1], R[k])
    print(f'pair {k-1}->{k}: dy={dy:+5d} dx={dx:+6d} peak={pk:.3f}')

print('\n=== T=vflip, F=vflip ===')
R = rect_ds('vflip', 'vflip')
for k in range(1, 8):
    dy, dx, pk = match(R[k - 1], R[k])
    print(f'pair {k-1}->{k}: dy={dy:+5d} dx={dx:+6d} peak={pk:.3f}')
