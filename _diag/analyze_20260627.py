# -*- coding: utf-8 -*-
"""20260627 批次三方案漂移分析（复用 testdata/tools 的工具函数）。

方案：
  A_old  旧拼接器 + 出厂 v6 标定（项目默认配置，现场现状）
  B_new  旧拼接器 + 本批 v7 标定（只换 yaml）
  C_str  流式拼接器 + 本批 v7 标定（本次合入）

指标（与 tools/stitch_report.py 同口径）：
  每缝 dx（列剖面相位相关，8 窗中位）→ 按时间序分 T/F：
    共模 cm = (mean_T+mean_F)/2   同向偏置 → “越来越偏”的每缝漂移
    差模 dm = (mean_T-mean_F)/2   交替锯齿 → 每条缝上肉眼可见错位
    单缝 rms / max
  布边列位置 → 布料在画布里走不走（真正的“越来越偏”观感）
  缝不连续度 disc = 缝上行差 - 本底

缝行定位：
  A/B：均匀 834 条带，缝 = k*834（tools 原口径）
  C：缝行由 stream_frame_log.csv 推出再梯度吸附（复用 v2.seam_rows）；
     注意 C 的画布时间序是反的（strip 69 在顶部），dx 取时间序需要变号，
     方向标签取“后一条带”（时间上后到的）。

时间序 dx 约定：dx_time = 后一条带内容相对前一条带的列偏移。
"""
import os
import sys
import csv
import json

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'testdata', 'tools'))

from stitch_report import seam_dx, fabric_cols  # noqa: E402  工具函数
import stitch_stream_finalv2 as v2  # noqa: E402（项目根目录，fastcore 同名约定）
from pathlib import Path  # noqa: E402

DATA_DIR = os.path.join(ROOT, 'testdata', '20260627', 'stitch')
recs = json.load(open(os.path.join(DATA_DIR, 'LocalImageInfos.json'), encoding='utf-8'))
DIRS = [bool(r['Info']['Direction']) for r in recs]
N = len(recs)

OUT = os.path.join(ROOT, 'testdata', 'out')


def decompose(dx, d_later):
    """dx: 时间序每缝错位；d_later: 每缝后一条带方向。返回 cm/dm/rms/max/n。"""
    g = np.isfinite(dx)
    dxg = dx[g]
    dg = np.asarray(d_later)[g]
    mT = dxg[dg].mean() if dg.sum() else np.nan
    mF = dxg[~dg].mean() if (~dg).sum() else np.nan
    cm = 0.5 * (mT + mF)
    dm = 0.5 * (mT - mF)
    resid = dxg - np.where(dg, mT, mF)
    return dict(mT=mT, mF=mF, cm=cm, dm=dm,
                rms=float(np.sqrt((dxg ** 2).mean())),
                mx=float(np.abs(dxg).max()),
                rms_rand=float(np.sqrt((resid ** 2).mean())),
                n=int(g.sum()),
                dx=dx)


def cloth_walk(canvas, seam_rows):
    """按画布条带量布边列位置，返回 (每带左缘, 每带右缘)。
    seam_rows: 该画布的条带边界（含 0 和 H）。"""
    H = canvas.shape[0]
    bounds = [0] + [int(r) for r in seam_rows] + [H]
    lefts, rights = [], []
    for i in range(len(bounds) - 1):
        y0, y1 = bounds[i] + 60, bounds[i + 1] - 60
        if y1 - y0 < 100:
            y1 = bounds[i + 1]
        r = fabric_cols(canvas[y0:y1])
        lefts.append(r[0] if r else np.nan)
        rights.append(r[1] if r else np.nan)
    return np.array(lefts, dtype=float), np.array(rights, dtype=float)


def disc(canvas, seam_rows):
    d = np.abs(canvas[1:].astype(np.int16) - canvas[:-1].astype(np.int16)).mean(axis=1)
    mask = np.ones(len(d), bool)
    for R in seam_rows:
        if 0 <= R - 1 < len(d):
            mask[R - 1] = False
    base = float(d[mask].mean())
    vals = [float(d[R - 1]) for R in seam_rows if 0 <= R - 1 < len(d)]
    return float(np.mean(vals)) - base


def report(tag, canvas, seam_rows, dx_time, d_later, time_band_index):
    dec = decompose(np.asarray(dx_time, dtype=float), d_later)
    lefts, rights = cloth_walk(canvas, seam_rows)
    # 布边走动：对时间序做线性拟合（斜率 px/条带）
    li = np.argsort(time_band_index)          # 时间升序
    l_t, r_t = lefts[li], rights[li]
    tt = np.asarray(time_band_index)[li]
    gl, gr = np.isfinite(l_t), np.isfinite(r_t)
    sl = np.polyfit(tt[gl], l_t[gl], 1)[0] if gl.sum() > 2 else np.nan
    sr = np.polyfit(tt[gr], r_t[gr], 1)[0] if gr.sum() > 2 else np.nan
    print('\n==== %s ====' % tag)
    print(' 缝数 %d (有效 %d)   单缝 rms %.2f px   最大 %.2f px' %
          (len(dx_time), dec['n'], dec['rms'], dec['mx']))
    print(' 共模 cm = %+.3f px/缝  (mean_T %+.2f / mean_F %+.2f)   差模 dm = %+.3f px' %
          (dec['cm'], dec['mT'], dec['mF'], dec['dm']))
    print(' 随机 rms %.2f px   cm 全程累积 %+.1f px   布边左 %+.2f px/带 右 %+.2f px/带' %
          (dec['rms_rand'], dec['cm'] * dec['n'], sl, sr))
    print(' 缝不连续超出 %+.2f' % disc(canvas, seam_rows))
    return dec


# ---------------- A / B：旧拼接器，均匀 834 ----------------
for tag, tif in [('A_old (旧拼接器+出厂v6标定)', '20260627_oldstitcher_A_oldcalib.tif'),
                 ('B_new (旧拼接器+本批v7标定)', '20260627_oldstitcher_B_newcalib.tif')]:
    cv = np.asarray(Image.open(os.path.join(OUT, tif)))
    H = cv.shape[0]
    nb = H // 834
    seams = [k * 834 for k in range(1, nb)]
    dx = [seam_dx(cv, R) for R in seams]
    d_later = [DIRS[k] for k in range(1, nb)]          # 缝 k*834 的下方 = 条带 k（时间后到）
    band_time = list(range(nb))                         # 画布带 i = 条带 i（时间正序）
    report(tag, cv, seams, dx, d_later, band_time)
    del cv

# ---------------- C：流式拼接器 ----------------
run = Path(os.path.join(OUT, '20260627_stream', '_base_stitch'))
tif = sorted(run.glob('stitched_*_stream.tif'))[0]
cv = np.asarray(Image.open(tif))
H = cv.shape[0]
seams_info = v2.seam_rows(run, cv)                       # [(pair 'a_b', row), ...] 时间反序画布
seam_rows_ = [s['row'] for s in seams_info]
# 时间序 dx：画布下方 = 时间上更早的条带 → 变号；方向 = 后到的（上方）= b
dx, d_later = [], []
for s in seams_info:
    a, b = (int(v) for v in s['pair'].split('_'))
    d = seam_dx(cv, int(s['row']))
    dx.append(-d if d == d else d)                       # NaN 保持
    d_later.append(DIRS[b])
band_time = [N - 1 - i for i in range(len(seam_rows_) + 1)]  # 顶部带 = 条带 69 → 时间反序
report('C_str (流式拼接器+本批v7标定)', cv, seam_rows_, dx, d_later, band_time)
