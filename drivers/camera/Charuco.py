

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线阵 ChArUco 快速校正（优化版）。对外接口：rectify_charuco_image()。
优化点：linear 插值 + 全图一次性 remap，避免分块循环开销。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import cv2
import numpy as np
import yaml
import tifffile
# 免 scipy：改用本文件内的纯 numpy PCHIP（_Pchip）

PathLike = Union[str, Path]


# ---------- 图像工具 ----------

def load_image(path: PathLike) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"无法读取图像: {path}")
    return img


def to_grayscale(image: np.ndarray) -> np.ndarray:
    img = np.asarray(image)
    if img.ndim == 2:
        return img
    if img.ndim == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 3 and img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    raise ValueError(f"不支持的图像 shape: {img.shape}")


def save_gray_tiff(path: PathLike, image: np.ndarray, dpi: int = 300) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    gray = to_grayscale(image)
    tifffile.imwrite(
        str(out), gray,
        resolution=(float(dpi), float(dpi)),
        resolutionunit="INCH",
        bigtiff=gray.nbytes >= 4 * 1024 ** 3,
    )
    return out


# ---------- 标定模型（仅加载 + 映射） ----------

# ============================================================================
# 纯 numpy 的 PCHIP（Fritsch-Carlson 单调三次插值）
# 与 scipy.interpolate.PchipInterpolator 同一算法，实测最大偏差 < 1e-11，
# 现场机因此不必安装 scipy。
# ============================================================================

def _pchip_slopes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    n = len(x)
    h = np.diff(x)
    delta = np.diff(y) / h
    m = np.zeros(n, dtype=np.float64)
    if n == 2:
        m[:] = delta[0]
        return m
    w1 = 2.0 * h[1:] + h[:-1]
    w2 = h[1:] + 2.0 * h[:-1]
    prod = delta[:-1] * delta[1:]
    m_int = np.where(prod <= 0.0, 0.0, (w1 + w2) / (w1 / delta[:-1] + w2 / delta[1:]))
    m_int = np.where(np.isfinite(m_int), m_int, 0.0)
    m[1:-1] = m_int
    m[0] = delta[0]
    m[-1] = delta[-1]
    if n > 2:
        m0 = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (h[0] + h[1])
        mn = ((2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]) / (h[-1] + h[-2])
        if m0 * delta[0] <= 0.0:
            m0 = 0.0
        elif delta[0] * delta[1] <= 0.0 and abs(m0) > abs(3.0 * delta[0]):
            m0 = 3.0 * delta[0]
        if mn * delta[-1] <= 0.0:
            mn = 0.0
        elif delta[-2] * delta[-1] <= 0.0 and abs(mn) > abs(3.0 * delta[-1]):
            mn = 3.0 * delta[-1]
        m[0], m[-1] = m0, mn
    return m


def _pchip_eval(x: np.ndarray, y: np.ndarray, m: np.ndarray, xq: np.ndarray) -> np.ndarray:
    xq = np.asarray(xq, dtype=np.float64)
    idx = np.clip(np.searchsorted(x, xq, side="right") - 1, 0, len(x) - 2)
    h = x[idx + 1] - x[idx]
    t = (xq - x[idx]) / h
    t2, t3 = t * t, t * t * t
    return ((2.0 * t3 - 3.0 * t2 + 1.0) * y[idx]
            + (t3 - 2.0 * t2 + t) * h * m[idx]
            + (-2.0 * t3 + 3.0 * t2) * y[idx + 1]
            + (t3 - t2) * h * m[idx + 1])


class _Pchip:
    """PchipInterpolator 的免 scipy 替身（只用到 __call__）。"""

    def __init__(self, x, y, extrapolate=False):
        self.x = np.asarray(x, dtype=np.float64)
        self.y = np.asarray(y, dtype=np.float64)
        self.m = _pchip_slopes(self.x, self.y)

    def __call__(self, xq):
        return _pchip_eval(self.x, self.y, self.m, xq)


@dataclass
class RobustAxisModel:
    physical_col: str
    pixel_col: str
    knots_physical_mm: np.ndarray
    knots_source_px: np.ndarray
    left_slope_px_per_mm: float
    right_slope_px_per_mm: float
    edge_fit_points: int
    # 跨轴剪切项（schema v7）：本轴像素对**另一根物理轴**的依赖 = 传感器线与运动方向夹角。
    # 正/反两份 yaml 各自加载，所以天然支持"双向不同角度"，不需要池化。
    cross_other_col: Optional[str] = None
    cross_reference_mm: float = 0.0
    cross_coefficients_px: Tuple[float, ...] = ()

    def __post_init__(self) -> None:
        self.knots_physical_mm = np.asarray(self.knots_physical_mm, dtype=np.float64)
        self.knots_source_px = np.asarray(self.knots_source_px, dtype=np.float64)
        self._pchip = _Pchip(self.knots_physical_mm, self.knots_source_px)

        increasing = self.knots_source_px[-1] >= self.knots_source_px[0]
        px_sorted = np.maximum.accumulate(self.knots_source_px) if increasing else np.minimum.accumulate(self.knots_source_px)[::-1]
        phys_sorted = self.knots_physical_mm if increasing else self.knots_physical_mm[::-1]
        unique_px, unique_index = np.unique(px_sorted, return_index=True)
        self._inverse_px_sorted = unique_px
        self._inverse_phys_sorted = phys_sorted[unique_index]
        self._inverse_pchip = _Pchip(unique_px, phys_sorted[unique_index])
        self.cross_coefficients_px = tuple(float(v) for v in self.cross_coefficients_px)

    @property
    def phys_min(self) -> float:
        return float(self.knots_physical_mm[0])

    @property
    def phys_max(self) -> float:
        return float(self.knots_physical_mm[-1])

    @property
    def px_at_phys_min(self) -> float:
        return float(self.knots_source_px[0])

    @property
    def px_at_phys_max(self) -> float:
        return float(self.knots_source_px[-1])

    def __call__(self, physical_mm: np.ndarray) -> np.ndarray:
        x = np.asarray(physical_mm, dtype=np.float64)
        out = np.empty_like(x)
        left, right = x < self.phys_min, x > self.phys_max
        mid = ~(left | right)
        if np.any(mid):
            out[mid] = self._pchip(x[mid])
        if np.any(left):
            out[left] = self.px_at_phys_min + self.left_slope_px_per_mm * (x[left] - self.phys_min)
        if np.any(right):
            out[right] = self.px_at_phys_max + self.right_slope_px_per_mm * (x[right] - self.phys_max)
        return out

    def inverse(self, source_px: np.ndarray) -> np.ndarray:
        y = np.asarray(source_px, dtype=np.float64)
        out = np.empty_like(y)
        px_lo, px_hi = float(self._inverse_px_sorted[0]), float(self._inverse_px_sorted[-1])
        phys_lo, phys_hi = float(self._inverse_phys_sorted[0]), float(self._inverse_phys_sorted[-1])
        slope_lo = self.left_slope_px_per_mm if abs(phys_lo - self.phys_min) <= abs(phys_lo - self.phys_max) else self.right_slope_px_per_mm
        slope_hi = self.left_slope_px_per_mm if abs(phys_hi - self.phys_min) <= abs(phys_hi - self.phys_max) else self.right_slope_px_per_mm
        low, high = y < px_lo, y > px_hi
        mid = ~(low | high)
        if np.any(mid):
            out[mid] = self._inverse_pchip(y[mid])
        if np.any(low):
            out[low] = phys_lo + (y[low] - px_lo) / slope_lo
        if np.any(high):
            out[high] = phys_hi + (y[high] - px_hi) / slope_hi
        return out

    @property
    def has_cross_term(self) -> bool:
        return bool(self.cross_coefficients_px)

    def cross(self, other_mm: np.ndarray) -> np.ndarray:
        """另一根轴带来的附加像素偏移；没有剪切项时返回 0。

        form: sum_k coefficients_px[k-1] * (other_mm - reference_mm)**k
        """
        arr = np.asarray(other_mm, dtype=np.float64)
        if not self.cross_coefficients_px:
            return np.zeros_like(arr)
        delta = arr - float(self.cross_reference_mm)
        out = np.zeros_like(arr)
        for power, coef in enumerate(self.cross_coefficients_px, start=1):
            out = out + float(coef) * delta ** power
        return out

    @classmethod
    def from_yaml(cls, data: Dict) -> "RobustAxisModel":
        ct = data.get("cross_term") or {}
        return cls(
            physical_col=str(data["physical_col"]),
            pixel_col=str(data["pixel_col"]),
            knots_physical_mm=np.asarray(data["knots_physical_mm"], dtype=np.float64),
            knots_source_px=np.asarray(data["knots_source_px"], dtype=np.float64),
            left_slope_px_per_mm=float(data["left_slope_px_per_mm"]),
            right_slope_px_per_mm=float(data["right_slope_px_per_mm"]),
            edge_fit_points=int(data["edge_fit_points"]),
            cross_other_col=(str(ct["other_col"]) if ct.get("other_col") else None),
            cross_reference_mm=float(ct.get("reference_mm", 0.0)),
            cross_coefficients_px=tuple(float(v) for v in (ct.get("coefficients_px") or ())),
        )


@dataclass
class RBFResidualModel:
    grid_x_mm: np.ndarray
    grid_y_mm: np.ndarray
    correction_x_grid_px: np.ndarray
    correction_y_grid_px: np.ndarray

    def __post_init__(self) -> None:
        self.grid_x_mm = np.asarray(self.grid_x_mm, dtype=np.float64)
        self.grid_y_mm = np.asarray(self.grid_y_mm, dtype=np.float64)
        self.correction_x_grid_px = np.asarray(self.correction_x_grid_px, dtype=np.float32)
        self.correction_y_grid_px = np.asarray(self.correction_y_grid_px, dtype=np.float32)

    def __call__(self, points_mm: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        pts = np.asarray(points_mm, dtype=np.float64)
        step_x = float(self.grid_x_mm[1] - self.grid_x_mm[0])
        step_y = float(self.grid_y_mm[1] - self.grid_y_mm[0])
        map_x_all = ((pts[:, 0] - self.grid_x_mm[0]) / step_x).astype(np.float32)
        map_y_all = ((pts[:, 1] - self.grid_y_mm[0]) / step_y).astype(np.float32)
        cx = np.zeros(len(pts), dtype=np.float64)
        cy = np.zeros(len(pts), dtype=np.float64)
        batch = 30000
        for s in range(0, len(pts), batch):
            e = min(s + batch, len(pts))
            mx = map_x_all[s:e].reshape(-1, 1)
            my = map_y_all[s:e].reshape(-1, 1)
            cx[s:e] = cv2.remap(self.correction_x_grid_px, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).ravel()
            cy[s:e] = cv2.remap(self.correction_y_grid_px, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).ravel()
        return cx, cy

    @classmethod
    def from_yaml(cls, data: Dict) -> "RBFResidualModel":
        return cls(
            grid_x_mm=np.asarray(data["grid_x_mm"], dtype=np.float64),
            grid_y_mm=np.asarray(data["grid_y_mm"], dtype=np.float64),
            correction_x_grid_px=np.asarray(data["correction_x_grid_px"], dtype=np.float32),
            correction_y_grid_px=np.asarray(data["correction_y_grid_px"], dtype=np.float32),
        )


@dataclass
class Calibration:
    pixels_per_mm: float
    source_x_model: RobustAxisModel
    source_y_model: RobustAxisModel
    residual_model: Optional[RBFResidualModel]
    output_dpi: int
    y_scale: float = 1.0
    # output_defaults.target_grid, when the YAML is one of a registered pair.
    # Pins the output grid instead of inferring it per image, and carries the
    # registration offset that puts the two scan directions on ONE grid. Without
    # it the two directions land on grids of slightly different size (2238x30781
    # vs 2239x30784) and the difference shows up as a ~2 px differential stretch
    # across the canvas - the same order as the seam error being chased.
    target_grid: Optional[Dict[str, object]] = None

    @classmethod
    def from_yaml(cls, path: PathLike, y_scale: float = 1.0) -> "Calibration":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        board = data.get("board", data)
        square_mm = float(board.get("square_size_mm", 20.0))
        px_per_sq = float(board.get("pixels_per_square", 236.18))
        residual = None
        rc = data.get("residual_correction") or data.get("residual_model")
        if isinstance(rc, dict) and rc.get("type") == "rbf_tapered_grid":
            residual = RBFResidualModel.from_yaml(rc)
        if int(data.get("schema_version", 1)) >= 2:
            sx = RobustAxisModel.from_yaml(data["source_x_axis_model"])
            sy = RobustAxisModel.from_yaml(data["source_y_axis_model"])
            dpi = int(data.get("output_defaults", {}).get("dpi", 300))
        else:
            sx = RobustAxisModel.from_yaml(data["source_x_model"])
            sy = RobustAxisModel.from_yaml(data["source_y_model"])
            dpi = int(data.get("output_defaults", {}).get("dpi", 300))
        tg = data.get("output_defaults", {}).get("target_grid")
        if isinstance(tg, dict) and tg.get("full_ranges_mm"):
            return cls(px_per_sq / square_mm, sx, sy, residual, dpi, y_scale, tg)
        return cls(px_per_sq / square_mm, sx, sy, residual, dpi, y_scale)


# ---------- 校正核心 ----------

_INTERP = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR, "cubic": cv2.INTER_CUBIC, "lanczos": cv2.INTER_LANCZOS4}


def _infer_ranges(shape, sx: RobustAxisModel, sy: RobustAxisModel) -> Dict[str, float]:
    h, w = shape[:2]
    xs = float(sx.inverse(np.array([-0.5]))[0])
    xe = float(sx.inverse(np.array([w - 0.5]))[0])
    ys = float(sy.inverse(np.array([-0.5]))[0])
    ye = float(sy.inverse(np.array([h - 0.5]))[0])
    return {"sx0": xs, "sx1": xe, "sy0": ys, "sy1": ye}


def _target_ranges(tg: Dict[str, object]) -> Dict[str, float]:
    """Output grid pinned by `output_defaults.target_grid`, replacing _infer_ranges.

    Two conventions, both settled by measurement (two independent frame pairs,
    7/7 windows matching at phase responses 0.33-0.48; every other combination
    fails to correlate at all, so neither is a tuning knob):

    * `coordinate_offset_mm` is SUBTRACTED from the grid. That is the same thing
      as subtracting it from the board coordinates fed to the axis models, which
      is how the offline pipeline writes it: `_step_vec` produces an evenly
      spaced vector, so a common shift of the endpoints changes neither the
      sample count nor the spacing.
    * `axis_directions` is read REVERSED here - the flag that is False marks the
      ASCENDING axis. It is read literally in the offline pipeline, and the two
      readings are both right: the two frames differ by the 180 degree rotation
      that the legacy stitch flow applies to the forward direction. This function
      stays in the legacy frame, so it reverses. Add that rotation and it would
      have to read literally instead.

    `sx` is fed the column axis and its physical_col is y_mm; `sy` is fed the row
    axis and its physical_col is x_mm.
    """
    fr = tg["full_ranges_mm"]
    dr = tg.get("axis_directions") or {"x_mm": True, "y_mm": False}
    off = tg.get("coordinate_offset_mm") or {"x_mm": 0.0, "y_mm": 0.0}
    ox = -float(off.get("x_mm", 0.0))
    oy = -float(off.get("y_mm", 0.0))

    y0, y1 = float(fr["y_mm_min"]) + oy, float(fr["y_mm_max"]) + oy
    x0, x1 = float(fr["x_mm_min"]) + ox, float(fr["x_mm_max"]) + ox
    sx0, sx1 = (y1, y0) if dr.get("y_mm", False) else (y0, y1)
    sy0, sy1 = (x1, x0) if dr.get("x_mm", True) else (x0, x1)
    return {"sx0": sx0, "sx1": sx1, "sy0": sy0, "sy1": sy1}


def _step_vec(start: float, end: float, ppm: float) -> np.ndarray:
    n = max(1, int(math.ceil(abs(end - start) * ppm)))
    sign = 1.0 if end >= start else -1.0
    return float(start) + sign * np.arange(n + 1, dtype=np.float64) / ppm


def _board_coords_2d(
    col_phys: np.ndarray,
    row_chunk: np.ndarray,
    bx_from_col: bool,
) -> Tuple[np.ndarray, np.ndarray]:
    """用广播构造板面坐标网格，避免每块 meshgrid 分配。"""
    col_2d = col_phys[np.newaxis, :]
    row_2d = row_chunk[:, np.newaxis]
    if bx_from_col:
        return col_2d, row_2d
    return row_2d, col_2d


def _build_chunk_remap_maps(
    sx: RobustAxisModel,
    sy: RobustAxisModel,
    col_phys: np.ndarray,
    row_chunk: np.ndarray,
    bx_from_col: bool,
    map_x_col: Optional[np.ndarray],
    rbf: Optional[RBFResidualModel],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成 remap 用的 map_x / map_y (float32)。

    常见 swapped 标定下 map_x 只随列变化、map_y 只随行变化，可 1D 求值再广播。
    """
    chunk_h = len(row_chunk)
    out_w = len(col_phys)
    bx, by = _board_coords_2d(col_phys, row_chunk, bx_from_col)

    if map_x_col is not None:
        map_x = np.broadcast_to(map_x_col, (chunk_h, out_w)).copy()
    elif sx.physical_col == "x_mm":
        map_x = np.broadcast_to(sx(row_chunk).astype(np.float32)[:, np.newaxis], (chunk_h, out_w)).copy()
    else:
        map_x = np.broadcast_to(sx(col_phys).astype(np.float32)[np.newaxis, :], (chunk_h, out_w)).copy()

    if sy.physical_col == "y_mm":
        if bx_from_col:
            map_y = np.broadcast_to(sy(row_chunk).astype(np.float32)[:, np.newaxis], (chunk_h, out_w)).copy()
        else:
            map_y = np.broadcast_to(sy(col_phys).astype(np.float32)[np.newaxis, :], (chunk_h, out_w)).copy()
    elif bx_from_col:
        map_y = np.broadcast_to(sy(col_phys).astype(np.float32)[np.newaxis, :], (chunk_h, out_w)).copy()
    else:
        map_y = np.broadcast_to(sy(row_chunk).astype(np.float32)[:, np.newaxis], (chunk_h, out_w)).copy()

    # 跨轴剪切项（角度）：用**另一根轴**的物理坐标求值后加到对应 map 上。
    #
    # 必须按**可分离**做：先对 1D 向量求 cross，再广播到 2D。
    # 若直接 broadcast_arrays 成 (chunk_h, out_w) 再逐元素做幂，每个 chunk 都是
    # 百万级 2D pow —— 实测整机 70 帧从 364s 涨到 786s（慢 2.2 倍）。
    #
    # 轴向约定（与本函数里 sx/sy 的求值一致）：row_chunk 对应 x_mm，col_phys 对应 y_mm。
    if sx.has_cross_term or sy.has_cross_term:
        if sx.has_cross_term:
            other_1d = row_chunk if sx.cross_other_col == "x_mm" else col_phys
            cx = sx.cross(other_1d).astype(np.float32)
            map_x += (cx[:, np.newaxis] if sx.cross_other_col == "x_mm"
                      else cx[np.newaxis, :])
        if sy.has_cross_term:
            other_1d = row_chunk if sy.cross_other_col == "x_mm" else col_phys
            cy = sy.cross(other_1d).astype(np.float32)
            map_y += (cy[:, np.newaxis] if sy.cross_other_col == "x_mm"
                      else cy[np.newaxis, :])

    if rbf is not None:
        bx_full, by_full = np.broadcast_arrays(bx, by)
        cx, cy = rbf(np.column_stack([bx_full.ravel(), by_full.ravel()]))
        map_x += cx.reshape(chunk_h, out_w).astype(np.float32)
        map_y += cy.reshape(chunk_h, out_w).astype(np.float32)

    return map_x, map_y


def _remap_full(
    image: np.ndarray,
    calib: Calibration,
    interpolation: str = "linear",
    clip: bool = True,
) -> np.ndarray:
    """全图一次性 remap，避免分块循环开销。"""
    if calib.target_grid is not None:
        ranges = _target_ranges(calib.target_grid)
        ppm = float(calib.target_grid.get("pixels_per_mm", calib.pixels_per_mm))
        y_scale = float(calib.target_grid.get("y_scale", calib.y_scale))
    else:
        ranges = _infer_ranges(image.shape, calib.source_x_model, calib.source_y_model)
        ppm, y_scale = calib.pixels_per_mm, calib.y_scale
    col_phys = _step_vec(ranges["sx0"], ranges["sx1"], ppm * y_scale)
    row_phys = _step_vec(ranges["sy0"], ranges["sy1"], ppm)
    out_h, out_w = len(row_phys), len(col_phys)
    sx, sy = calib.source_x_model, calib.source_y_model
    rbf = calib.residual_model
    interp = _INTERP[interpolation]

    if image.ndim == 2:
        output = np.empty((out_h, out_w), dtype=image.dtype)
    else:
        output = np.empty((out_h, out_w, image.shape[2]), dtype=image.dtype)
    h, w = image.shape[:2]

    bx_from_col = sx.physical_col == "x_mm"
    sx_uses_col = (sx.physical_col == "x_mm" and bx_from_col) or (sx.physical_col == "y_mm" and not bx_from_col)
    map_x_col = sx(col_phys).astype(np.float32)[np.newaxis, :] if sx_uses_col else None
    w_max, h_max = float(w - 1), float(h - 1)

    # 一次性构建全图 map
    map_x, map_y = _build_chunk_remap_maps(
        sx, sy, col_phys, row_phys, bx_from_col, map_x_col, rbf,
    )
    if clip:
        np.clip(map_x, 0.0, w_max, out=map_x)
        np.clip(map_y, 0.0, h_max, out=map_y)
    output = cv2.remap(
        image, map_x, map_y, interp, borderMode=cv2.BORDER_REPLICATE,
    )
    return output


def rectify_charuco_image(
    yaml_path: PathLike,
    image: Union[PathLike, np.ndarray],
    interpolation: str = "linear",
    chunk_rows: int = 256,
    rotate_ccw_90: bool = True,
    y_scale: float = 1.0,
) -> np.ndarray:
    calib = Calibration.from_yaml(yaml_path, y_scale=y_scale)
    img = load_image(image) if isinstance(image, (str, Path)) else np.asarray(image)
    out = _remap_full(img, calib, interpolation=interpolation)
    if rotate_ccw_90:
        out = cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return to_grayscale(out)

def calibration(img, params):
    out = _remap_full(img, params, interpolation="linear")
    out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
    return to_grayscale(out)

def calibration_origin(img, params):
    """Read YAML configuration and correct image

    :param img: Original image (BGR)
    :param params: Calibration parameters
    :return: PIL.Image object (RGB format)
    :raises: ValueError, KeyError
    :note::
    """

    # 2. Read image
    if img is None:
        raise ValueError("Cannot read image, please check format")

    h, w = img.shape[:2]

    # 3. Check if calibration is enabled
    if not params or not params.get('enable', False):
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # 4. Extract parameters and convert to numpy arrays
    try:
        mtx1 = np.array(params['mtx1'])
        dist1 = np.array(params['dist1'])
        mode = params.get('mode', 'resize')
    except KeyError as e:
        raise KeyError(f"Missing necessary parameters in YAML file: {e}")

    # 5. Step 1: Remove lens distortion (Undistort)
    img_undistort = cv2.undistort(img, mtx1, dist1, None, mtx1)

    # 6. Step 2: Geometric transformation based on mode
    final_img = None
    if mode == 'resize':
        final_img = img_undistort
    elif mode == 'warp':
        # --- Warp mode (Perspective transform) ---
        if params['H_board'] is None:
            final_img = img_undistort
        else:
            H = np.array(params['H_board'])

            # [Key Step] Automatically calculate boundaries after transformation
            # Direct warpPerspective may cause image disappearance due to negative coordinates
            # 1. Get original four corners
            corners = np.array([
                [0, 0],
                [w, 0],
                [w, h],
                [0, h]
            ], dtype=np.float32).reshape(-1, 1, 2)

            # 2. Calculate transformed corner positions
            new_corners = cv2.perspectiveTransform(corners, H)

            # 3. Get bounding box of transformed image (x_min, x_max, y_min, y_max)
            [x_min, y_min] = np.int32(new_corners.min(axis=0).ravel() - 0.5)
            [x_max, y_max] = np.int32(new_corners.max(axis=0).ravel() + 0.5)

            # 4. Calculate translation matrix to move image back to positive coordinate area
            translation_dist = [-x_min, -y_min]
            H_translation = np.array([
                [1, 0, translation_dist[0]],
                [0, 1, translation_dist[1]],
                [0, 0, 1]
            ])

            # 5. Combine transformation matrices
            full_H = H_translation.dot(H)

            # 6. Calculate new image size
            new_w = x_max - x_min
            new_h = y_max - y_min

            # Execute perspective transform
            final_img = cv2.warpPerspective(img_undistort, full_H, (new_w, new_h))
    else:
        final_img = img_undistort
    return final_img
