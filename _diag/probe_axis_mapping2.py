# -*- coding: utf-8 -*-
"""正确版坐标映射探针：旧条带 (swath, travel) vs 流式条带 (travel, swath)。

假设（由 buffer 一致性推出）：
  old(r_swath, c_travel) = new(c_travel + off_t, (SW-1 - r_swath) + off_s)
即 travel 轴同向（+off_t），swath 轴镜像（+off_s）。用 2D 模板匹配验证。
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


def verify(old, new, tag):
    """在 new 中按假设映射找 old 的块。"""
    H_sw, W_tr = old.shape          # (2238, 30786)
    r0, c0 = 900, 12000
    ph, pw = 400, 3000
    tpl = old[r0:r0+ph, c0:c0+pw].astype(np.float32)
    # 候选区域：new[c0-m : c0+pw+m, 对应 swath 镜像范围]
    m = 150
    # swath 镜像: r -> (H_new_swath-1 - r)，取镜像后 r0-m..r0+ph+m 的范围
    lo_r = H_sw - 1 - (r0 + ph + m)
    hi_r = H_sw - 1 - (r0 - m)
    region = new[c0-m:c0+pw+m, lo_r:hi_r].astype(np.float32)   # (travel范围, swath范围)
    region_m = region[:, ::-1]                                   # 撤销镜像 -> r 升序
    target = region_m.T                                          # (swath, travel) 同 old 布局
    res = cv2.matchTemplate(target, tpl, cv2.TM_CCOEFF_NORMED)
    _, pk, _, loc = cv2.minMaxLoc(res)
    # loc 是 target 里的位置: target[i,j] = region_m[j, i] = region[j, W-i-1]
    #   -> new 行 = c0-m+j, new 列 = lo_r + (W-i-1)
    jj, ii = loc
    new_row = c0 - m + jj
    new_col = lo_r + (region_m.shape[1] - 1 - ii)
    print('%s: peak=%.4f  old块(r%d,c%d) 找到于 new(row=%d, col=%d)   期望 row≈c%d, col≈%d' %
          (tag, pk, r0, c0, new_row, new_col, c0, H_sw - 1 - r0))
    print('   => off_t = %+d, off_s = %+d' % (new_row - c0, new_col - (H_sw - 1 - r0)))


for idx in (0, 1):
    r = recs[idx]
    img = np.array(Image.open(os.path.join(D, 'stitch', r['ImagePath'])))
    d = bool(r['Info']['Direction'])
    img_old = img if d else img[:, ::-1]      # 旧引擎：F 图先 hflip 再用 F 标定
    old = Charuco.calibration(img_old, calT if d else calF)
    img2 = img if d else cv2.flip(img, 1)     # 流式引擎：同样 hflip
    new = S.ensure_grayscale(S.rectify_image_array(img2, calT_s if d else calF_s, S.RECTIFY_OPTIONS))
    print('=== 帧%d 方向%s: old %s new %s' % (idx, 'T' if d else 'F', old.shape, new.shape))
    verify(old, new, 'travel同向+swath镜像')
    # 对照：纯转置（无镜像）
    m = 150
    region = new[12000-150:12000+3000+150, 900-150:900+400+150].astype(np.float32)
    tpl = old[900:1300, 12000:15000].astype(np.float32)
    res2 = cv2.matchTemplate(region.T, tpl, cv2.TM_CCOEFF_NORMED)
    _, pk2, _, loc2 = cv2.minMaxLoc(res2)
    print('   对照(纯转置无镜像): peak=%.4f  位置(new row=%d, col=%d)' % (pk2, 12000-150+loc2[1], 900-150+loc2[0]))
