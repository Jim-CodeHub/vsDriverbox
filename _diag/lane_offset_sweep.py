# -*- coding: utf-8 -*-
"""纵向接缝根因验证：扰动 5_final 的 coordinate_offset_mm.y_mm，
测 T->F 与 F->T 的织物实际行进量是否同时变为 834。

背景：拼接器每条固定切 834 行。实测行进量 T->F=828.75 / F->T=840.33，
说明 F 网格整体纵向偏了 ~5.8 行（~0.49mm）——即标定配准时用的那一步
（70.23mm）与拼接步距（70.61mm）不一致。
"""
import os, sys, json, copy
import numpy as np
import cv2
import yaml
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from drivers.camera import Charuco

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'testdata', 'stitch')
SRC = os.path.join(ROOT, 'testdata', 'calib', '5_final_calib.yaml')

infos = json.load(open(os.path.join(DATA, 'LocalImageInfos.json'), encoding='utf-8'))
raw = [np.array(Image.open(os.path.join(DATA, it['ImagePath']))) for it in infos]
DIRS = [bool(it['Info']['Direction']) for it in infos]

base = yaml.safe_load(open(SRC, encoding='utf-8'))
pt = Charuco.Calibration.from_yaml(os.path.join(ROOT, 'testdata', 'calib', '4_final_calib.yaml'))

def adv(dy):
    return -dy

def measure(off_y):
    d = copy.deepcopy(base)
    d['output_defaults']['target_grid']['coordinate_offset_mm']['y_mm'] = float(off_y)
    tmp = os.path.join(ROOT, '_diag', '_tmp_5.yaml')
    yaml.safe_dump(d, open(tmp, 'w', encoding='utf-8'), allow_unicode=True)
    pf = Charuco.Calibration.from_yaml(tmp)
    R = []
    for i, dr in enumerate(DIRS):
        R.append(Charuco.calibration(raw[i], pt) if dr else Charuco.calibration(raw[i][:, ::-1], pf))
    res = []
    for k in range(1, 8):
        A, B = R[k - 1], R[k]
        tpl = A[1000:1300, 9000:15000].astype(np.float32).copy(); tpl -= tpl.mean()
        r = cv2.matchTemplate(B.astype(np.float32), tpl, cv2.TM_CCOEFF_NORMED)
        _, _, _, loc = cv2.minMaxLoc(r)
        res.append(loc[1] - 1000)
    # res[k-1] 是 pair k。T->F: k=1,3,5,7；F->T: k=2,4,6
    tf = [adv(res[k - 1]) for k in (1, 3, 5, 7)]
    ft = [adv(res[k - 1]) for k in (2, 4, 6)]
    return tf, ft

print('off.y      T->F 行进量(4缝)          F->T 行进量(3缝)        目标都是834')
for dy in [None, -70.6, -70.7, -70.75, -70.8, -70.9]:
    if dy is None:
        tf, ft = measure(-70.229)
        tag = '%-10s' % ('原始-70.229')
    else:
        tf, ft = measure(dy)
        tag = '%-10.2f' % dy
    print('%s  %s  avg=%6.2f   %s  avg=%6.2f' % (
        tag, tf, float(np.mean(tf)), ft, float(np.mean(ft))))
