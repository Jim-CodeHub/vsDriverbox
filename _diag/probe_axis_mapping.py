# -*- coding: utf-8 -*-
"""测定旧引擎条带坐标 (swath, travel) 与流式引擎条带坐标 (travel, swath)
之间的镜像/偏移关系（T/F 各测一帧）。

- 旧引擎: Charuco.calibration(img, cal) -> (swath 2240, travel 30785)
- 流式:   hflip(F) + stitch_stream_final.rectify_image_array -> (travel 30785, swath 2240)
用行/列均值剖面的互相关（正反两个方向）判定镜像与偏移。
"""
import sys, os, json
import numpy as np
import cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from drivers.camera import Charuco
import stitch_stream_final as S

D = os.path.join(ROOT, 'testdata', '20260627')
YT = os.path.join(D, 'calib', '4_final_calib.yaml')
YF = os.path.join(D, 'calib', '3_final_calib.yaml')
recs = json.load(open(os.path.join(D, 'stitch', 'LocalImageInfos.json'), encoding='utf-8'))

calT = Charuco.Calibration.from_yaml(YT)
calF = Charuco.Calibration.from_yaml(YF)
calT_s = S.load_calibration_yaml(YT)
calF_s = S.load_calibration_yaml(YF)


def corr_offset(a, b, rng=400):
    """b 相对 a 的偏移（亚像素抛物线）。返回 (offset, peak)。"""
    a = a.astype(np.float64); b = b.astype(np.float64)
    a = a - a.mean(); b = b - b.mean()
    n = min(len(a), len(b))
    m = rng
    aa = a[m:len(a)-m]
    best, bo = -9e99, 0
    for d in range(-rng, rng+1):
        bb = b[m+d:m+d+len(aa)]
        v = float((aa*bb).sum())
        if v > best:
            best, bo = v, d
    return bo, best


for idx in (0, 1):   # 0=T, 1=F
    r = recs[idx]
    img = np.array(Image.open(os.path.join(D, 'stitch', r['ImagePath'])))
    d = bool(r['Info']['Direction'])
    old = Charuco.calibration(img, calT if d else calF)          # (swath, travel)
    img2 = img if d else cv2.flip(img, 1)
    new = S.rectify_image_array(img2, calT_s if d else calF_s, S.RECTIFY_OPTIONS)
    new = S.ensure_grayscale(new)                                # (travel, swath)
    print('=== 帧%d 方向%s: old %s, new %s' % (idx, 'T' if d else 'F', old.shape, new.shape))

    # travel 轴：old 的列均值剖面（axis=0） vs new 的行均值剖面（axis=1）
    p_old_t = old.mean(axis=0)
    p_new_t = new.mean(axis=1)
    off_dir, pk_dir = corr_offset(p_old_t, p_new_t)
    off_rev, pk_rev = corr_offset(p_old_t, p_new_t[::-1])
    rev = pk_rev > pk_dir
    print('  travel: 直接 off=%+d peak=%.3e | 反向 off=%+d peak=%.3e  => %s' %
          (off_dir, pk_dir, off_rev, pk_rev, '反向(镜像)' if rev else '同向'))
    off = off_rev if rev else off_dir
    # 镜像时：new_r = (L-1) - old_c + off'，从 off 换算：见下验证

    # swath 轴：old 的行均值剖面（axis=1） vs new 的列均值剖面（axis=0）
    p_old_s = old.mean(axis=1)
    p_new_s = new.mean(axis=0)
    off_dir2, pk_dir2 = corr_offset(p_old_s, p_new_s)
    off_rev2, pk_rev2 = corr_offset(p_old_s, p_new_s[::-1])
    rev2 = pk_rev2 > pk_dir2
    print('  swath : 直接 off=%+d peak=%.3e | 反向 off=%+d peak=%.3e  => %s' %
          (off_dir2, pk_dir2, off_rev2, pk_rev2, '反向(镜像)' if rev2 else '同向'))

    # 2D 验证：old 中心小块 在 new 中（按判定的镜像组合）应能找到
    r0, c0 = old.shape[0]//2, old.shape[1]//2
    ph, pw = 400, 2000
    tpl = old[r0:r0+ph, c0:c0+pw].astype(np.float32)
    cand = new
    if rev:   # travel 镜像: old col c -> new row (L-1-c)
        cand = cand[::-1, :]
    if rev2:  # swath 镜像: old row r -> new col (L'-1-r)
        cand = cand[:, ::-1]
    res = cv2.matchTemplate(cand.astype(np.float32), tpl, cv2.TM_CCOEFF_NORMED)
    _, pk, _, loc = cv2.minMaxLoc(res)
    print('  2D 验证: new 中找到 old 块, peak=%.4f, 位于 new(%d,%d) vs 期望(%d,%d)' %
          (pk, loc[1], loc[0], r0, c0))
