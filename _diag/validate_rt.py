# -*- coding: utf-8 -*-
"""StreamRealtime 离线验证：模拟实时喂帧，逐带与旧引擎画布对比。

B 画布（旧引擎+v7 标定）= 旧路径转发带的逐带 vstack —— 即逐带 ground truth。
验证点：
  1. 带数量 / 形状 / y_step 与旧口径一致
  2. 每带内容与旧带对齐（局部互相关 -> 横向偏移应近似常数=锚定偏移+微漂）
  3. 自身缝质量（拼接我的带 -> 共模/差模分解，应为 C 级）
  4. 每帧耗时（实时预算）
"""
import os
import sys
import time
import json

import numpy as np
import cv2
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'testdata', 'tools'))

from drivers.camera.StreamRealtime import StreamRealtime  # noqa: E402
from stitch_report import seam_dx          # noqa: E402


def run_case(tag, data_dir, true_yaml, false_yaml, b_tif, *, d_step_x,
             x_offset_false, seam_inset, canvas_start, canvas_width, hold_pix,
             x_base_L, x_base_R, x_invert, limit=None):
    recs = json.load(open(os.path.join(data_dir, 'LocalImageInfos.json'), encoding='utf-8'))
    if limit:
        recs = recs[:limit]
    B = np.asarray(Image.open(b_tif))

    rt = StreamRealtime(
        true_yaml, false_yaml,
        d_step_x=d_step_x, x_offset_false=x_offset_false, seam_inset=seam_inset,
        canvas_start=canvas_start, canvas_width=canvas_width, hold_pix=hold_pix,
        x_base_L=x_base_L, x_base_R=x_base_R, x_invert=x_invert,
        log_cb=lambda m: print('   [rt]', m))

    all_bands = []
    times = []
    for i, r in enumerate(recs):
        img = np.array(Image.open(os.path.join(data_dir, r['ImagePath'])))
        info = r['Info']
        t0 = time.perf_counter()
        bands = rt.feed_frame(img, info['Step'], info['Direction'], info['MotionStartPoint'])
        times.append(time.perf_counter() - t0)
        for b, ys in bands:
            all_bands.append((b, ys))
        del img

    print('\n===== %s =====' % tag)
    print('带数 %d / 帧数 %d   带形状 %s   y_step 集合 %s' %
          (len(all_bands), len(recs), all_bands[0][0].shape if all_bands else None,
           sorted(set(ys for _, ys in all_bands))))
    ts = np.array(times)
    print('每帧耗时: mean %.2fs  p95 %.2fs  max %.2fs  (含首帧 MSP 等待的释放峰值)' %
          (ts.mean(), np.percentile(ts, 95), ts.max()))
    peak_hold = max(len(rt._infos) - len(all_bands), 0)
    print('MSP 积压峰值: %d 帧' % peak_hold)

    # 逐带与 B 对比（局部互相关，取横向偏移）
    W = all_bands[0][0].shape[1]
    offsets, resps = [], []
    for k, (band, ys) in enumerate(all_bands):
        r0 = k * ys
        if r0 + ys > B.shape[0]:
            break
        bref = B[r0:r0 + ys]
        # 中心窗口互相关（±80px）
        c0, c1 = W // 3, W // 3 + 6000
        a = bref[:, c0:c1].mean(axis=0).astype(np.float64)
        b = band[:, c0:c1].mean(axis=0).astype(np.float64)
        a -= a.mean(); b -= b.mean()
        best, bo = -9e99, 0
        for d in range(-80, 81):
            if d >= 0:
                x, y = a[:len(a) - d], b[d:]
            else:
                x, y = a[-d:], b[:len(b) + d]
            v = float((x * y).sum())
            if v > best:
                best, bo = v, d
        na = np.linalg.norm(a) * np.linalg.norm(b) + 1e-9
        offsets.append(bo)
        resps.append(best / na)
    offsets = np.array(offsets)
    resps = np.array(resps)
    print('逐带横向偏移 vs B: mean %+.2f px  std %.2f  min %+.1f  max %+.1f  '
          '(漂移差=两引擎各自残差)' % (offsets.mean(), offsets.std(), offsets.min(), offsets.max()))
    print('互相关响应: mean %.3f  min %.3f' % (resps.mean(), resps.min()))

    # 自身缝质量（拼接我的带 -> 共模/差模）
    seams = []
    y = 0
    for band, ys in all_bands:
        seams.append(y)
        y += ys
    mine = np.vstack([b for b, _ in all_bands])
    dxs = [seam_dx(mine, R) for R in seams[1:]]
    dirs = [bool(recs[k]['Info']['Direction']) for k in range(1, len(all_bands))]
    g = np.isfinite(dxs)
    dxg = np.array(dxs)[g]
    dg = np.array(dirs)[g]
    mT = dxg[dg].mean() if dg.sum() else float('nan')
    mF = dxg[~dg].mean() if (~dg).sum() else float('nan')
    print('我的带缝质量: rms %.2f px  max %.2f  共模 %+.3f  差模 %+.3f' % (
        float(np.sqrt((dxg ** 2).mean())), float(np.abs(dxg).max()),
        0.5 * (mT + mF), 0.5 * (mT - mF)))
    return all_bands


if __name__ == '__main__':
    # 与产线一致的加速内核（进程内）
    try:
        import fastcore
        fastcore.install(use_gpu=False, no_diag=True)
    except Exception as exc:
        print('[warn] fastcore unavailable:', exc)
    # 20260627（旧机器，项目默认参数）
    run_case(
        '20260627 旧机器 (项目默认参数, 70帧)',
        os.path.join(ROOT, 'testdata', '20260627', 'stitch'),
        os.path.join(ROOT, 'testdata', '20260627', 'calib', '4_final_calib.yaml'),
        os.path.join(ROOT, 'testdata', '20260627', 'calib', '3_final_calib.yaml'),
        os.path.join(ROOT, 'testdata', 'out', '20260627_oldstitcher_B_newcalib.tif'),
        d_step_x=847.965622809793, x_offset_false=2.908141050525, seam_inset=256,
        canvas_start=7906, canvas_width=21259, hold_pix=500,
        x_base_L=2461790, x_base_R=29057700, x_invert=629)

    # 20260903（新机器：hold=300, seam_inset=384, 新常数）
    run_case(
        '20260903 新机器 (hold=300, 8帧)',
        os.path.join(ROOT, 'testdata', '20260903', 'stitch'),
        os.path.join(ROOT, 'testdata', '20260903', 'calib', '4_final_calib.yaml'),
        os.path.join(ROOT, 'testdata', '20260903', 'calib', '5_final_calib.yaml'),
        os.path.join(ROOT, 'testdata', 'out', 'canvas_v7_newcalib_refine.png'),
        d_step_x=846.0527400801201, x_offset_false=5.2406, seam_inset=384,
        canvas_start=8000, canvas_width=21259, hold_pix=300,
        x_base_L=2461080, x_base_R=29191669, x_invert=788)
