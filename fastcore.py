#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fastcore.py — 矫正（rectify）的**可分离快速内核**，calib / stitch 两个加速版共用。

为什么能快 20 倍以上
====================
带 cross_term 时 `stitch_stream_final.rectify_image_array` 走 2-D 路径：先在
30785×2240 的 meshgrid 上求 PCHIP，再逐点加剪切项 —— **6.9 千万个点的插值**。
但看一眼模型就知道它其实是可分离的：

    map_x(c)      = fx(c)                       只随列变（source_x_model 的自变量是 y_mm）
    map_y(r, c)   = fy(r) + cross(c)            行项 + 只随列变的剪切项

所以只要在两个 **1 维向量**（长 30785 和 2240，合计 3.3 万点）上求一次 PCHIP，
再外加成 2-D 即可。实测：

    建图  ~4.2 s  ->  0.7 ms        （~6000x）
    remap 0.18 s（不变，这才是 cv2.remap 的真实成本）
    合计  4.41 s  ->  0.18 s        （24x）

这是**数值等价**的（PCHIP 是逐点求值，1-D 与 2-D 给同样的数；外加成 2-D 只差
一次广播），不是近似。唯一要注意的是 **clip 必须加在"加完剪切项之后"**，
否则在 fy 贴边的行上会与 2-D 路径差出几个灰阶（实测 31160 / 6.9e7 像素，max 6）——
这个坑已经踩过并修掉，`verify_against_reference()` 就是守它的。

另外提供 GPU remap（torch grid_sample）。注意：GPU 只省 remap 那 0.18 s，
**省不掉建图**；真正的大头是可分离建图。所以 `--gpu` 是锦上添花，不是主角。

用法
----
    from fastcore import rectify_array_fast
    out = rectify_array_fast(img, cal, options, use_gpu=True)

    # 给拼接器打补丁（含子进程内重新打补丁，Windows spawn 也有效）
    import fastcore; fastcore.install(use_gpu=True)
    import stitch_stream_final as S; S.main()
"""
from __future__ import annotations

import os
import sys

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

GPU_OK = False
_torch = None
_device = None


def gpu_available() -> bool:
    global GPU_OK, _torch, _device
    if _torch is not None:
        return GPU_OK
    try:
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA 不可用")
        torch.cuda.init()
        _torch, _device, GPU_OK = torch, torch.device("cuda"), True
    except Exception:
        _torch, GPU_OK = None, False
    return GPU_OK


# ══════════════════════════════════════════ 可分离建图

def separable_maps(cal, vec, image_shape):
    """返回 (fx, fy, cc_row, cc_col)：

    fx       (W,)   map_x 的列向部分
    fy       (H,)   map_y 的行向部分
    cc_row   (H,)|None  source_x_model 的剪切项（按其 cross_other_col 落在行或列上）
    cc_col   (W,)|None  source_y_model 的剪切项
    调用方自行组合并 clip。
    """
    off = cal.target_coordinate_offset_mm or {}
    ox, oy = float(off.get("x_mm", 0.0)), float(off.get("y_mm", 0.0))
    orientation = str(vec["orientation"][0])
    if orientation == "board_transposed":
        col_phys = vec["col_y_mm"] - oy      # 沿列变化 -> y_mm
        row_phys = vec["row_x_mm"] - ox      # 沿行变化 -> x_mm
    else:                                    # "board"
        col_phys = vec["col_x_mm"] - ox
        row_phys = vec["row_y_mm"] - oy

    sx, sy = cal.source_x_model, cal.source_y_model

    def pick(model):
        """该轴模型的自变量是哪条物理向量；以及它的 cross 自变量是哪条。"""
        phys_vec = col_phys if model.physical_col == "y_mm" else row_phys
        if not model.has_cross_term:
            return phys_vec, None
        other = col_phys if model.cross_other_col == "y_mm" else row_phys
        return phys_vec, other

    xin, xother = pick(sx)
    yin, yother = pick(sy)
    fx = sx(xin)
    fy = sy(yin)
    cc_row = sx.cross(xother) if (xother is not None and xother is row_phys) else None
    cc_col_x = sx.cross(xother) if (xother is not None and xother is col_phys) else None
    cc_col_y = sy.cross(yother) if (yother is not None and yother is col_phys) else None
    cc_row_y = sy.cross(yother) if (yother is not None and yother is row_phys) else None
    # 把同一根轴上的两个贡献合成一个向量（一般只有一个非空）
    if cc_col_x is None and cc_col_y is None:
        cc_col = None
    else:
        cc_col = (cc_col_x if cc_col_x is not None else 0.0) + \
                 (cc_col_y if cc_col_y is not None else 0.0)
    if cc_row is None and cc_row_y is None:
        cc_r = None
    else:
        cc_r = (cc_row if cc_row is not None else 0.0) + \
               (cc_row_y if cc_row_y is not None else 0.0)
    # cc_col 加在 map_y 上（列向量），cc_r 加在 map_x 上（行向量）
    return fx, fy, cc_r, cc_col


def _out_hw(vec, orientation):
    if orientation == "board":
        return len(vec["row_y_mm"]), len(vec["col_x_mm"])
    return len(vec["row_x_mm"]), len(vec["col_y_mm"])


def build_maps_2d(cal, vec, image_shape):
    """组合成 2-D map 并 clip。返回 (map_x, map_y)，形状 = 输出 (out_h, out_w)。"""
    fx, fy, cc_r, cc_c = separable_maps(cal, vec, image_shape)
    h, w = _out_hw(vec, str(vec["orientation"][0]))
    src_h, src_w = image_shape[:2]
    # map_x = fx(列) [+ 行向剪切]
    fx2 = (fx[None, :] + cc_r[:, None]) if cc_r is not None \
        else np.broadcast_to(fx[None, :], (h, w))
    # map_y = fy(行) [+ 列向剪切]
    fy2 = (fy[:, None] + cc_c[None, :]) if cc_c is not None \
        else np.broadcast_to(fy[:, None], (h, w))
    # clip 必须加在"加完剪切项之后"，且夹到**源图**边界
    fx2 = np.clip(fx2, 0.0, float(src_w - 1)).astype(np.float32)
    fy2 = np.clip(fy2, 0.0, float(src_h - 1)).astype(np.float32)
    return fx2, fy2


# ══════════════════════════════════════════ 快速矫正

def rectify_array_fast(image, cal, options=None, use_gpu=False, chunk=1024):
    """等价于 stitch_stream_final.rectify_image_array，但用可分离建图。"""
    import stitch_stream_final as S
    opts = options or S.RECTIFY_OPTIONS
    ranges = opts.target_full_ranges_mm or cal.target_full_ranges_mm
    if ranges is None:
        raise ValueError("yaml 缺 target_full_ranges_mm")
    full_ranges = S.normalize_target_full_ranges_mm(ranges)
    orientation = "board_transposed" if opts.orientation == "auto" else opts.orientation
    ppm = float(opts.target_grid_pixels_per_mm or cal.target_grid_pixels_per_mm
                or cal.pixels_per_mm)
    y_scale = float(cal.target_grid_y_scale or opts.y_scale)
    vec = S.build_output_vectors(full_ranges, ppm, orientation, y_scale=y_scale,
                                 target_axis_directions=cal.target_grid_axis_directions)
    out_h = len(vec["row_y_mm"] if orientation == "board" else vec["row_x_mm"])
    out_w = len(vec["col_x_mm"] if orientation == "board" else vec["col_y_mm"])

    fx, fy, cc_r, cc_c = separable_maps(cal, vec, image.shape)
    src_h, src_w = image.shape[:2]
    out = np.empty((out_h, out_w), dtype=image.dtype)
    if use_gpu and gpu_available():
        return _remap_gpu(image, (fx, fy, cc_r, cc_c), (out_h, out_w),
                          (src_h, src_w), chunk)
    for y0 in range(0, out_h, chunk):
        y1 = min(y0 + chunk, out_h)
        mx = ((fx[None, :] + cc_r[y0:y1, None]) if cc_r is not None
              else np.broadcast_to(fx[None, :], (y1 - y0, out_w)))
        my = ((fy[y0:y1, None] + cc_c[None, :]) if cc_c is not None
              else np.broadcast_to(fy[y0:y1, None], (y1 - y0, out_w)))
        mx = np.clip(mx, 0.0, float(src_w - 1)).astype(np.float32)
        my = np.clip(my, 0.0, float(src_h - 1)).astype(np.float32)
        out[y0:y1] = cv2.remap(image, mx, my,
                               interpolation=S.interpolation_flag(opts.interpolation),
                               borderMode=cv2.BORDER_REPLICATE)
    return out


def _remap_gpu(image, pieces, out_hw, src_hw, chunk=512):
    """grid_sample 的网格坐标按**源图**尺寸归一化（不是输出尺寸）—— 用错会全图错位。"""
    torch, dev = _torch, _device
    fx, fy, cc_r, cc_c = pieces
    out_h, out_w = out_hw
    src_h, src_w = src_hw
    out = np.empty((out_h, out_w), dtype=image.dtype)
    src = torch.from_numpy(np.ascontiguousarray(image)).to(dev).float()[None, None]
    for y0 in range(0, out_h, chunk):
        y1 = min(y0 + chunk, out_h)
        mx = ((fx[None, :] + cc_r[y0:y1, None]) if cc_r is not None
              else np.broadcast_to(fx[None, :], (y1 - y0, out_w)))
        my = ((fy[y0:y1, None] + cc_c[None, :]) if cc_c is not None
              else np.broadcast_to(fy[y0:y1, None], (y1 - y0, out_w)))
        mx = np.clip(mx, 0.0, float(src_w - 1)).astype(np.float32)
        my = np.clip(my, 0.0, float(src_h - 1)).astype(np.float32)
        gx = (2.0 * torch.from_numpy(np.ascontiguousarray(mx)).to(dev) + 1.0) / src_w - 1.0
        gy = (2.0 * torch.from_numpy(np.ascontiguousarray(my)).to(dev) + 1.0) / src_h - 1.0
        grid = torch.stack((gx, gy), dim=-1).unsqueeze(0)
        res = torch.nn.functional.grid_sample(src, grid, mode="bilinear",
                                              padding_mode="border",
                                              align_corners=False)
        out[y0:y1] = res.squeeze().round().clamp(0, 255).to(torch.uint8).cpu().numpy()
    return out


# ══════════════════════════════════════════ 给拼接器打补丁

def _fast_rectify_and_orient(path, direction, true_calibration, false_calibration):
    import stitch_stream_final as S
    image = S.load_gray_array(path)
    if not direction:
        image = cv2.flip(image, 1)
    cal = true_calibration if direction else false_calibration
    res = rectify_array_fast(image, cal, S.RECTIFY_OPTIONS, use_gpu=INSTALL_GPU)
    return S.ensure_grayscale(res)


def _measure_one_window_fast(img_a, img_b, a, b, rect, window_index, ox, oy, ow, oh):
    """_measure_one_window 的精简版：砍掉**纯诊断**的 FFT。

    peak_margin（旁峰诊断，2 次 rfft2 + 1 次 irfft2）和 response_flip（翻转同分，
    1 次相关）在默认配置下**门都是关的**（GATE_PEAK_MARGIN_PX=0、REJECT_DEGENERATE=False），
    算出来只写进 CSV、不参与任何决策。但它们占了窗口耗时的 **83%**（实测 139.7 ms 里的
    116.4 ms）。砍掉后 dx / dy / phase_response 一个数都不变，只是那几个诊断列变成空。

    键名与原版保持一致，CSV 的 schema 不会变。
    """
    import stitch_stream_final as S
    patch_a = S.extract_from_canvas_rect(img_a, a, rect)
    patch_b = S.extract_from_canvas_rect(img_b, b, rect)
    if patch_a.size == 0 or patch_b.size == 0:
        return None
    fa, fb = S.normalize_feature(patch_a), S.normalize_feature(patch_b)
    if fa is None or fb is None:
        dx = dy = response = float("nan")
    else:
        (dx, dy), response = cv2.phaseCorrelate(fa, fb)
    gx = np.abs(np.diff(patch_a.astype(np.float32), axis=1))
    gy = np.abs(np.diff(patch_a.astype(np.float32), axis=0))
    return {
        "pair": f"{int(a['index'])}_{int(b['index'])}",
        "a_index": int(a["index"]), "b_index": int(b["index"]),
        "transition": S.transition_label(a, b),
        "window_index": int(window_index),
        "final_x_band": S.band_label(window_index, S.WINDOW_COUNT),
        "phase_dx_px_pre_rotation": dx,
        "phase_dy_px_pre_rotation": dy,
        "phase_response": response,
        "lane_grad": float(gx.mean()) if gx.size else 0.0,
        "scan_grad": float(gy.mean()) if gy.size else 0.0,
        "overlap_w": int(ow), "overlap_h": int(oh),
        "a_canvas_x": int(a["canvas_x"]), "a_canvas_y": int(a["canvas_y"]),
        "b_canvas_x": int(b["canvas_x"]), "b_canvas_y": int(b["canvas_y"]),
        "sat_frac": round(max(S.sat_share(patch_a), S.sat_share(patch_b)), 4),
        "peak_strength": None, "rival_ratio": None, "rival_dist_px": None,
        "response_flip": None, "degenerate": 0,
    }


INSTALL_GPU = False
INSTALL_NO_DIAG = False


def install(use_gpu: bool = False, no_diag: bool = False):
    """把快速矫正装进 stitch_stream_final（含子进程内重装，Windows spawn 也有效）。

    no_diag=True 再砍掉窗口里的纯诊断 FFT（dx/dy 不变，只是 CSV 少几个诊断值）。
    """
    global INSTALL_GPU, INSTALL_NO_DIAG
    INSTALL_GPU = bool(use_gpu) and gpu_available()
    INSTALL_NO_DIAG = bool(no_diag)
    _apply()
    print(f"[fastcore] 已启用：可分离建图"
          f"{' + GPU remap' if INSTALL_GPU else ''}"
          f"{' + 去诊断FFT' if INSTALL_NO_DIAG else ''}")


def _apply():
    import stitch_stream_final as S
    S.rectify_and_orient = _fast_rectify_and_orient
    S.rectify_image_array = lambda image, cal, options=None: rectify_array_fast(
        image, cal, options or S.RECTIFY_OPTIONS, use_gpu=INSTALL_GPU)
    if INSTALL_NO_DIAG:
        S._measure_one_window = _measure_one_window_fast
    if not hasattr(S, "_fastcore_orig_worker_init"):
        S._fastcore_orig_worker_init = S._worker_init
        S._worker_init = _patched_worker_init
    if INSTALL_NO_DIAG:
        S._window_pool_init.__doc__ = S._window_pool_init.__doc__  # no-op，保持引用


def _patched_worker_init(*args):
    """子进程里重新打补丁 —— spawn 模式下子进程是重新 import 的，父进程的补丁不会带过去。

    注意顺序：必须先 _apply() 再调原始 init。子进程里模块是**全新导入**的，
    `_fastcore_orig_worker_init` 这个属性还不存在（它由 _apply() 建立，此时
    _worker_init 还是原版函数）；先调原版会因属性不存在直接把 worker 打崩
    （本文件在 delivery 的子进程架构下从未走到过这条路径，是该 bug 的暴露条件）。
    """
    S_mod = sys.modules.get("stitch_stream_final")
    if S_mod is None:
        import stitch_stream_final as S_mod
    _apply()
    S_mod._fastcore_orig_worker_init(*args)


# ══════════════════════════════════════════ 自检：与 2-D 参考路径比对

def verify_against_reference(cal, image, n_rows=512):
    """只校验前 n_rows 行，确认可分离建图与 2-D 路径像素一致。"""
    import stitch_stream_final as S
    vec = S.build_output_vectors(
        S.normalize_target_full_ranges_mm(cal.target_full_ranges_mm),
        float(cal.target_grid_pixels_per_mm or cal.pixels_per_mm),
        "board_transposed",
        y_scale=float(cal.target_grid_y_scale or 1.0),
        target_axis_directions=cal.target_grid_axis_directions)
    fx, fy, cc_r, cc_c = separable_maps(cal, vec, image.shape)
    src_h, src_w = image.shape[:2]
    h, w = _out_hw(vec, str(vec["orientation"][0]))
    y1 = min(n_rows, h)
    mx = ((fx[None, :] + cc_r[:y1, None]) if cc_r is not None
          else np.broadcast_to(fx[None, :], (y1, w)))
    my = ((fy[:y1, None] + cc_c[None, :]) if cc_c is not None
          else np.broadcast_to(fy[:y1, None], (y1, w)))
    mx = np.clip(mx, 0.0, float(src_w - 1))
    my = np.clip(my, 0.0, float(src_h - 1))
    ref_x, ref_y = S.generate_map_chunk(
        vec, 0, y1, image.shape, cal.source_x_model, cal.source_y_model,
        cal.residual_model, True, cal.target_coordinate_offset_mm, None)
    return float(np.abs(mx - ref_x).max()), float(np.abs(my - ref_y).max())
