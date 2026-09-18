#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
stitch_stream_standalone_v2.py — 流式拼接 v2，按 stitch0905.txt 的结论加固

来历：底子是 comate/stitch_stream_standalone_fast.py（它比 treawork/standalone 那份多了
schema 7 的 cross_term、--x-gain、带 cross_term 时自动归零在线 skew、--seam-inset）。
treawork 那份全文 0 处 cross_term，喂它 v7 yaml 会把剪切**静默丢弃**，所以 v2 只能以
comate 那份为底，不能原地改老文件。

从 stitch0905（vsDriverbox 全链路分析，已数值闭环）落到本文件的改动：

坑2 过曝饱和骗度量：饱和块本身梯度为 0，但它的硬边界会造出假强边。现在窗口特征里
    把邻域贴顶(>=SAT_THRESH)的梯度掩掉，并报窗内饱和比例 sat_frac；超限的窗不参与中位数
    (--max-sat-frac)。
坑3/5 周期图案假峰、必须报峰高：|phase|<=MAX_ABS_PHASE 已拒掉大位移假峰，但周期小于该
    限制的花型仍可能在许可区内选到旁峰。现在额外算相关面，报 peak_margin_px（最近一个
    高度>=主峰70%的旁峰距离）；默认只诊断不改数值，要拒绝加 --gate-peak-margin。
坑4 明暗包络左右对称时“翻转同分”是退化：每窗多做一次列翻转相关，同分则标 degenerate=1
    （--reject-degenerate 才参与拒绝）。
坑1 首帧 MSP=0 是真实位置（现场版靠 alignment 把 2906px 补回，代回映射验过 img0 与标准
    正向帧落同一坐标系）。本文件**没有这个 bug**：`infer_standard_msp_causal` 的 repair 与
    special_offset 两项加起来正好抵消（raw_y + special_offset = -H + 0.5），等价于现场版那个
    补正。实证：若首帧真被放错 2907px，frame1 的 dy 应该是 ~2907px，实测是 -2.1px。
    四个现场常数（左/右基准、拼接偏移、画布开始）在本程序里**不需要**：它们是"固定画布 +
    裁剪"那一揽子约定的原点量，而本程序用逐帧编码器值 + 自适应画布。已用数据核过两者自洽：
    (base_R-base_L)/K_Coef = 31570.99 px vs 实测两方向 MSP 中位差 31571.04 px（差 0.05px）。
    反面对照（试验已删）：若把折返点当唯一位置、丢弃逐帧 MSP，首反向那条**真实过冲 82px**
    会被抹掉，导致相邻两对的窗口测量全部超出搜索限制而失效。
坑6/7 硬编码像素数当物理量：834 是单帧步进 70.626mm、canvas_start 是像素。本文件的
    K_COEF_NOMINAL 原来硬编码 300dpi；--encoder-scale yaml-nominal 改为从 yaml 自己的
    output_defaults.dpi 推 K_Coef。

要记牢的几何事实（stitch0905，下次不要重新推）：原始帧 27800 行=横移轴 X(2606.46mm,
10.666 行/mm)、2048 列=传感器轴=走纸方向 Y(189.65mm, 10.799 px/mm)；标定把它重采样到
11.811 px/mm。所以“300dpi”在原始图上是假的（两轴都假且不方），把它做真是标定的工作。
左右基准=两个折返点(2461080/29191669 原始单位, 除 K_Coef)；拼接偏移 788 = 行程 31570.7px
- 图宽 30785px；画布开始 8000 是像素，合法区间 [2906, 8737]；单帧步进 834px=70.626mm，
可用高度 2240-500=1740px，重叠 906px=76.7mm(52%)。

Streaming (place-on-arrival) stitching for the line-scan machine, in ONE file.
算法与摆放决策与上游一致; 加速(可分离建图 / shm 零拷贝流水线 / 窗口测量进程池 / GPU warp)
只并行化计算, 不改任何数值路径。70 帧实测 302.4s -> 72.4s (4.2x), 金标准对照决策逐位一致。

Inputs
------
    --data-dir    the acquisition folder: the .tif frames plus the LocalImageInfos.json
                  the acquisition software writes next to them (images may sit in the
                  folder itself or in an `Images/` subfolder). The output of
                  enhance_standalone.py (brightness+sharpness corrected strips) can be
                  used directly.
    --true-yaml   ChArUco calibration for Direction=True
    --false-yaml  ChArUco calibration for Direction=False (hflip first)
    --workers N   0 = original serial path; >0 = accelerated pipeline (recommended 8)

    conda run -n digitalpainter python stitch_stream_standalone_fast.py ^
        --data-dir <acquisition or enhance_standalone output> ^
        --true-yaml <4_registered_calib.yaml> ^
        --false-yaml <3_hflip_registered_calib.yaml> ^
        --output-dir <out> --workers 8

Acceleration flags
------------------
    --workers N            rectify/window parallelism (default 0 = serial, original)
    --rectify-backend      shm (default; shared-memory zero-copy pipeline) | process | thread
    --gpu-warp / --no-gpu-warp   torch grid_sample warp on the GPU (default on when
                           torch+CUDA is available; canvas pixels may differ from the
                           CPU warp by <=3/255 interpolation rounding — placement
                           decisions are made BEFORE the warp and are unaffected)
    env TREAWORK_PROFILE=1 prints a per-frame time breakdown

Correctness summary (validated against the comate original on this dataset):
    frame-log decisions bit-identical; 70-frame geometry identical
    (s=3.2918e-3, A=-1.4855, chain last +0.0622 px, 68/68 loop pairs).

Why the frames' own metadata is still required: `Step` (encoder x), `MotionStartPoint`
(encoder y) and `Direction` are not recoverable from pixels. They live in the acquisition
folder's LocalImageInfos.json, which is found automatically.

How it works
------------
1. Frames arrive in order. Each one is placed from its own metadata plus a skew model, then
   measured against its neighbour, corrected once, warped and pasted. Nothing already pasted
   is ever revised.
2. The skew model `dy = s*u + A*sigma` is refitted after every trusted pair, so the placement
   gets better as the roll runs. Cold-start values are a starting point, not a calibration.
3. Each strip is also measured against the strip TWO back (they still overlap by ~316 px after
   the seam inset). That second constraint keeps the residual chain from being a random walk.
4. The placement is sub-pixel: the integer part selects the paste row, the fraction is folded
   into the same vertical warp that carries the local-pose correction.
5. A frame whose MotionStartPoint is invalid (~0) is HELD until two same-direction frames have
   arrived to repair it - a start-up latency, not a lookahead.

Outputs (in --output-dir)
-------------------------
    stitched_<start>_<end>_stream.tif
    stream_frame_log.csv                                  per-frame decisions and the fit
    estimated_final_window_residuals_before_local_pose.csv  input for comate/eval_stitch_seams.py
    loop_closure_pairs.csv                                the i,i+2 measurements
    stream_summary.json                                   (includes wall_seconds / seconds_per_frame)

The rectification core, the overlap measurement and the local-pose warp are vendored verbatim
from 0717/0731back/stitch_0_34_registered_v14final_local_pose.py so this file has no project
imports.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import os
import re
import statistics
import sys
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from PIL import Image
from scipy.interpolate import PchipInterpolator

Image.MAX_IMAGE_PIXELS = None


# ============================================================================
# vendored verbatim from the delivery script: rectification, overlap measurement,
# local-pose warp, and the geometry constants
# ============================================================================

def interpolation_flag(name: str) -> int:
    table = {
        "nearest": cv2.INTER_NEAREST,
        "linear": cv2.INTER_LINEAR,
        "cubic": cv2.INTER_CUBIC,
        "lanczos": cv2.INTER_LANCZOS4,
    }
    return table[name]


def allocate_output(image: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    if image.ndim == 2:
        return np.zeros((out_h, out_w), dtype=image.dtype)
    if image.ndim == 3:
        return np.zeros((out_h, out_w, image.shape[2]), dtype=image.dtype)
    raise ValueError(f"Unsupported image shape: {image.shape}")


@dataclass
class RobustAxisModel:
    physical_col: str
    pixel_col: str
    knots_physical_mm: np.ndarray
    knots_source_px: np.ndarray
    left_slope_px_per_mm: float
    right_slope_px_per_mm: float
    edge_fit_points: int
    # 跨轴耦合项（schema v7：相机扫描线与运动方向差 0.17 度）。之前这个移植丢了，
    # 所以 yaml 里写了 cross_term 也不会进成图（标定侧 step6 和现场版
    # vsDriverbox/drivers/camera/Charuco.py 都是实现了的）。默认空 = v6 行为。
    cross_other_col: str | None = None
    cross_reference_mm: float = 0.0
    cross_coefficients_px: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        self.knots_physical_mm = np.asarray(self.knots_physical_mm, dtype=np.float64)
        self.knots_source_px = np.asarray(self.knots_source_px, dtype=np.float64)
        self.cross_coefficients_px = tuple(float(v) for v in self.cross_coefficients_px)
        if self.cross_coefficients_px and not self.cross_other_col:
            raise ValueError("有跨轴项系数时必须给 cross_other_col。")
        if len(self.knots_physical_mm) < 2:
            raise ValueError("Axis model needs at least 2 knots.")
        if len(self.knots_physical_mm) != len(self.knots_source_px):
            raise ValueError("Axis physical/source knot counts do not match.")
        if not np.all(np.diff(self.knots_physical_mm) > 0):
            raise ValueError("Axis physical knots must be strictly increasing.")
        self._pchip = PchipInterpolator(
            self.knots_physical_mm,
            self.knots_source_px,
            extrapolate=False,
        )

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
        result = np.empty_like(x, dtype=np.float64)
        left = x < self.phys_min
        right = x > self.phys_max
        middle = ~(left | right)
        if np.any(middle):
            result[middle] = self._pchip(x[middle])
        if np.any(left):
            result[left] = self.px_at_phys_min + self.left_slope_px_per_mm * (x[left] - self.phys_min)
        if np.any(right):
            result[right] = self.px_at_phys_max + self.right_slope_px_per_mm * (x[right] - self.phys_max)
        return result

    def cross(self, other_mm: np.ndarray) -> np.ndarray:
        """另一根轴对这条像素列的偏移；没有耦合项时返回 0。与 step6:406 逐字一致。"""
        arr = np.asarray(other_mm, dtype=np.float64)
        if not self.cross_coefficients_px:
            return np.zeros_like(arr)
        delta = arr - float(self.cross_reference_mm)
        out = np.zeros_like(arr)
        for power, coef in enumerate(self.cross_coefficients_px, start=1):
            out += float(coef) * delta ** power
        return out

    @property
    def has_cross_term(self) -> bool:
        return bool(self.cross_coefficients_px)

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "RobustAxisModel":
        cross = data.get("cross_term") or {}
        return cls(
            physical_col=str(data["physical_col"]),
            pixel_col=str(data["pixel_col"]),
            knots_physical_mm=np.asarray(data["knots_physical_mm"], dtype=np.float64),
            knots_source_px=np.asarray(data["knots_source_px"], dtype=np.float64),
            left_slope_px_per_mm=float(data["left_slope_px_per_mm"]),
            right_slope_px_per_mm=float(data["right_slope_px_per_mm"]),
            edge_fit_points=int(data["edge_fit_points"]),
            cross_other_col=(str(cross["other_col"]) if cross.get("other_col") else None),
            cross_reference_mm=float(cross.get("reference_mm", 0.0)),
            cross_coefficients_px=tuple(float(v) for v in (cross.get("coefficients_px") or ())),
        )


def normalize_target_full_ranges_mm(ranges: dict[str, object]) -> dict[str, float]:
    aliases = {
        "x_mm_min": ("x_mm_min", "x_min"),
        "x_mm_max": ("x_mm_max", "x_max"),
        "y_mm_min": ("y_mm_min", "y_min"),
        "y_mm_max": ("y_mm_max", "y_max"),
    }
    normalized: dict[str, float] = {}
    for target_key, candidates in aliases.items():
        value = next((ranges[key] for key in candidates if key in ranges), None)
        if value is None:
            raise ValueError(f"target_full_ranges_mm is missing {target_key}.")
        normalized[target_key] = float(value)
    if normalized["x_mm_max"] <= normalized["x_mm_min"]:
        raise ValueError("target_full_ranges_mm requires x_mm_max > x_mm_min.")
    if normalized["y_mm_max"] <= normalized["y_mm_min"]:
        raise ValueError("target_full_ranges_mm requires y_mm_max > y_mm_min.")
    return normalized


@dataclass
class RectificationOptions:
    orientation: str = "auto"
    interpolation: str = "linear"
    chunk_rows: int = 128
    clip_map_to_image: bool = True
    output_dpi: int = 300
    y_scale: float = 1.0
    target_full_ranges_mm: dict[str, float] | None = None
    target_grid_pixels_per_mm: float | None = None


@dataclass
class LineScanPlanarCalibration:
    pixels_per_mm: float
    output_dpi: int
    source_x_model: RobustAxisModel
    source_y_model: RobustAxisModel
    residual_model: Any = None
    target_full_ranges_mm: dict[str, float] | None = None
    target_grid_pixels_per_mm: float | None = None
    target_grid_y_scale: float | None = None
    target_grid_orientation: str = "board_transposed"
    target_grid_axis_directions: dict[str, bool] | None = None
    target_coordinate_offset_mm: dict[str, float] | None = None
    target_coordinate_affine_mm: dict[str, object] | None = None

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "LineScanPlanarCalibration":
        residual_yaml = data.get("residual_correction", {"type": "none"}) or {"type": "none"}
        residual_model = None
        if isinstance(residual_yaml, dict) and residual_yaml.get("type") == "hybrid_poly_target":
            residual_model = HybridPolyTargetResidualModel.from_yaml_dict(residual_yaml)
        elif isinstance(residual_yaml, dict) and residual_yaml.get("type") == "rbf_tapered_grid":
            residual_model = TaperedRBFGridResidualModel.from_yaml_dict(residual_yaml)
        elif isinstance(residual_yaml, dict) and residual_yaml.get("type") not in {None, "none"}:
            raise ValueError(
                "v14final standalone only supports PCHIP-only, RBF grid, or 0717 hybrid-poly experimental YAML. "
                f"Unsupported residual_correction.type={residual_yaml.get('type')!r}."
            )

        output_defaults = data.get("output_defaults", {}) or {}
        target_grid = output_defaults.get("target_grid", {}) or {}
        target_ranges = target_grid.get("full_ranges_mm") or output_defaults.get("target_full_ranges_mm")
        target_y_scale = target_grid.get("y_scale")
        board = data["board"]
        pixels_per_mm = (
            board.get("pixels_per_mm")
            or board.get("output_pixels_per_mm")
            or (float(board["pixels_per_square"]) / float(board["square_size_mm"]))
        )
        return cls(
            pixels_per_mm=float(pixels_per_mm),
            output_dpi=int(board.get("output_dpi", 300)),
            source_x_model=RobustAxisModel.from_yaml_dict(data["source_x_axis_model"]),
            source_y_model=RobustAxisModel.from_yaml_dict(data["source_y_axis_model"]),
            residual_model=residual_model,
            target_full_ranges_mm=(
                normalize_target_full_ranges_mm(target_ranges)
                if target_ranges is not None else None
            ),
            target_grid_pixels_per_mm=(
                float(target_grid["pixels_per_mm"])
                if target_grid.get("pixels_per_mm") is not None else None
            ),
            target_grid_y_scale=float(target_y_scale) if target_y_scale is not None else None,
            target_grid_orientation=str(target_grid.get("orientation", "board_transposed")),
            target_grid_axis_directions=(
                {str(k): bool(v) for k, v in dict(target_grid["axis_directions"]).items()}
                if target_grid.get("axis_directions") is not None else None
            ),
            target_coordinate_offset_mm=(
                {str(k): float(v) for k, v in dict(target_grid["coordinate_offset_mm"]).items()}
                if target_grid.get("coordinate_offset_mm") is not None else None
            ),
            target_coordinate_affine_mm=(
                {str(k): v for k, v in dict(target_grid["coordinate_affine_mm"]).items()}
                if target_grid.get("coordinate_affine_mm") is not None else None
            ),
        )


@dataclass
class HybridPolyTargetResidualModel:
    common_exponents: list[tuple[int, int]]
    direction_exponents: list[tuple[int, int]]
    center: np.ndarray
    scale: np.ndarray
    coef_x: np.ndarray
    coef_y: np.ndarray
    direction_sign: float
    _cache: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "HybridPolyTargetResidualModel":
        return cls(
            common_exponents=[tuple(int(v) for v in item) for item in data["common_exponents"]],
            direction_exponents=[tuple(int(v) for v in item) for item in data["direction_exponents"]],
            center=np.asarray(data["center"], dtype=np.float64),
            scale=np.asarray(data["scale"], dtype=np.float64),
            coef_x=np.asarray(data["coef_x"], dtype=np.float64),
            coef_y=np.asarray(data["coef_y"], dtype=np.float64),
            direction_sign=float(data["direction_sign"]),
        )

    def __call__(self, target_x_mm: np.ndarray, target_y_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (
            tuple(target_x_mm.shape),
            float(target_x_mm[0, 0]),
            float(target_x_mm[-1, 0]),
            float(target_y_mm[0, 0]),
            float(target_y_mm[0, -1]),
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        target_x = np.asarray(target_x_mm, dtype=np.float64)
        target_y = np.asarray(target_y_mm, dtype=np.float64)
        separable_grid = (
            target_x.ndim == 2
            and target_y.ndim == 2
            and np.allclose(target_x, target_x[:, :1])
            and np.allclose(target_y, target_y[:1, :])
        )
        if separable_grid:
            x = (target_x[:, 0] - float(self.center[0])) / float(self.scale[0])
            y = (target_y[0, :] - float(self.center[1])) / float(self.scale[1])
            corr_x = np.zeros(target_x.shape, dtype=np.float64)
            corr_y = np.zeros(target_x.shape, dtype=np.float64)
        else:
            x = (target_x - float(self.center[0])) / float(self.scale[0])
            y = (target_y - float(self.center[1])) / float(self.scale[1])
            corr_x = np.zeros_like(x, dtype=np.float64)
            corr_y = np.zeros_like(y, dtype=np.float64)
        term_index = 0
        max_x_power = max([i for i, _ in self.common_exponents + self.direction_exponents] or [0])
        max_y_power = max([j for _, j in self.common_exponents + self.direction_exponents] or [0])
        x_powers = [np.ones_like(x, dtype=np.float64)]
        y_powers = [np.ones_like(y, dtype=np.float64)]
        for _ in range(max_x_power):
            x_powers.append(x_powers[-1] * x)
        for _ in range(max_y_power):
            y_powers.append(y_powers[-1] * y)
        for i, j in self.common_exponents:
            term = (
                x_powers[i][:, None] * y_powers[j][None, :]
                if separable_grid else x_powers[i] * y_powers[j]
            )
            corr_x += term * float(self.coef_x[term_index])
            corr_y += term * float(self.coef_y[term_index])
            term_index += 1
        direction = float(self.direction_sign)
        for i, j in self.direction_exponents:
            term = direction * (
                x_powers[i][:, None] * y_powers[j][None, :]
                if separable_grid else x_powers[i] * y_powers[j]
            )
            corr_x += term * float(self.coef_x[term_index])
            corr_y += term * float(self.coef_y[term_index])
            term_index += 1
        corr_x = corr_x.astype(np.float32)
        corr_y = corr_y.astype(np.float32)
        self._cache[cache_key] = (corr_x, corr_y)
        return corr_x, corr_y


@dataclass
class TaperedRBFGridResidualModel:
    grid_x_mm: np.ndarray
    grid_y_mm: np.ndarray
    correction_x_grid_px: np.ndarray
    correction_y_grid_px: np.ndarray
    _cache: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    coordinate_space: str = "local"

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "TaperedRBFGridResidualModel":
        return cls(
            grid_x_mm=np.asarray(data["grid_x_mm"], dtype=np.float64),
            grid_y_mm=np.asarray(data["grid_y_mm"], dtype=np.float64),
            correction_x_grid_px=np.asarray(data["correction_x_grid_px"], dtype=np.float32),
            correction_y_grid_px=np.asarray(data["correction_y_grid_px"], dtype=np.float32),
        )

    def __call__(self, local_x_mm: np.ndarray, local_y_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (
            tuple(local_x_mm.shape),
            float(local_x_mm[0, 0]),
            float(local_x_mm[-1, 0]),
            float(local_y_mm[0, 0]),
            float(local_y_mm[0, -1]),
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        step_x = float(self.grid_x_mm[1] - self.grid_x_mm[0])
        step_y = float(self.grid_y_mm[1] - self.grid_y_mm[0])
        map_x = ((np.asarray(local_x_mm, dtype=np.float64) - self.grid_x_mm[0]) / step_x).astype(np.float32)
        map_y = ((np.asarray(local_y_mm, dtype=np.float64) - self.grid_y_mm[0]) / step_y).astype(np.float32)
        correction_x = cv2.remap(
            self.correction_x_grid_px,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        correction_y = cv2.remap(
            self.correction_y_grid_px,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        self._cache[cache_key] = (correction_x, correction_y)
        return correction_x, correction_y


def load_calibration_yaml(path: str | Path) -> LineScanPlanarCalibration:
    with open(path, "r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid calibration YAML: {path}")
    return LineScanPlanarCalibration.from_yaml_dict(data)


def fixed_step_vector(start: float, end: float, pixels_per_mm: float) -> np.ndarray:
    span_mm = abs(float(end) - float(start))
    intervals = max(1, int(math.ceil(span_mm * pixels_per_mm)))
    sign = 1.0 if end >= start else -1.0
    return float(start) + sign * np.arange(intervals + 1, dtype=np.float64) / float(pixels_per_mm)


def build_output_vectors(
    full_ranges: dict[str, float],
    pixels_per_mm: float,
    orientation: str,
    y_scale: float = 1.0,
    target_axis_directions: dict[str, bool] | None = None,
) -> dict[str, np.ndarray]:
    if orientation == "board_transposed":
        directions = target_axis_directions or {}
        y_forward = bool(directions.get("y_mm", True))
        x_forward = bool(directions.get("x_mm", False))
        col_y_start, col_y_end = (
            (full_ranges["y_mm_min"], full_ranges["y_mm_max"])
            if y_forward else (full_ranges["y_mm_max"], full_ranges["y_mm_min"])
        )
        row_x_start, row_x_end = (
            (full_ranges["x_mm_min"], full_ranges["x_mm_max"])
            if x_forward else (full_ranges["x_mm_max"], full_ranges["x_mm_min"])
        )
        return {
            "orientation": np.array(["board_transposed"], dtype=object),
            "col_y_mm": fixed_step_vector(col_y_start, col_y_end, pixels_per_mm * y_scale),
            "row_x_mm": fixed_step_vector(row_x_start, row_x_end, pixels_per_mm),
        }
    if orientation == "board":
        return {
            "orientation": np.array(["board"], dtype=object),
            "col_x_mm": fixed_step_vector(full_ranges["x_mm_min"], full_ranges["x_mm_max"], pixels_per_mm * y_scale),
            "row_y_mm": fixed_step_vector(full_ranges["y_mm_min"], full_ranges["y_mm_max"], pixels_per_mm),
        }
    raise ValueError(f"Unsupported rectification orientation for v14final: {orientation}")


def generate_map_chunk(
    vectors: dict[str, np.ndarray],
    row_start: int,
    row_end: int,
    image_shape: tuple[int, ...],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    residual_model: Any,
    clip_map_to_image: bool,
    target_coordinate_offset_mm: dict[str, float] | None = None,
    target_coordinate_affine_mm: dict[str, object] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    orientation = str(vectors["orientation"][0])
    if orientation == "board_transposed":
        board_y_mm, board_x_mm = np.meshgrid(vectors["col_y_mm"], vectors["row_x_mm"][row_start:row_end])
    elif orientation == "board":
        board_x_mm, board_y_mm = np.meshgrid(vectors["col_x_mm"], vectors["row_y_mm"][row_start:row_end])
    else:
        raise ValueError(f"Unsupported orientation: {orientation}")

    offset = target_coordinate_offset_mm or {}
    local_board_x_mm = board_x_mm - float(offset.get("x_mm", 0.0))
    local_board_y_mm = board_y_mm - float(offset.get("y_mm", 0.0))

    affine = target_coordinate_affine_mm or {}
    if affine and bool(affine.get("enabled", True)):
        target_axis = str(affine.get("target_axis", "y_mm"))
        apply_axis = str(affine.get("apply_to", target_axis))
        intercept_mm = float(affine.get("intercept_mm", 0.0))
        slope = float(affine.get("slope", 0.0))
        target_coord_mm = board_x_mm if target_axis == "x_mm" else board_y_mm
        center_mm = float(affine.get("center_mm", float(np.mean(target_coord_mm))))
        correction_mm = intercept_mm + slope * (target_coord_mm - center_mm)
        if apply_axis == "x_mm":
            local_board_x_mm = local_board_x_mm - correction_mm
        elif apply_axis == "y_mm":
            local_board_y_mm = local_board_y_mm - correction_mm
        else:
            raise ValueError("target_coordinate_affine_mm.apply_to must be 'x_mm' or 'y_mm'.")

    source_x_input = local_board_x_mm if source_x_model.physical_col == "x_mm" else local_board_y_mm
    source_y_input = local_board_x_mm if source_y_model.physical_col == "x_mm" else local_board_y_mm
    map_x = source_x_model(source_x_input)
    map_y = source_y_model(source_y_input)
    # 跨轴项：求值坐标是**本地**板坐标（已经减过 coordinate_offset_mm），与
    # step6:981-986 和现场版 Charuco.py:343-348 同一口径。
    if source_x_model.has_cross_term:
        src = local_board_x_mm if source_x_model.cross_other_col == "x_mm" else local_board_y_mm
        map_x = map_x + source_x_model.cross(src)
    if source_y_model.has_cross_term:
        src = local_board_x_mm if source_y_model.cross_other_col == "x_mm" else local_board_y_mm
        map_y = map_y + source_y_model.cross(src)
    if residual_model is not None:
        if getattr(residual_model, "coordinate_space", "target") == "local":
            correction_x, correction_y = residual_model(local_board_x_mm, local_board_y_mm)
        else:
            correction_x, correction_y = residual_model(board_x_mm, board_y_mm)
        map_x = map_x + correction_x
        map_y = map_y + correction_y
    if clip_map_to_image:
        h, w = image_shape[:2]
        map_x = np.clip(map_x, 0.0, float(w - 1))
        map_y = np.clip(map_y, 0.0, float(h - 1))
    return map_x.astype(np.float32), map_y.astype(np.float32)


def separable_maps_available(
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    residual_model: Any,
    target_coordinate_affine_mm: dict[str, object] | None,
) -> bool:
    """True when the full 2D map is separable: map_x depends only on the column and
    map_y only on the row. That holds when there is no 2D residual field, no
    cross-axis affine term, AND no cross-term: the axis models are 1D PCHIP and the
    offset subtracts a constant per axis, so evaluating them on the 2D meshgrid
    recomputes each 1D result H*W times instead of once. Bit-identical to the 2D path
    by construction.

    有 cross_term 时必须走 2-D 路径：map_x 除了列还依赖行，在这条快路径里会被
    彻底丢弃（就是之前的 bug）。"""
    return (residual_model is None and not target_coordinate_affine_mm
            and not source_x_model.has_cross_term
            and not source_y_model.has_cross_term)


def generate_separable_maps(
    vectors: dict[str, np.ndarray],
    image_shape: tuple[int, ...],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    clip_map_to_image: bool,
    target_coordinate_offset_mm: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """1D map arrays: fx (out_w,) for map_x, fy (out_h,) for map_y.

    Only valid when `separable_maps_available(...)`; covers the board_transposed and
    board orientations for both swapped/direct axis mappings."""
    orientation = str(vectors["orientation"][0])
    offset = target_coordinate_offset_mm or {}
    off_x = float(offset.get("x_mm", 0.0))
    off_y = float(offset.get("y_mm", 0.0))
    if orientation == "board_transposed":
        col_phys = vectors["col_y_mm"] - off_y      # varies along columns -> y_mm values
        row_phys = vectors["row_x_mm"] - off_x      # varies along rows    -> x_mm values
    elif orientation == "board":
        col_phys = vectors["col_x_mm"] - off_x
        row_phys = vectors["row_y_mm"] - off_y
    else:
        raise ValueError(f"Unsupported orientation: {orientation}")
    # source_x_model maps the physical column that drives map_x (pixel x)
    fx_input = col_phys if source_x_model.physical_col == ("y_mm" if orientation == "board_transposed" else "x_mm") else row_phys
    fy_input = row_phys if source_y_model.physical_col == ("x_mm" if orientation == "board_transposed" else "y_mm") else col_phys
    fx = source_x_model(fx_input)
    fy = source_y_model(fy_input)
    if clip_map_to_image:
        h, w = image_shape[:2]
        fx = np.clip(fx, 0.0, float(w - 1))
        fy = np.clip(fy, 0.0, float(h - 1))
    return fx.astype(np.float32), fy.astype(np.float32)


def remap_full_image_in_chunks(
    image: np.ndarray,
    vectors: dict[str, np.ndarray],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    residual_model: Any,
    interpolation: int,
    chunk_rows: int,
    clip_map_to_image: bool,
    target_coordinate_offset_mm: dict[str, float] | None = None,
    target_coordinate_affine_mm: dict[str, object] | None = None,
) -> np.ndarray:
    orientation = str(vectors["orientation"][0])
    if orientation == "board_transposed":
        out_h, out_w = len(vectors["row_x_mm"]), len(vectors["col_y_mm"])
    elif orientation == "board":
        out_h, out_w = len(vectors["row_y_mm"]), len(vectors["col_x_mm"])
    else:
        raise ValueError(f"Unsupported orientation: {orientation}")

    output = allocate_output(image, out_h, out_w)
    separable = separable_maps_available(
        source_x_model, source_y_model, residual_model, target_coordinate_affine_mm)
    if separable:
        fx, fy = generate_separable_maps(
            vectors, image.shape, source_x_model, source_y_model,
            clip_map_to_image, target_coordinate_offset_mm)
    for y0 in range(0, out_h, chunk_rows):
        y1 = min(y0 + chunk_rows, out_h)
        if separable:
            # map_x identical on every row; map_y identical on every column. Same values
            # as the 2D path, materialised by broadcast instead of a 2D PCHIP evaluation.
            map_x = np.repeat(fx[None, :], y1 - y0, axis=0)
            map_y = np.repeat(fy[y0:y1, None], out_w, axis=1)
        else:
            map_x, map_y = generate_map_chunk(
                vectors=vectors,
                row_start=y0,
                row_end=y1,
                image_shape=image.shape,
                source_x_model=source_x_model,
                source_y_model=source_y_model,
                residual_model=residual_model,
                clip_map_to_image=clip_map_to_image,
                target_coordinate_offset_mm=target_coordinate_offset_mm,
                target_coordinate_affine_mm=target_coordinate_affine_mm,
            )
        output[y0:y1] = cv2.remap(
            image,
            map_x,
            map_y,
            interpolation=interpolation,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if not _QUIET_REMAP:
            print(f"[remap] rows={y0:6d}..{y1:6d} / {out_h}")
    return output


def rectify_image_array(
    image: np.ndarray,
    calibration: LineScanPlanarCalibration,
    options: RectificationOptions | None = None,
) -> np.ndarray:
    opts = options or RectificationOptions(output_dpi=calibration.output_dpi)
    target_ranges = opts.target_full_ranges_mm or calibration.target_full_ranges_mm
    if target_ranges is None:
        raise ValueError("v14final standalone requires registered YAML target_full_ranges_mm.")

    full_ranges = normalize_target_full_ranges_mm(target_ranges)
    orientation = "board_transposed" if opts.orientation == "auto" else opts.orientation
    if orientation == "auto":
        orientation = calibration.target_grid_orientation
    pixels_per_mm = float(opts.target_grid_pixels_per_mm or calibration.target_grid_pixels_per_mm or calibration.pixels_per_mm)
    y_scale = float(calibration.target_grid_y_scale or opts.y_scale)
    vectors = build_output_vectors(
        full_ranges,
        pixels_per_mm,
        orientation,
        y_scale=y_scale,
        target_axis_directions=calibration.target_grid_axis_directions,
    )
    return remap_full_image_in_chunks(
        image=image,
        vectors=vectors,
        source_x_model=calibration.source_x_model,
        source_y_model=calibration.source_y_model,
        residual_model=calibration.residual_model,
        interpolation=interpolation_flag(opts.interpolation),
        chunk_rows=max(1, int(opts.chunk_rows)),
        clip_map_to_image=bool(opts.clip_map_to_image),
        target_coordinate_offset_mm=calibration.target_coordinate_offset_mm,
        target_coordinate_affine_mm=calibration.target_coordinate_affine_mm,
    )


D_STEP_X = 847.965622809793
D_MSP_Y = 846.668360003
# The field version (vsDriverbox `Camera.ImageStitch`) does not use the fitted encoder
# scales; it derives both axes from the nominal DPI, `K_Coef = 25.4/DPI*10000`.
# stitch0905 坑6/7：这个 300 是现场配置里的 DPI，不是物理常数，换机器/换配置就错；
# 所以下面的 K_COEF_ACTIVE 在启动时从 **yaml 自己的 output_defaults.dpi** 重算，
# `--encoder-scale yaml-nominal` 用的就是它（硬编码值仅作默认/回参）。
K_COEF_NOMINAL = 25.4 / 300.0 * 10000.0
K_COEF_ACTIVE = K_COEF_NOMINAL


def yaml_output_dpi(path) -> float | None:
    """从标定 yaml 里抟出输出 DPI（只读文本，不解析 800KB）。"""
    try:
        m = re.search(r"^\s{2,}dpi:\s*([0-9.]+)", Path(path).read_text(
            encoding="utf-8", errors="replace"), re.M)
        return float(m.group(1)) if m else None
    except OSError:
        return None
X_OFFSET_TRUE_PX = 0.0

X_OFFSET_FALSE_PX = 2.908141050525
Y_OFFSET_TRUE_PX = 0.0
Y_OFFSET_FALSE_PX = -0.436554481180
SEAM_INSET_PX = 256
ROTATE_FINAL_CCW_90 = True

# Placement skew: y is coupled to x by a machine geometry constant, so every adjacent
# pair carries the same y offset and the sequential refinement used to integrate it
# into an ~90 px chain. Fitted per batch from the measured pair offsets; the fallback
# is only used when the fit is degenerate. Three independent runs on this machine agreed
# to 1.9% (theta 0.18550 deg on strips 35-69, 0.18618 and 0.18899 on strips 0-34 with
# two different calibrations), which is why a single constant per batch is enough.
SKEW_S_FALLBACK_PX_PER_PX = 3.2376e-3
# 注意：本常量在下面"在线拟合"一节会被重新赋值，那里的值才是运行时生效的。
SKEW_S_PLAUSIBLE_RANGE = (-2.0e-3, 6.0e-3)
SKEW_FIT_MIN_PAIRS = 6

# MSP ~= 0 repair constants.
INVALID_MSP_ABS_THRESHOLD = 1.0
NEAREST_SAME_DIRECTION_COUNT = 6
ZERO_MSP_RANGE_START_FINE_TUNE_PX = 0.5
ZERO_MSP_FINE_TUNE_PX = ZERO_MSP_RANGE_START_FINE_TUNE_PX
GLOBAL_MANUAL_Y_COMPENSATION_PX = 0.0

# Registered target-grid rectification.
RECTIFY_OPTIONS = RectificationOptions(
    orientation="auto",
    interpolation="linear",
    chunk_rows=256,
    clip_map_to_image=True,
    output_dpi=300,
    y_scale=1.0,
)

# Overlap measurement.
WINDOW_COUNT = 7
MIN_WINDOW_H = 220
MIN_PHASE_RESPONSE = 0.05
OVERLAP_MAX_WIDTH = 1400
OVERLAP_CROP_MARGIN = 32


# ============================================================================
# acceleration: process-pool prefetch rectification + thread-parallel windows
# ============================================================================

import threading
from concurrent.futures import ProcessPoolExecutor

_QUIET_REMAP = False          # workers set True to silence chunk prints
_WINDOW_POOL = None           # ThreadPoolExecutor for window phase correlation
_PAIR_POOL = None             # single-thread pool: loop-closure pair measured concurrently

# optional per-frame profiling (TREAWORK_PROFILE=1)
import os as _os
_PROFILE = bool(_os.environ.get("TREAWORK_PROFILE"))
_FRAME_T: dict[str, float] = {}


def _tick(key: str, seconds: float) -> None:
    if _PROFILE:
        _FRAME_T[key] = _FRAME_T.get(key, 0.0) + seconds


def _worker_init(true_yaml: str, false_yaml: str, cv2_threads: int = 0) -> None:
    """ProcessPool initializer: load calibrations once, silence progress prints.

    cv2_threads > 0 caps each worker's internal OpenCV thread pool; with several
    worker processes the default (= all cores each) oversubscribes the machine.
    """
    global _QUIET_REMAP, _WORKER_CALS
    if cv2_threads > 0:
        cv2.setNumThreads(int(cv2_threads))
    import builtins
    _orig_print = print

    def _quiet(*a, **k):
        if not (a and isinstance(a[0], str) and a[0].startswith("[remap]")):
            _orig_print(*a, **k)

    builtins.print = _quiet
    _QUIET_REMAP = True
    _WORKER_CALS = ((true_yaml, false_yaml),
                    load_calibration_yaml(true_yaml), load_calibration_yaml(false_yaml))


_WORKER_CALS = None


def _rectify_task(path: str, direction: bool, true_yaml: str, false_yaml: str) -> np.ndarray:
    """Worker-side full rectification (load + hflip + remap)."""
    global _WORKER_CALS
    if _WORKER_CALS is None or _WORKER_CALS[0] != (true_yaml, false_yaml):
        _WORKER_CALS = ((true_yaml, false_yaml),
                        load_calibration_yaml(true_yaml), load_calibration_yaml(false_yaml))
    return rectify_and_orient(path, direction, _WORKER_CALS[1], _WORKER_CALS[2])


# ============================================================================
# shared-memory pipeline: workers write rectified strips into shm blocks; the main
# process and the window-worker processes read the same blocks zero-copy, so no
# 69 MB array ever crosses a process boundary.
# ============================================================================

from multiprocessing import shared_memory


def _rectify_into_shm_task(
    shm_name: str, out_h: int, out_w: int,
    path: str, direction: bool, true_yaml: str, false_yaml: str,
) -> tuple[int, int]:
    """Rectify one strip inside a worker and write it straight into shared memory."""
    global _WORKER_CALS
    if _WORKER_CALS is None or _WORKER_CALS[0] != (true_yaml, false_yaml):
        _WORKER_CALS = ((true_yaml, false_yaml),
                        load_calibration_yaml(true_yaml), load_calibration_yaml(false_yaml))
    image = rectify_and_orient(path, direction, _WORKER_CALS[1], _WORKER_CALS[2])
    shm = shared_memory.SharedMemory(name=shm_name)
    try:
        view = np.ndarray((out_h, out_w), dtype=np.uint8, buffer=shm.buf)
        view[:] = image
    finally:
        shm.close()  # detach only; the mapping stays alive for the readers
    return out_h, out_w


# worker-side attach cache: name -> (SharedMemory, ndarray). LRU-bounded so the
# window pool processes eventually release old strips.
_SHM_ATTACH: OrderedDict[str, tuple[Any, np.ndarray]] = OrderedDict()


def _shm_array(name: str, out_h: int, out_w: int) -> np.ndarray:
    hit = _SHM_ATTACH.pop(name, None)
    if hit is None:
        shm = shared_memory.SharedMemory(name=name)
        hit = (shm, np.ndarray((out_h, out_w), dtype=np.uint8, buffer=shm.buf))
    _SHM_ATTACH[name] = hit
    while len(_SHM_ATTACH) > 6:
        _, (old_shm, _) = _SHM_ATTACH.popitem(last=False)
        old_shm.close()
    return hit[1]


def _window_task(payload: tuple) -> dict[str, Any] | None:
    """Process-pool counterpart of _measure_one_window: resolve images from shm."""
    (shm_a, shape_a, shm_b, shape_b, a, b, rect, window_index, ox, oy, ow, oh) = payload
    img_a = _shm_array(shm_a, *shape_a)
    img_b = _shm_array(shm_b, *shape_b)
    return _measure_one_window(img_a, img_b, a, b, rect, window_index, ox, oy, ow, oh)


def _window_pool_init(cv2_threads: int) -> None:
    if cv2_threads > 0:
        cv2.setNumThreads(int(cv2_threads))
    global _QUIET_REMAP
    _QUIET_REMAP = True


class ShmRectifiedCache:
    """Prefetch cache whose entries are shared-memory blocks written by the rectify
    pool. get() returns a zero-copy ndarray view. Window measurement dispatches to a
    separate process pool that attaches the same blocks by name."""

    def __init__(self, executor: Any, window_executor: Any,
                 true_yaml, false_yaml, true_shape, false_shape, max_size: int = 3):
        self.executor = executor
        self.window_executor = window_executor
        self._ykey = (str(true_yaml), str(false_yaml))
        self.true_shape = tuple(int(v) for v in true_shape)
        self.false_shape = tuple(int(v) for v in false_shape)
        self.max_size = int(max_size)
        self._items: OrderedDict[int, tuple[Any, np.ndarray]] = OrderedDict()
        self._futures: dict[int, Any] = {}
        self._lock = threading.Lock()

    def submit(self, index: int, path: str, direction: bool) -> None:
        with self._lock:
            if index in self._futures or index in self._items:
                return
            out_h, out_w = self.true_shape if direction else self.false_shape
            shm = shared_memory.SharedMemory(create=True, size=out_h * out_w)
            future = self.executor.submit(
                _rectify_into_shm_task, shm.name, out_h, out_w,
                path, direction, self._ykey[0], self._ykey[1])
            self._futures[index] = (future, shm)
            future.add_done_callback(lambda f, s=shm: None)  # keep ref via _futures

    def _resolve(self, index: int, direction: bool) -> np.ndarray:
        with self._lock:
            hit = self._items.get(index)
            if hit is not None:
                # atomic move-to-end; NEVER pop here - another thread may look the name
                # up (shm_name) between a pop and the re-insert
                self._items.move_to_end(index)
            pending = self._futures.get(index)
        if hit is not None:
            return hit[1]
        if pending is None:
            raise KeyError(index)
        future, shm = pending
        out_h, out_w = self.true_shape if direction else self.false_shape
        future.result()  # worker finished writing
        view = np.ndarray((out_h, out_w), dtype=np.uint8, buffer=shm.buf)
        with self._lock:
            self._futures.pop(index, None)
            self._items[index] = (shm, view)
            while len(self._items) > self.max_size:
                _, (old_shm, _) = self._items.popitem(last=False)
                old_shm.close()
                old_shm.unlink()
        return view

    def get(self, record: dict[str, Any]) -> np.ndarray:
        return self._resolve(int(record["index"]), bool(record["direction"]))

    def shm_name(self, index: int) -> str:
        """Name of the shm block holding this strip (attached or pending)."""
        with self._lock:
            hit = self._items.get(index)
            if hit is not None:
                return hit[0].name
            pending = self._futures.get(index)
            if pending is not None:
                return pending[1].name
        raise KeyError(index)

    def run_windows(self, a: dict[str, Any], b: dict[str, Any],
                    tasks: list[tuple[tuple[int, int, int, int], int]],
                    ox: int, oy: int, ow: int, oh: int) -> list[dict[str, Any] | None]:
        """Dispatch window measurements to the process pool over shm references."""
        ia, ib = int(a["index"]), int(b["index"])
        shape_a = self.true_shape if a["direction"] else self.false_shape
        shape_b = self.true_shape if b["direction"] else self.false_shape
        payloads = [
            (self.shm_name(ia), shape_a, self.shm_name(ib), shape_b,
             a, b, rect, window_index, ox, oy, ow, oh)
            for rect, window_index in tasks
        ]
        return list(self.window_executor.map(_window_task, payloads))

    def close(self) -> None:
        with self._lock:
            for future, shm in self._futures.values():
                try:
                    future.result()
                except Exception:
                    pass
                shm.close()
                shm.unlink()
            self._futures.clear()
            for shm, _ in self._items.values():
                shm.close()
                shm.unlink()
            self._items.clear()


class PrefetchRectifiedCache:
    """Cache backed by pre-submitted futures. Same interface as RectifiedImageCache;
    get() blocks until the worker finishes. Thread-safe for the window pool."""

    def __init__(self, executor: ProcessPoolExecutor, true_yaml, false_yaml, max_size: int = 4):
        self.executor = executor
        self._ykey = (str(true_yaml), str(false_yaml))
        self.max_size = int(max_size)
        self._items: OrderedDict[int, np.ndarray] = OrderedDict()
        self._futures: dict[int, Any] = {}
        self._lock = threading.Lock()

    def submit(self, index: int, path: str, direction: bool) -> None:
        with self._lock:
            if index in self._futures or index in self._items:
                return
            self._futures[index] = self.executor.submit(
                _rectify_task, path, direction, self._ykey[0], self._ykey[1])

    def get(self, record: dict[str, Any]) -> np.ndarray:
        index = int(record["index"])
        with self._lock:
            image = self._items.pop(index, None)
            future = self._futures.get(index)
        if image is None:
            if future is not None:
                image = future.result()
                with self._lock:
                    self._futures.pop(index, None)
            else:
                image = rectify_and_orient(
                    str(record["path"]), bool(record["direction"]),
                    load_calibration_yaml(self._ykey[0]), load_calibration_yaml(self._ykey[1]),
                )
        with self._lock:
            self._items[index] = image
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)
        return image


class RectifiedImageCache:
    def __init__(self, true_calibration: Any, false_calibration: Any, max_size: int = 4) -> None:
        self.true_calibration = true_calibration
        self.false_calibration = false_calibration
        self.max_size = int(max_size)
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()

    def get(self, record: dict[str, Any]) -> np.ndarray:
        index = int(record["index"])
        if index in self._cache:
            image = self._cache.pop(index)
            self._cache[index] = image
            return image
        image = rectify_and_orient(
            str(record["path"]),
            bool(record["direction"]),
            self.true_calibration,
            self.false_calibration,
        )
        self._cache[index] = image
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
        return image

def target_grid_shape(calibration: Any) -> tuple[int, int]:
    ranges = calibration.target_full_ranges_mm
    if ranges is None:
        raise ValueError("Registered YAML is missing target_full_ranges_mm.")
    ppm = float(calibration.target_grid_pixels_per_mm or calibration.pixels_per_mm)
    y_scale = float(calibration.target_grid_y_scale or 1.0)
    height = int(math.ceil((ranges["x_mm_max"] - ranges["x_mm_min"]) * ppm)) + 1
    width = int(math.ceil((ranges["y_mm_max"] - ranges["y_mm_min"]) * ppm * y_scale)) + 1
    return height, width



def load_json(path: Path, end_idx: int) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, list):
        raise ValueError("LocalImageInfos.json root must be a list")
    if len(data) <= end_idx:
        raise ValueError(f"JSON has {len(data)} entries, cannot read {end_idx}.tif")
    return data



def load_gray_array(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(path)
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    raise ValueError(f"Unsupported image shape: {image.shape}")


def ensure_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    raise ValueError(f"Unsupported corrected image shape: {image.shape}")


def is_valid_msp(value: float) -> bool:
    return abs(float(value)) > INVALID_MSP_ABS_THRESHOLD


def direction_x_offset(direction: bool) -> float:
    return X_OFFSET_TRUE_PX if direction else X_OFFSET_FALSE_PX


def direction_y_offset(direction: bool) -> float:
    return Y_OFFSET_TRUE_PX if direction else Y_OFFSET_FALSE_PX



def rectify_and_orient(
    path: str,
    direction: bool,
    true_calibration: Any,
    false_calibration: Any,
) -> np.ndarray:
    image = load_gray_array(path)
    if not direction:
        image = cv2.flip(image, 1)
    calibration = true_calibration if direction else false_calibration
    result = rectify_image_array(image, calibration, options=RECTIFY_OPTIONS)
    return ensure_grayscale(result)


def pasted_rect(record: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(record["canvas_x"]),
        int(record["canvas_y"]),
        int(record["paste_width"]),
        int(record["corrected_height"]),
    )


def intersect_rect(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0 = max(ax, bx)
    y0 = max(ay, by)
    x1 = min(ax + aw, bx + bw)
    y1 = min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1 - x0, y1 - y0


def center_limited_overlap(
    rect: tuple[int, int, int, int],
    max_width: int = OVERLAP_MAX_WIDTH,
    crop_margin: int = OVERLAP_CROP_MARGIN,
) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    if crop_margin > 0 and w > 2 * crop_margin and h > 2 * crop_margin:
        x += crop_margin
        y += crop_margin
        w -= 2 * crop_margin
        h -= 2 * crop_margin
    if w > max_width:
        x += (w - max_width) // 2
        w = max_width
    return x, y, w, h


def extract_from_canvas_rect(
    image: np.ndarray,
    record: dict[str, Any],
    canvas_rect: tuple[int, int, int, int],
) -> np.ndarray:
    rx, ry, _, _ = pasted_rect(record)
    x, y, w, h = canvas_rect
    ix0 = x - rx
    iy0 = y - ry
    ix1 = ix0 + w
    iy1 = iy0 + h
    if ix0 < 0 or iy0 < 0 or ix1 > image.shape[1] or iy1 > image.shape[0]:
        return np.empty((0, 0), dtype=image.dtype)
    return image[iy0:iy1, ix0:ix1]


def sat_mask(patch: np.ndarray) -> np.ndarray | None:
    """贴顶像素及其 3x3 邻域。没饱和时返回 None。

    stitch0905 坑2：现场用 std 剖面配准时，过曝饱和块因纹理被抹平而被当成"空白"，
    剖面完全失真。本文件的窗口特征走 Sobel 幅值，饱和块内部梯度为 0，但**它的边界会
    造出假强边**（硬裁切），所以连邻域一起掩。只处理 8bit 图（float 里没有 250 这个概念）。"""
    if patch.size == 0 or patch.dtype != np.uint8:
        return None
    m = patch >= SAT_THRESH
    if not m.any():
        return None
    return cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def sat_share(patch: np.ndarray) -> float:
    m = sat_mask(patch)
    return 0.0 if m is None else float(m.mean())


def normalize_feature(patch: np.ndarray) -> np.ndarray | None:
    if patch.size == 0:
        return None
    # Sobel reads uint8 directly (verified bit-identical to the float32 path) which
    # avoids a 4x-bigger float32 copy of every window patch.
    src = patch if patch.dtype == np.uint8 else patch.astype(np.float32)
    gx = cv2.Sobel(src, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(src, cv2.CV_32F, 0, 1, ksize=3)
    feature = cv2.magnitude(gx, gy)
    m = sat_mask(patch) if SAT_MASK_ON else None
    if m is not None and m.shape == feature.shape:
        keep = ~m
        if int(keep.sum()) < max(int(0.25 * feature.size), 64):
            return None                 # 基本全饱和，没有可用纹理，当不可信处理
        # 用非饱和区的均值填充，而不是置 0：置 0 会在掩膜边界自己造出一圈假边缘
        feature = np.where(m, float(np.mean(feature[keep])), feature)
    feature -= float(np.mean(feature))
    std = float(np.std(feature))
    if std < 1e-3:
        return None
    return feature / std


def peak_margin(fa: np.ndarray, fb: np.ndarray, dx: float, dy: float) -> dict[str, Any]:
    """相关面上的旁峰诊断（stitch0905 坑3/5：全局峰在周期图案上会选到假峰，
    不报峰高与旁峰距离就没法区分"真位移小"和"锁到了旁峰"）。

    只当诊断：cv2.phaseCorrelate 自带汉宁窗，这里的归一化互功率谱没开窗，所以上面的
    峰位与高度与 cv2 的会差零点几 px；看的是"旁峰有多近"这个形状，不是取它的位移。
    """
    h, w = fa.shape
    r = np.fft.rfft2(fa) * np.conj(np.fft.rfft2(fb))
    surf = np.fft.irfft2(r / (np.abs(r) + 1e-12), s=(h, w))
    iy, ix = int(round(dy)) % h, int(round(dx)) % w
    main = float(surf[iy, ix])
    s = surf.copy()
    # 抑制主峰附近 ±4px 邻域。必须用环绕索引逐个置，切片写法在峰靠边界时不会跨边界，
    # 会漏掉真正的邻域、把主峰自己当成旁峰（报出 rival_dist=0 就是这个 bug）。
    for oy in range(-4, 5):
        for ox in range(-4, 5):
            s[(iy + oy) % h, (ix + ox) % w] = -np.inf
    jy, jx = (int(i) for i in np.unravel_index(int(np.argmax(s)), s.shape))
    rival = float(s[jy, jx])
    drow, dcol = min(abs(jy - iy), h - abs(jy - iy)), min(abs(jx - ix), w - abs(jx - ix))
    ratio = rival / main if main > 1e-9 else float("nan")
    near = bool(ratio >= PEAK_RIVAL_FRAC)                # 旁峰真成才报距离
    return {"peak_strength": round(main, 4),
            "rival_ratio": round(ratio, 3) if np.isfinite(ratio) else None,
            "rival_dist_px": round(float(np.hypot(drow, dcol)), 2) if near else None}


def phase_one(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    fa = normalize_feature(a)
    fb = normalize_feature(b)
    if fa is None or fb is None:
        return float("nan"), float("nan"), float("nan")
    (dx, dy), response = cv2.phaseCorrelate(fa, fb)
    return float(dx), float(dy), float(response)


def band_label(window_index: int, count: int) -> str:
    frac = (window_index + 0.5) / count
    if frac < 1.0 / 3.0:
        return "left"
    if frac < 2.0 / 3.0:
        return "center"
    return "right"


def transition_label(a: dict[str, Any], b: dict[str, Any]) -> str:
    return f"{'T' if a['direction'] else 'F'}->{'T' if b['direction'] else 'F'}"


def _measure_one_window(
    img_a: np.ndarray, img_b: np.ndarray,
    a: dict[str, Any], b: dict[str, Any],
    rect: tuple[int, int, int, int], window_index: int,
    ox: int, oy: int, ow: int, oh: int,
) -> dict[str, Any] | None:
    """Phase correlation of one overlap window; pure function of its patches."""
    patch_a = extract_from_canvas_rect(img_a, a, rect)
    patch_b = extract_from_canvas_rect(img_b, b, rect)
    if patch_a.size == 0 or patch_b.size == 0:
        return None
    # 自己展开 phase_one，因为下面的旁峰/退化诊断要复用同一对特征图
    fa, fb = normalize_feature(patch_a), normalize_feature(patch_b)
    if fa is None or fb is None:
        dx = dy = response = float("nan")
    else:
        (dx, dy), response = cv2.phaseCorrelate(fa, fb)
    diag: dict[str, Any] = {"sat_frac": round(max(sat_share(patch_a), sat_share(patch_b)), 4)}
    if fa is not None and fb is not None and np.isfinite(dx) and np.isfinite(dy):
        diag.update(peak_margin(fa, fb, float(dx), float(dy)))
        # 坑4：无图案处信号就是灯光强度包络（左右对称的钟形），翻转模板与正向响应同分，
        # 那是退化不是匹配。多做一次翻转相关只为把它标出来。
        fbf = normalize_feature(np.ascontiguousarray(patch_b[:, ::-1]))
        if fbf is not None:
            (_, _), resp_flip = cv2.phaseCorrelate(fa, fbf)
            diag["response_flip"] = round(float(resp_flip), 4)
            diag["degenerate"] = int(abs(float(resp_flip) - float(response))
                                     <= DEGENERATE_TIE * abs(float(response)))
    diag.setdefault("rival_dist_px", None)
    diag.setdefault("rival_ratio", None)
    diag.setdefault("peak_strength", None)
    diag.setdefault("response_flip", None)
    diag.setdefault("degenerate", 0)
    # Lane-direction (dx) localizability. `phase_response` is a single scalar for the
    # whole 2-D peak, so a window full of strokes running ALONG the lane scores high on
    # it while carrying almost no information about a lane-direction shift - which is how
    # a white-paper line target lets a 1 px dx error through. Structure across the lane
    # axis (line ends, stroke edges) is what actually pins dx down, so measure it.
    gx = np.abs(np.diff(patch_a.astype(np.float32), axis=1))
    gy = np.abs(np.diff(patch_a.astype(np.float32), axis=0))
    lane_grad = float(gx.mean()) if gx.size else 0.0
    scan_grad = float(gy.mean()) if gy.size else 0.0
    return {
        "pair": f"{int(a['index'])}_{int(b['index'])}",
        "a_index": int(a["index"]),
        "b_index": int(b["index"]),
        "transition": transition_label(a, b),
        "window_index": int(window_index),
        "final_x_band": band_label(window_index, WINDOW_COUNT),
        "phase_dx_px_pre_rotation": dx,
        "phase_dy_px_pre_rotation": dy,
        "phase_response": response,
        "lane_grad": lane_grad,
        "scan_grad": scan_grad,
        "overlap_w": int(ow),
        "overlap_h": int(oh),
        "a_canvas_x": int(a["canvas_x"]),
        "a_canvas_y": int(a["canvas_y"]),
        "b_canvas_x": int(b["canvas_x"]),
        "b_canvas_y": int(b["canvas_y"]),
        **diag,                      # stitch0905 的诊断量（sat_frac / 旁峰 / 翻转同分）
    }


def measure_adjacent_pair(
    cache: Any,
    a: dict[str, Any],
    b: dict[str, Any],
) -> list[dict[str, Any]]:
    overlap = intersect_rect(pasted_rect(a), pasted_rect(b))
    if overlap is None:
        return []
    ox, oy, ow, oh = center_limited_overlap(overlap)
    _t = time.perf_counter()
    img_a = cache.get(a)
    img_b = cache.get(b)
    _tick("cache_get", time.perf_counter() - _t)
    tasks = []
    for window_index in range(WINDOW_COUNT):
        y0 = int(round(oh * window_index / WINDOW_COUNT))
        y1 = int(round(oh * (window_index + 1) / WINDOW_COUNT))
        if y1 - y0 < MIN_WINDOW_H:
            continue
        rect = (ox, oy + y0, ow, y1 - y0)
        tasks.append((rect, window_index))
    _t = time.perf_counter()
    runner = getattr(cache, "run_windows", None)
    if runner is not None:
        # shm backend: window phase correlation in a process pool over zero-copy strips
        rows = runner(a, b, tasks, ox, oy, ow, oh)
    elif _WINDOW_POOL is not None and len(tasks) > 1:
        rows = list(_WINDOW_POOL.map(
            lambda t: _measure_one_window(img_a, img_b, a, b, t[0], t[1], ox, oy, ow, oh),
            tasks))
    else:
        rows = [_measure_one_window(img_a, img_b, a, b, t[0], t[1], ox, oy, ow, oh)
                for t in tasks]
    _tick("windows", time.perf_counter() - _t)
    return [row for row in rows if row is not None]



def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError(f"No rows to write: {path}")
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)



WINDOW_COUNT = 7
MIN_RESPONSE = 0.12
MAX_ABS_PHASE = 20.0
MAX_LOCAL_CORRECTION_PX = 4.0
CHUNK_ROWS = 512

# ── stitch0905 加固：饱和掩蔽 / 旁峰裕度 / 翻转同分 ─────────────────────
# 默认值都设计成"不改变现有数值"：三个新门都是记录不拒绝（坑: 该不该拒需要数据定）。
SAT_THRESH = 250             # uint8 贴顶阈值（文档要求先掩掉 >250 的饱和像素）
SAT_MASK_ON = False          # 默认关：默认数值与上游完全一致（已逐位验），要试加 --sat-mask
# 窗口测量跑在**进程池**里，不会看到主进程里改的全局；用环境变量把它带进子进程
# （Windows 是 spawn，子进程重导入本模块时会读到继承的 env）。
if os.environ.get("STITCH_SAT_MASK") == "1":
    SAT_MASK_ON = True
MAX_SAT_FRAC = 1.0           # 窗内饱和比例上限，>此值不计入中位数；1.0=不启用
GATE_PEAK_MARGIN_PX = 0.0    # 旁峰距离小于此值判不可信；0=不启用（只报）
REJECT_DEGENERATE = False    # 翻转同分的窗是否拒绝
DEGENERATE_TIE = 0.02        # 翻转与正向响应之差小于主响应的这个比例 => 退化
PEAK_RIVAL_FRAC = 0.7        # 旁峰达到主峰这个比例才报（否则认为是噪声起伏）


def _row_float(row: dict[str, Any], key: str, default: float) -> float:
    try:
        v = row.get(key, default)
        return default if v in ("", None) else float(v)
    except (TypeError, ValueError):
        return default


def valid_phase(row: dict[str, Any]) -> bool:
    response = float(row["phase_response"])
    dx = float(row["phase_dx_px_pre_rotation"])
    dy = float(row["phase_dy_px_pre_rotation"])
    if not (response >= MIN_RESPONSE and abs(dx) <= MAX_ABS_PHASE and abs(dy) <= MAX_ABS_PHASE):
        return False
    # stitch0905 坑2/3/4 的三个新门。默认阈值都等于"不启用"，所以默认行为与上游一致；
    # 但诊断量已经写进 CSV，要打开哪个门可以用同一份数据直接对比。
    if _row_float(row, "sat_frac", 0.0) > MAX_SAT_FRAC:
        return False
    margin = _row_float(row, "rival_dist_px", 9e9)
    if GATE_PEAK_MARGIN_PX > 0 and margin < GATE_PEAK_MARGIN_PX:
        return False
    if REJECT_DEGENERATE and _row_float(row, "degenerate", 0.0) >= 1.0:
        return False
    return True



def smooth_window_values(values: list[float]) -> list[float]:
    if len(values) != WINDOW_COUNT:
        raise ValueError(values)
    result: list[float] = []
    for i, value in enumerate(values):
        neighbors = [value]
        if i > 0:
            neighbors.append(values[i - 1])
        if i + 1 < len(values):
            neighbors.append(values[i + 1])
        result.append(float(sum(neighbors) / len(neighbors)))
    return result


def warp_strip_local_y(image: np.ndarray, window_corrections: list[float]) -> np.ndarray:
    """Apply y shift varying along image rows; positive values move content down."""
    height, width = image.shape[:2]
    smoothed = smooth_window_values(window_corrections)
    knots_y = np.linspace(0.0, float(height - 1), num=WINDOW_COUNT, dtype=np.float32)
    knots_delta = np.asarray(smoothed, dtype=np.float32)
    x_base = np.arange(width, dtype=np.float32)[None, :]
    warped = np.empty_like(image)
    for y0 in range(0, height, CHUNK_ROWS):
        y1 = min(height, y0 + CHUNK_ROWS)
        y_coords = np.arange(y0, y1, dtype=np.float32)
        delta = np.interp(y_coords, knots_y, knots_delta).astype(np.float32)
        map_x = np.repeat(x_base, y1 - y0, axis=0)
        map_y = np.repeat((y_coords[:, None] - delta[:, None]).astype(np.float32), width, axis=1)
        warped[y0:y1] = cv2.remap(
            image,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    return warped


class GpuWarp:
    """Row-shift warp on the GPU: map_x is the identity and map_y = y - delta(y), so a
    single grid_sample over the whole strip replaces the chunked cv2.remap. Bilinear
    with zeros padding matches the CPU path's semantics; fixed-point vs float
    interpolation leaves differences of at most 1-2 gray levels on the final canvas
    (placement decisions are made before the warp and are unaffected)."""

    def __init__(self) -> None:
        import os
        os.environ.setdefault("CUDA_CACHE_PATH",
                              str(Path(__file__).resolve().parent / ".nv_cache"))
        # numpy/cv2/scipy (MKL) and torch each bundle an OpenMP runtime; loading both
        # in one process aborts with "OMP Error #15". The duplicate-runtime env var is
        # the standard workaround; safe here because the pools' workers never load torch.
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        import torch
        self.torch = torch
        self.device = torch.device("cuda")
        torch.cuda.init()

    def __call__(self, image: np.ndarray, window_corrections: list[float]) -> np.ndarray:
        torch = self.torch
        height, width = image.shape[:2]
        smoothed = smooth_window_values(window_corrections)
        knots_y = np.linspace(0.0, float(height - 1), num=WINDOW_COUNT, dtype=np.float32)
        delta = np.interp(np.arange(height, dtype=np.float32),
                          knots_y, np.asarray(smoothed, dtype=np.float32)).astype(np.float32)
        src_y = (np.arange(height, dtype=np.float32) - delta).astype(np.float32)
        # build the sampling grid on the GPU: a (H, W, 2) float32 grid is ~0.5 GB and
        # building it in numpy would dominate the whole warp
        t_delta = torch.from_numpy(delta).to(self.device)
        t_rows = torch.arange(height, device=self.device, dtype=torch.float32)
        t_src_y = t_rows - t_delta
        gy = (2.0 * t_src_y + 1.0) / height - 1.0            # (H,)
        gx = (2.0 * torch.arange(width, device=self.device, dtype=torch.float32) + 1.0) / width - 1.0
        grid = torch.empty((height, width, 2), device=self.device, dtype=torch.float32)
        grid[..., 1] = gy[:, None]
        grid[..., 0] = gx[None, :]
        t_img = torch.from_numpy(np.ascontiguousarray(image)).to(self.device).float()[None, None]
        out = torch.nn.functional.grid_sample(
            t_img, grid[None], mode="bilinear", padding_mode="zeros", align_corners=False)
        return out.squeeze().round().clamp(0, 255).to(torch.uint8).cpu().numpy()


_GPU_WARP: GpuWarp | None = None


def warp_strip(image: np.ndarray, window_corrections: list[float]) -> np.ndarray:
    if _GPU_WARP is not None:
        return _GPU_WARP(image, window_corrections)
    return warp_strip_local_y(image, window_corrections)


def warp_strip_local_x(image: np.ndarray, window_corrections: list[float]) -> np.ndarray:
    """车道向(axis 1)平移, 平移量沿扫描轴(axis 0)变化; 正值把内容往右推。

    `warp_strip_local_y` 的镜像: 那边 map_y = y - delta(y)、map_x 恒等; 这边
    map_x = x - delta(y)、map_y 恒等。

    为什么需要它: 逐窗相位相关实测缝的车道向误差沿列方向极差 0.75~1.63 px
    (缝 2_3 从 +0.08 到 +0.83, 缝 6_7 达 1.63)。扫描向一直有这套 7 窗局部修正兜着,
    车道向却只有一个标量 `refine_x` —— 闭环把均值调到 0, 沿列不均匀原封不动留在缝上,
    在极差最大的那一列就看得见。这是纹理无关的测量, 布料上同样成立。

    边界用 BORDER_REPLICATE: 缝在条带内部, 复制边列不会影响它。
    """
    height, width = image.shape[:2]
    smoothed = smooth_window_values(window_corrections)
    knots_y = np.linspace(0.0, float(height - 1), num=WINDOW_COUNT, dtype=np.float32)
    knots_delta = np.asarray(smoothed, dtype=np.float32)
    x_base = np.arange(width, dtype=np.float32)[None, :]
    warped = np.empty_like(image)
    for y0 in range(0, height, CHUNK_ROWS):
        y1 = min(height, y0 + CHUNK_ROWS)
        y_coords = np.arange(y0, y1, dtype=np.float32)
        delta = np.interp(y_coords, knots_y, knots_delta).astype(np.float32)
        map_x = np.repeat(x_base, y1 - y0, axis=0) - delta[:, None]
        map_y = np.repeat(y_coords[:, None], width, axis=1)
        warped[y0:y1] = cv2.remap(
            image, map_x, map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    return warped


def shift_strip_lane(image: np.ndarray, frac: float) -> np.ndarray:
    """Sub-pixel translation along the lane axis (axis 1); positive moves content right.

    The y chain has had sub-pixel placement all along (`canvas_y_frac_px` folded into the
    local-pose warp), but x was quantised to whole columns, so every seam kept up to
    0.5 px of pure rounding error. That is what is left at seam 4_5 once the constants and
    the feedback have done their part, and no measurement can remove it.

    A pure translation needs only a 1-D lerp between two neighbouring columns, so this is
    much cheaper than a general remap. |frac| <= 0.5 here (the integer part is already in
    `canvas_x`), and the edge column is replicated - the seam sits in the interior.
    """
    if abs(frac) < 1e-3:
        return image
    out = np.empty_like(image)
    w = abs(float(frac))
    for y0 in range(0, image.shape[0], CHUNK_ROWS):
        y1 = min(image.shape[0], y0 + CHUNK_ROWS)
        block = image[y0:y1].astype(np.float32)
        if frac > 0.0:                      # content right: sample from j-1
            other = np.empty_like(block)
            other[:, 1:] = block[:, :-1]
            other[:, 0] = block[:, 0]
        else:                               # content left: sample from j+1
            other = np.empty_like(block)
            other[:, :-1] = block[:, 1:]
            other[:, -1] = block[:, -1]
        np.clip(block * (1.0 - w) + other * w + 0.5, 0, 255, out=block)
        out[y0:y1] = block.astype(image.dtype)
    return out


def stitch_with_local_pose(
    records: list[dict[str, Any]],
    true_calibration: Any,
    false_calibration: Any,
    strip_corrections: dict[int, list[float]],
    output_tif: Path,
) -> None:
    canvas_width = max(int(record["canvas_x"]) + int(record["paste_width"]) for record in records)
    canvas_height = max(int(record["canvas_y"]) + int(record["corrected_height"]) for record in records)
    canvas = Image.new("L", (canvas_width, canvas_height), 0)
    for record in records:
        corrected = rectify_and_orient(
            str(record["path"]),
            bool(record["direction"]),
            true_calibration,
            false_calibration,
        )
        index = int(record["index"])
        corrected = warp_strip_local_y(corrected, strip_corrections.get(index, [0.0] * WINDOW_COUNT))
        image = Image.fromarray(corrected)
        seam_inset = int(record["seam_inset_px"])
        if seam_inset > 0:
            cropped = image.crop((0, 0, image.width - seam_inset, image.height))
            image.close()
            image = cropped
        canvas.paste(image, (int(record["canvas_x"]), int(record["canvas_y"])))
        image.close()
        del corrected
    if ROTATE_FINAL_CCW_90:
        rotated = canvas.transpose(Image.Transpose.ROTATE_90)
        canvas.close()
        canvas = rotated
    output_tif.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_tif, compression="tiff_lzw", dpi=(300, 300))
    canvas.close()




# ============================================================================
# input discovery: acquisition folder -> metadata + frame paths
# ============================================================================

INFO_JSON_NAMES = ("LocalImageInfos.json", "ImageInfos.json", "localimageinfos.json")


def discover_info_json(data_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    for name in INFO_JSON_NAMES:
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    matches = sorted(data_dir.glob("*mageInfos*.json"))
    if matches:
        return matches[0]
    raise SystemExit(
        f"no image-info JSON in {data_dir}. The acquisition software writes "
        f"LocalImageInfos.json next to the frames; pass --json to point at it."
    )


def resolve_image_path(data_dir: Path, entry: dict[str, Any], index: int) -> str:
    """Find this frame's file inside the acquisition folder.

    The JSON records the path from the machine that captured it, which is meaningless on
    another host, so the file NAME is what gets used. Everything is resolved against
    --data-dir.
    """
    recorded = str(entry.get("ImagePath") or "")
    name = Path(recorded.replace("\\", "/")).name or f"{index}.tif"
    relative = recorded.replace("\\", "/").lstrip("/")
    for candidate in (
        data_dir / "Images" / name,
        data_dir / name,
        data_dir / relative if relative else data_dir,
        Path(os.path.normpath(recorded.replace("\\", os.sep))) if recorded else data_dir,
    ):
        if candidate.is_file():
            return str(candidate.resolve())
    raise SystemExit(
        f"frame {index} not found: looked for '{name}' in {data_dir} and {data_dir / 'Images'}"
    )


def last_available_index(data_dir: Path, all_info: list[dict[str, Any]]) -> int:
    """Highest index whose file is actually on disk - lets --end default to 'everything'."""
    last = -1
    for index in range(len(all_info)):
        try:
            resolve_image_path(data_dir, all_info[index], index)
        except SystemExit:
            break
        last = index
    if last < 1:
        raise SystemExit(f"need at least 2 frames in {data_dir}, found {last + 1}")
    return last


# ============================================================================
# streaming stitcher
# ============================================================================

# buffer growth in x, in pixels; ~8 strips per reallocation
X_GROW_CHUNK = 8192
# fixed head/tail room in y.
# 注意：y 的摆放用的是【绝对 MSP / D_MSP_Y】，没有减去机器 X 轴零点，所以机器的
# X 原点一漂，整批条带就一起上移/下移，直接吃这块余量。
# 实测（_diag/diag_msp_repair.py）：strip 0 的 MSP=0 会被修复、并按 "MSP=0" 定位，
# 而其余条带用真实 MSP 定位 —— 两者天然差 standard_msp/D_MSP_Y（约 2908 px，
# True 向）和约 3693 px（False 向）。也就是说 Y_MARGIN=4096 时实际只剩约 400 px
# 余量。2026-09-12 现场机器 X 零点比标定条件高了 499,880 单位（≈590 px），
# strip 1 落到 row=-271 直接越界停机。
# 加大到 8192 后可容忍约 4500 px（≈380 mm）的 X 零点漂移。
# 已验证：只改这个值，同一数据集产出的带**逐字节相同**（摆放与缝质量不受影响），
# 代价是 buffer 高度 38977 -> 47169 行（约 +70 MB）。
Y_MARGIN = 8192

# a pair whose residual exceeds this is treated as a failed measurement and the model
# carries the strip instead. This is what replaces `search_reset_offset()`.
MAX_TRUSTED_RESIDUAL_PX = 2.5
# 车道向逐窗修正: 固定项 vs 差分链的判据。
# 实测依据(diag_window_chain.py): y 链各窗口偏差同号率只有 57%、均值近 0, 所以累积
# 等价于取平均、天然有界(<=1.06px)。x 的 w6 偏差 7 对全部同号、均值 +0.47, 线性累积
# 冲到 3.27px 逼近 ±4 上限, 成图反而变差 —— 因为它是**每条带共有的固有畸变**
# (扫描行程末端的横向漂移, w6 中心列 28657 正好覆盖标定板上实测漂移的 col 29112~29348),
# 该按绝对量修一次, 不该当条带间差分累积。
X_WINDOW_MIN_OBS = 3          # 样本不足时保守走差分链(与原行为一致)
X_WINDOW_SAME_SIGN = 0.8      # 同号率门槛
X_WINDOW_SIGNIF = 1.5         # |均值| 要大于这个倍数的标准误才算显著
MIN_TRUSTED_WINDOWS = 3

# Online skew fit. The machine's angle is NOT a constant to hard-code - another machine has
# another one, and even this one drifts with the calibration. Every trusted pair contributes
# one observation of
#     dy = s * u + A * sigma        u = -(raw_x_b - raw_x_a),  sigma = +-1 by transition
# and the model is refitted after each pair, so the placement gets better as the roll runs.
# Both transitions must have been seen, otherwise s and A are not separable.
SKEW_FIT_MIN_PAIRS = 4
# 下界原来取 1.0e-3：那等于先假定"机器一定有 0.06~0.34 度的斜切"。可标定一旦自己带了
# cross_term，在线需要学的只剩零点几分之一毫弧度（实测 1.3e-4），会被这道门判成"不合理"
# 而整批拒掉，剩下那 0.007 度就永远修不掉。放到允许接近 0/轻度反号，上限不变。
SKEW_S_PLAUSIBLE_RANGE = (-2.0e-3, 6.0e-3)

# Loop closure. After the seam inset strip i still overlaps i+2 by ~316 px, which is a second
# independent constraint on the same strip. Placing b against BOTH b-1 and b-2 keeps the
# residual chain from being a pure random walk. The i,i+2 overlap is ~3.6x narrower than the
# adjacent one, so it gets a smaller weight.
LOOP_CLOSURE_WEIGHT = 0.5

# Cold start values, used only until the online fit has enough pairs. They are a plausible
# machine, NOT a calibration: any real number here is replaced by the fitted one within a few
# strips, and whatever error they carry is absorbed by that strip's own residual.
COLD_START_SKEW_S = 3.2376e-3
COLD_START_ANTISYM = 0.0




class CausalViolation(RuntimeError):
    """Raised when the streaming code reads metadata of a strip that has not arrived."""


class CausalInfoFeed:
    """Metadata of arrived strips only. Reading ahead raises instead of silently working."""

    def __init__(self, all_info: list[dict[str, Any]]) -> None:
        self._all = all_info
        self._arrived = 0

    def arrive(self, index: int) -> dict[str, Any]:
        if index != self._arrived:
            raise CausalViolation(f"strips must arrive in order; expected {self._arrived}, got {index}")
        self._arrived = index + 1
        return self._all[index]

    @property
    def arrived(self) -> int:
        return self._arrived

    def history(self) -> list[tuple[int, dict[str, Any]]]:
        return [(i, self._all[i]) for i in range(self._arrived)]

    def __getitem__(self, index: int) -> dict[str, Any]:
        if index >= self._arrived:
            raise CausalViolation(f"strip {index} has not arrived (arrived: {self._arrived})")
        return self._all[index]


def same_direction_valid_history(
    history: list[tuple[int, dict[str, Any]]],
    target_index: int,
    target_direction: bool,
) -> list[dict[str, Any]]:
    """Arrived strips of the same direction whose MSP can be trusted."""
    return [
        {"idx": idx,
         "step": float(item["Info"]["Step"]),
         "msp": float(item["Info"]["MotionStartPoint"])}
        for idx, item in history
        if idx != target_index
        and bool(item["Info"]["Direction"]) == target_direction
        and is_valid_msp(float(item["Info"]["MotionStartPoint"]))
    ]


def infer_standard_msp_causal(
    history: list[tuple[int, dict[str, Any]]],
    target_index: int,
    target_step: float,
    target_direction: bool,
) -> tuple[float, str, list[int]]:
    """Estimate a missing MSP from arrived strips only.

    The batch version interpolates between the nearest valid same-direction neighbour on
    each side. For an interior strip such as 28 the left side alone is enough. For strip 0
    there is no left side at all, which is why placement is held until two same-direction
    strips have arrived (see `StreamingStitcher.can_place`) - then this extrapolates
    backwards along the Step axis.
    """
    candidates = same_direction_valid_history(history, target_index, target_direction)
    if len(candidates) < 2:
        raise RuntimeError(
            f"MSP of {target_index}.tif needs 2 arrived same-direction strips, have {len(candidates)}"
        )
    candidates.sort(key=lambda item: abs(float(item["step"]) - target_step))
    a, b = candidates[0], candidates[1]
    if abs(a["step"] - b["step"]) < 1e-12:
        estimated = 0.5 * (a["msp"] + b["msp"])
    else:
        slope = (b["msp"] - a["msp"]) / (b["step"] - a["step"])
        estimated = a["msp"] + slope * (target_step - a["step"])
    sources = [int(a["idx"]), int(b["idx"])]
    return float(estimated), f"causal Step extrapolation from {sources[0]}.tif and {sources[1]}.tif", sources


class StreamingStitcher:
    """Places, measures and pastes one strip at a time. No lookahead anywhere."""

    def __init__(
        self,
        data_dir: Path,
        feed: CausalInfoFeed,
        true_calibration: Any,
        false_calibration: Any,
        true_yaml: Path,
        false_yaml: Path,
        skew_s: float,
        antisym: float,
        subpixel: bool = True,
        online_fit: bool = True,
        loop_closure: bool = True,
        feedback: bool = True,
        nominal_scale: bool = False,
        rectified_cache: Any = None,
        x_feedback: bool = False,
        x_loop_mode: str = "adjacent-first",
        x_gate_lane_grad: float = 0.0,
        x_window_top_half: bool = True,
        subpixel_x: bool = True,
        x_local_pose: bool = True,
        x_gain: float = 1.0,
        seam_inset_px: int = SEAM_INSET_PX,
    ) -> None:

        self.data_dir = Path(data_dir)
        self.feed = feed
        self.true_calibration = true_calibration
        self.false_calibration = false_calibration
        self.true_yaml = Path(true_yaml)
        self.false_yaml = Path(false_yaml)
        self.skew_s = float(skew_s)
        self.antisym = float(antisym)
        self.skew_prior = (float(skew_s), float(antisym))
        self.online_fit = bool(online_fit)
        self.loop_closure = bool(loop_closure)
        # `feedback=False` reproduces the field version's placement policy: the strip goes
        # where the encoders say and is never measured against its neighbour, so neither the
        # rigid refine nor the per-window field exists.
        self.feedback = bool(feedback)
        # Lane-direction (x) feedback: the x placement is encoder dead-reckoning
        # (Step / d_step_x + direction offset); its per-pair random residual (encoder
        # jitter + calibration local error) is measured by the same trusted windows
        # that already feed the y chain and corrected into the NEXT strip, mirroring
        # `refine_y`. x stays integer - there is no sub-pixel x warp - so the residual
        # after correction is bounded by quantization (<=0.5 px) + measurement noise.
        self.x_feedback = bool(x_feedback)
        self.x_loop_mode = str(x_loop_mode)
        self.x_gate_lane_grad = float(x_gate_lane_grad)
        self.x_window_top_half = bool(x_window_top_half)
        self.subpixel_x = bool(subpixel_x)
        self.x_local_pose = bool(x_local_pose)
        # 闭环增益。代码假定"量到多少就修多少"(gain=1), 但这个假定从没被成图验证过。
        # 若画布上残余的缝误差与所施加的修正成比例且比例不是 1, 那增益本身就是要找的
        # 那个参数 —— 扫一遍 gain 可以直接量出闭环的真实增益, 而不是继续猜。
        # 注意: 只缩放**施加**的量, `measured_dx_px` 仍写裸测量值, 两者分开才能事后回归。
        self.x_gain = float(x_gain)
        # Where the cut between adjacent strips falls, counted back from the strip's
        # trailing lane edge. 256 puts the seam at lane y 99.72 mm - right ON the
        # calibration support boundary (100.0), so the 256 px beyond it are pure linear
        # extrapolation in BOTH directions and any change to the edge slope is levered
        # by 21.87 mm (see README 5.9.5: a 0.098 px/mm slope change moved the seam by
        # 2.1 px). Raising the inset moves the cut deeper into the measured band.
        self.seam_inset_px = max(0, int(seam_inset_px))

        self.refine_x = 0.0
        self.d_step_x = K_COEF_ACTIVE if nominal_scale else D_STEP_X
        self.d_msp_y = K_COEF_ACTIVE if nominal_scale else D_MSP_Y
        self.nominal_scale = bool(nominal_scale)
        # (u, sigma, model-free dy) of every trusted pair seen so far
        self.fit_observations: list[tuple[float, float, float]] = []
        self.fit_source = "prior"
        # sub-pixel paste: `canvas_y` stays the integer paste row, and the fractional part of
        # the placement is handed to `warp_strip_local_y` as a uniform y shift. Without it the
        # placement is quantised to whole rows and every strip throws away up to 0.5 px, which
        # is the only thing left explaining the residual chain's -3.6 px accumulation.
        self.subpixel = bool(subpixel)
        self.true_shape = target_grid_shape(true_calibration)
        self.false_shape = target_grid_shape(false_calibration)
        # b, b-1 and b-2 are all needed while a strip is being placed (adjacent pair plus the
        # i,i+2 loop closure), and the paste reuses the same cached image
        self.cache = rectified_cache if rectified_cache is not None else RectifiedImageCache(
            true_calibration, false_calibration, max_size=4)

        self.start_index: int | None = None
        self.step_ref: float | None = None
        self.previous: dict[str, Any] | None = None
        self.grandparent: dict[str, Any] | None = None
        self.model_y = 0.0
        self.refine_y = 0.0
        self.window_correction = [0.0] * WINDOW_COUNT
        # 车道向的逐窗修正, 与上面那条 y 链完全对称。见 warp_strip_local_x 的说明。
        self.window_correction_x = [0.0] * WINDOW_COUNT
        # 逐窗观测历史, 用来在线判定"固定项 / 差分链"
        self.x_window_obs: dict[int, list[float]] = {w: [] for w in range(WINDOW_COUNT)}
        self.x_window_mode: list[str] = ["chain"] * WINDOW_COUNT

        self._buffer: np.ndarray | None = None
        self._x_of_col0 = 0.0
        self._y_of_row0 = 0.0
        self._min_col: int | None = None
        self._max_col: int | None = None
        self._min_row: int | None = None
        self._max_row: int | None = None

        self.records: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.residual_rows: list[dict[str, Any]] = []
        self.loop_rows: list[dict[str, Any]] = []

        # ---- lane-offset (T/F) online observation ----
        # The i,i+2 loop pair is SAME-direction, so its dx carries no information about
        # the T/F lane-origin difference; only the adjacent pair sees it. Collect the
        # adjacent dx split by seam type so the run can report what the two x constants
        # should have been. Keyed by the arriving strip's direction: False = a T->F seam.
        self.x_seam_obs: dict[bool, list[float]] = {True: [], False: []}
        self.x_seam_scale: list[float] = []

    def x_constant_refit(self) -> dict[str, Any]:
        """Re-fit the two lane-direction constants from this run's own seam measurements.

        With the adjacent correction applied in full, each trusted `adjacent_dx` is the
        model error of that one link, so the seam type separates the two constants:

            gap(T->F) = dStep/D - X_OFF      gap(F->T) = dStep/D + X_OFF

        A positive dx means the pair sits too close (the loop widens the gap), so an
        excess eps in X_OFF shows up as +eps on T->F seams and -eps on F->T seams:

            eps   = (mean dx[T->F] - mean dx[F->T]) / 2   ->  X_OFF -= eps
            delta = (mean dx[T->F] + mean dx[F->T]) / 2   ->  D    *= 1 - delta / u_bar

        `delta` is the direction-independent part, i.e. the Step scale error. Reported
        rather than applied mid-run: the per-pair feedback already removes both from the
        seams, and these numbers are what the NEXT run (or the calibration) should use so
        the open-loop fallback lands right too.
        """
        tf, ft = self.x_seam_obs[False], self.x_seam_obs[True]
        out: dict[str, Any] = {
            "d_step_x_used": float(self.d_step_x),
            "x_offset_false_used": float(X_OFFSET_FALSE_PX),
            "n_seams_t_to_f": len(tf),
            "n_seams_f_to_t": len(ft),
            "mean_dx_t_to_f_px": round(statistics.fmean(tf), 4) if tf else None,
            "mean_dx_f_to_t_px": round(statistics.fmean(ft), 4) if ft else None,
        }
        if not (tf and ft and self.x_seam_scale):
            out["status"] = "not enough trusted seams of both types"
            return out
        mean_tf, mean_ft = statistics.fmean(tf), statistics.fmean(ft)
        eps = 0.5 * (mean_tf - mean_ft)
        delta = 0.5 * (mean_tf + mean_ft)
        u_bar = statistics.fmean(self.x_seam_scale)
        out.update({
            "status": "ok",
            "direction_typed_residual_eps_px": round(eps, 4),
            "common_residual_delta_px": round(delta, 4),
            "mean_link_scale_px": round(u_bar, 3),
            "x_offset_false_refit": round(float(X_OFFSET_FALSE_PX) - eps, 4),
            "d_step_x_refit": round(float(self.d_step_x) * (1.0 - delta / u_bar), 4),
            "spread_t_to_f_px": round(max(tf) - min(tf), 4),
            "spread_f_to_t_px": round(max(ft) - min(ft), 4),
        })
        return out

    # ---------------- placement ----------------

    def _place(self, index: int, entry: dict[str, Any]) -> dict[str, Any]:
        info = entry["Info"]
        direction = bool(info["Direction"])
        step = float(info["Step"])
        original_msp = float(info["MotionStartPoint"])
        zero_msp_special = not is_valid_msp(original_msp)

        if zero_msp_special:
            standard_msp, repair_method, repair_sources = infer_standard_msp_causal(
                self.feed.history(), index, step, direction
            )
        else:
            standard_msp, repair_method, repair_sources = original_msp, "original JSON value", []

        if direction:
            corrected_height, corrected_width = self.true_shape
            yaml_used = self.true_yaml.name
            raw_y_nominal = (-standard_msp / self.d_msp_y - float(corrected_height)
                             + direction_y_offset(direction))
        else:
            corrected_height, corrected_width = self.false_shape
            yaml_used = self.false_yaml.name
            raw_y_nominal = -standard_msp / self.d_msp_y + direction_y_offset(direction)

        special_offset = (standard_msp / self.d_msp_y + float(ZERO_MSP_FINE_TUNE_PX)
                          if zero_msp_special else 0.0)
        raw_x = -(step - float(self.step_ref)) / self.d_step_x + direction_x_offset(direction)
        seam_inset = 0 if index == self.start_index else self.seam_inset_px


        record = {
            "index": index,
            "path": resolve_image_path(self.data_dir, entry, index),
            "direction": direction,
            "step": step,
            "original_msp": original_msp,
            "standard_msp": standard_msp,
            "zero_msp_special": zero_msp_special,
            "repair_method": repair_method,
            "repair_sources": repair_sources,
            "yaml_used": yaml_used,
            "corrected_width": int(corrected_width),
            "corrected_height": int(corrected_height),
            "seam_inset_px": int(seam_inset),
            "paste_width": int(corrected_width) - int(seam_inset),
            "raw_x": raw_x,
            "raw_y_nominal": raw_y_nominal,
            "special_zero_msp_offset_px": special_offset,
            "manual_y_compensation_px": float(GLOBAL_MANUAL_Y_COMPENSATION_PX),
        }
        record["filename"] = Path(record["path"]).name
        return record

    def _predicted_dy(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        u = -(float(current["raw_x"]) - float(previous["raw_x"]))
        sigma = 1.0 if not bool(current["direction"]) else -1.0
        return self.skew_s * u + self.antisym * sigma

    def _observe_and_refit(self, u: float, sigma: float, model_free_dy: float) -> None:
        """Feed one pair into the running fit of `dy = s*u + A*sigma` and refit.

        `model_free_dy` is what the pair would have measured with no model applied, i.e.
        prediction + measured residual. That reconstruction is exact because the measurement
        is linear in the placement offset with slope 1 (see `diag_offset_bias.py`).

        Nothing already pasted is revised - an improved model only makes the NEXT strips land
        closer, which is why the residuals shrink as the roll runs.
        """
        self.fit_observations.append((float(u), float(sigma), float(model_free_dy)))
        if not self.online_fit or len(self.fit_observations) < SKEW_FIT_MIN_PAIRS:
            return
        u_col = np.array([row[0] for row in self.fit_observations], dtype=float)
        sigma_col = np.array([row[1] for row in self.fit_observations], dtype=float)
        target = np.array([row[2] for row in self.fit_observations], dtype=float)
        if len(set(sigma_col.tolist())) < 2:
            self.fit_source = "prior (only one transition seen)"
            return
        solution, *_ = np.linalg.lstsq(np.column_stack([u_col, sigma_col]), target, rcond=None)
        s_fit, antisym_fit = float(solution[0]), float(solution[1])
        low, high = SKEW_S_PLAUSIBLE_RANGE
        if not (low <= s_fit <= high):
            self.fit_source = f"prior (fitted s {s_fit:+.3e} out of range)"
            return
        self.skew_s = s_fit
        self.antisym = antisym_fit
        self.fit_source = "fitted"

    def _measure_pair(
        self, a: dict[str, Any], b: dict[str, Any], b_frac: float,
    ) -> tuple[float | None, float | None, int, list[dict[str, Any]]]:
        """Median misalignment of a pair at the current sub-pixel placement.

        The patches are cut at whole-row canvas offsets, so the phase correlation describes
        the integer placement; the two fractional parts turn it into the real misalignment.
        Returns (dy_misalignment, dx_misalignment, n_valid_windows, rows). Both axes now
        carry a fractional term: the patches come from the cached rectified strips placed at
        integer canvas offsets, so neither the y warp nor the lane shift is baked in, and
        each axis needs its own `frac_gap` to become the real misalignment.
        """
        rows = measure_adjacent_pair(self.cache, a, b)
        valid = [row for row in rows if valid_phase(row)]
        if len(valid) < MIN_TRUSTED_WINDOWS:
            return None, None, len(valid), rows
        median_dy = float(statistics.median(
            float(row["phase_dy_px_pre_rotation"]) for row in valid))
        # dx uses a stricter window set: only windows with real across-lane structure can
        # localise a lane-direction shift. Below the gate the dx median is noise (measured
        # ~1 px swing between two runs of the SAME placement on this white-paper target),
        # so report None and let the caller dead-reckon instead of locking onto it.
        lane_ok = [row for row in valid
                   if float(row.get("lane_grad", 0.0)) >= self.x_gate_lane_grad]
        if self.x_window_top_half and len(lane_ok) >= 2 * MIN_TRUSTED_WINDOWS - 1:
            # Relative selection instead of an absolute floor: the useful window count
            # varies per pair, and a fixed threshold silently starves a pair that has
            # only one strong window (pair 0_1 here) while a relative one always keeps
            # the best half. Measured per-window dx tracks lane_grad closely - on pair
            # 6_7 the two high-gradient windows read +0.57/+1.29 while the three flat
            # ones read ~0, and the line-endpoint truth says +1.12.
            lane_ok = sorted(lane_ok, key=lambda r: -float(r.get("lane_grad", 0.0)))
            lane_ok = lane_ok[:max(MIN_TRUSTED_WINDOWS, (len(lane_ok) + 1) // 2)]
        median_dx: float | None = None
        if len(lane_ok) >= MIN_TRUSTED_WINDOWS:
            median_dx = float(statistics.median(
                float(row["phase_dx_px_pre_rotation"]) for row in lane_ok))
            # `a` is already placed and its lane shift is fixed; `b`'s provisional fraction
            # is whatever `_set_canvas_x` last stored. Same bookkeeping as frac_gap below.
            median_dx += (float(b.get("canvas_x_frac_px", 0.0))
                          - float(a.get("canvas_x_frac_px", 0.0)))
        frac_gap = b_frac - float(a.get("canvas_y_frac_px", 0.0))
        return median_dy + frac_gap, median_dx, len(valid), rows


    # ---------------- canvas ----------------

    def _ensure_buffer(self, record: dict[str, Any]) -> None:
        height = int(record["corrected_height"]) + 2 * Y_MARGIN
        width = int(record["paste_width"]) + X_GROW_CHUNK
        self._buffer = np.zeros((height, width), dtype=np.uint8)
        self._x_of_col0 = float(record["raw_x"])
        self._y_of_row0 = float(record["raw_y_corrected"]) - Y_MARGIN

    def _set_canvas_x(self, record: dict[str, Any]) -> int:
        """Place this strip in the lane direction, keeping the sub-pixel remainder.

        Mirror of the y placement: the integer column goes into `canvas_x`, the remainder
        into `canvas_x_frac_px`, and the remainder is applied to the pixels by
        `shift_strip_lane` just before the paste. Without it every seam keeps up to 0.5 px
        of rounding, which is the floor the constants + feedback run into.
        """
        placed = float(record["raw_x"]) + self.refine_x - self._x_of_col0
        col = int(round(placed))
        record["canvas_x"] = col
        record["canvas_x_frac_px"] = (placed - col) if self.subpixel_x else 0.0
        return col

    def _grow_left(self, needed: int) -> None:
        """Widen the buffer on the left and move every recorded column with it.

        `_x_of_col0` is the origin of the buffer, and x decreases with index, so this fires
        every ~10 strips. Everything already recorded in buffer coordinates - the placed
        records, the frame log's `buffer_col`, the residual rows - has to shift by the same
        pad, otherwise the next pair is measured against a stale column for strip index-1
        and the phase correlation collapses.
        """
        assert self._buffer is not None
        pad = needed + X_GROW_CHUNK
        grown = np.zeros((self._buffer.shape[0], self._buffer.shape[1] + pad), dtype=np.uint8)
        grown[:, pad:] = self._buffer
        self._buffer = grown
        self._x_of_col0 -= pad
        if self._min_col is not None:
            self._min_col += pad
            self._max_col = int(self._max_col) + pad
        for record in self.records:
            if "canvas_x" in record:
                record["canvas_x"] = int(record["canvas_x"]) + pad
        for frame in self.frames:
            if frame.get("buffer_col") is not None:
                frame["buffer_col"] = int(frame["buffer_col"]) + pad
        for row in self.residual_rows:
            for key in ("a_canvas_x", "b_canvas_x"):
                if key in row:
                    row[key] = int(row[key]) + pad

    def _reserve_columns(self, record: dict[str, Any]) -> None:
        """Make room for this strip before any canvas coordinate is derived from it."""
        assert self._buffer is not None
        col = int(round(float(record["raw_x"]) + self.refine_x - self._x_of_col0))
        if col < 0:
            self._grow_left(-col)


    def _paste(self, record: dict[str, Any], image: np.ndarray) -> tuple[int, int]:
        assert self._buffer is not None
        # use the canvas coords derived in push(): in sub-pixel mode the fractional part of
        # the placement has already been folded into the warp, so re-deriving the row from
        # `raw_y_corrected` here would apply it twice
        col = int(record["canvas_x"])
        row = int(record["canvas_y"])
        h, w = image.shape[:2]
        if row < 0 or row + h > self._buffer.shape[0]:
            raise RuntimeError(
                f"strip {record['index']} needs rows [{row}, {row + h}) outside the y margin; "
                f"the placement model is probably wrong"
            )
        if col + w > self._buffer.shape[1]:
            grown = np.zeros((self._buffer.shape[0], col + w + X_GROW_CHUNK), dtype=np.uint8)
            grown[:, : self._buffer.shape[1]] = self._buffer
            self._buffer = grown
        self._buffer[row : row + h, col : col + w] = image
        self._min_col = col if self._min_col is None else min(self._min_col, col)
        self._max_col = col + w if self._max_col is None else max(self._max_col, col + w)
        self._min_row = row if self._min_row is None else min(self._min_row, row)
        self._max_row = row + h if self._max_row is None else max(self._max_row, row + h)
        return col, row

    # ---------------- per-strip entry point ----------------

    def can_place(self, index: int) -> tuple[bool, str]:
        """Whether this strip can be placed with the data that has arrived.

        Only an MSP~=0 strip can be blocked, and only because repairing it needs two
        same-direction strips to define the Step->MSP slope. Strip 28 has plenty of them
        behind it; strip 0 has none, so it waits for strips 2 and 4. That is a start-up
        latency of a few frames, not a lookahead - once placed, nothing is revised.
        """
        info = self.feed[index]["Info"]
        if is_valid_msp(float(info["MotionStartPoint"])):
            return True, "MSP valid"
        candidates = same_direction_valid_history(
            self.feed.history(), index, bool(info["Direction"])
        )
        if len(candidates) >= 2:
            return True, f"MSP repairable from {[c['idx'] for c in candidates[:2]]}"
        return False, f"MSP~=0 and only {len(candidates)} same-direction strips have arrived"

    def push(self, index: int) -> dict[str, Any]:
        info = self.feed[index]
        if self.start_index is None:
            self.start_index = index
            self.step_ref = float(info["Info"]["Step"])

        record = self._place(index, info)

        predicted_dy: float | None = None
        measured_dy: float | None = None
        residual_dy = 0.0
        applied_dy = 0.0
        adjacent_dx: float | None = None
        loop_dx: float | None = None
        applied_dx = 0.0
        dx_source = "anchor"
        loop_residual: float | None = None
        loop_windows = 0
        loop_reject: str | None = None
        dy_source = "anchor"
        trusted = False
        trusted_windows = 0
        reject_reason: str | None = None
        pair_rows: list[dict[str, Any]] = []
        loop_pair_rows: list[dict[str, Any]] = []
        skew_s_used = self.skew_s
        antisym_used = self.antisym


        if self.previous is None:
            record["skew_model_y_px"] = 0.0
        else:
            predicted_dy = self._predicted_dy(self.previous, record)
            self.model_y -= predicted_dy
            record["skew_model_y_px"] = self.model_y

        record["total_y_compensation_px"] = (
            float(record["special_zero_msp_offset_px"])
            + float(record["manual_y_compensation_px"])
            + float(record["skew_model_y_px"])
        )
        record["raw_y_pre_refine"] = float(record["raw_y_nominal"]) + record["total_y_compensation_px"]
        # provisional placement: the pair is measured here, before the residual is known
        record["raw_y_corrected"] = record["raw_y_pre_refine"] + self.refine_y
        if self._buffer is None:
            self._ensure_buffer(record)
        self._reserve_columns(record)
        # provisional x: encoder dead-reckoning + the accumulated lane refine (measured
        # by the previous pair); the pair below may correct it once more
        record["canvas_x"] = int(round(float(record["raw_x"]) + self.refine_x
                                       - self._x_of_col0))
        record["canvas_x_frac_px"] = 0.0
        placed_y = float(record["raw_y_corrected"]) - self._y_of_row0
        record["canvas_y"] = int(round(placed_y))
        # where the content really sits, relative to the paste row (0 in integer mode)
        provisional_frac = (placed_y - record["canvas_y"]) if self.subpixel else 0.0
        record["canvas_y_frac_px"] = provisional_frac
        record["canvas_y_before_adjacent_refine"] = int(record["canvas_y"])

        if self.previous is not None:
            # the loop-closure pair does not depend on the adjacent result, so when a
            # pair pool exists it is measured concurrently; both window sets share the
            # same window thread pool. Results are identical to the serial order.
            loop_future = None
            if (self.loop_closure and self.grandparent is not None
                    and _PAIR_POOL is not None):
                loop_future = _PAIR_POOL.submit(
                    self._measure_pair, self.grandparent, record, provisional_frac)
            adjacent_dy, adjacent_dx, trusted_windows, pair_rows = self._measure_pair(
                self.previous, record, provisional_frac)
            if adjacent_dy is None:
                reject_reason = f"only {trusted_windows} trusted windows"
            elif abs(adjacent_dy) > MAX_TRUSTED_RESIDUAL_PX:
                reject_reason = f"residual {adjacent_dy:+.3f} px exceeds {MAX_TRUSTED_RESIDUAL_PX}"
            else:
                measured_dy = adjacent_dy
                residual_dy = adjacent_dy
                trusted = True

            # the fit only ever sees the adjacent pair, and only when it is trustworthy
            if trusted:
                self._observe_and_refit(
                    -(float(record["raw_x"]) - float(self.previous["raw_x"])),
                    1.0 if not bool(record["direction"]) else -1.0,
                    float(predicted_dy) + residual_dy,
                )

            # second constraint: this strip also overlaps the one before its neighbour
            if self.loop_closure and self.grandparent is not None:
                if loop_future is not None:
                    loop_dy, loop_dx, loop_windows, loop_pair_rows = loop_future.result()
                else:
                    loop_dy, loop_dx, loop_windows, loop_pair_rows = self._measure_pair(
                        self.grandparent, record, provisional_frac)
                if loop_dy is not None and abs(loop_dy) <= MAX_TRUSTED_RESIDUAL_PX:
                    loop_residual = loop_dy
                elif loop_dy is not None:
                    loop_reject = f"loop residual {loop_dy:+.3f} px exceeds {MAX_TRUSTED_RESIDUAL_PX}"
                else:
                    loop_reject = f"loop pair has only {loop_windows} trusted windows"
                for row in loop_pair_rows:
                    if valid_phase(row):
                        self.loop_rows.append(row)

            if trusted and loop_residual is not None:
                weight = LOOP_CLOSURE_WEIGHT
                applied_dy = (residual_dy + weight * loop_residual) / (1.0 + weight)
                dy_source = "adjacent+loop"
            elif trusted:
                applied_dy = residual_dy
                dy_source = "adjacent"
            elif loop_residual is not None:
                applied_dy = loop_residual
                dy_source = "loop"
            else:
                dy_source = "model"

            # the field version never closes the loop: the pair is still measured (the
            # residual CSV is what the evaluator derives the seam layout from) but nothing
            # is fed back into the placement
            if not self.feedback:
                applied_dy = 0.0
                dy_source = "open loop"

            self.refine_y -= applied_dy
            record["raw_y_corrected"] = record["raw_y_pre_refine"] + self.refine_y
            placed_y = float(record["raw_y_corrected"]) - self._y_of_row0
            record["canvas_y"] = int(round(placed_y))
            record["canvas_y_frac_px"] = (placed_y - record["canvas_y"]) if self.subpixel else 0.0

            # ---- lane-direction (x) feedback: mirror of the y refine chain ----
            # The x placement is pure encoder dead-reckoning, so its per-pair random
            # residual (encoder jitter + calibration local error, ~1-2 px on this
            # machine) stays in the seam forever unless measured and corrected here.
            # phase_dx comes from the SAME trusted windows that measured dy, so it
            # costs nothing extra. Corrections accumulate in refine_x and shift this
            # strip immediately (integer columns only).
            if adjacent_dx is not None and abs(adjacent_dx) <= MAX_TRUSTED_RESIDUAL_PX:
                # Record the trusted adjacent observation BEFORE any blending. With the
                # per-pair correction applied in full, each observation is that single
                # link's own model error, so the two seam types separate the Step scale
                # from the T/F lane-origin difference (see x_constant_refit()).
                self.x_seam_obs[bool(record["direction"])].append(float(adjacent_dx))
                self.x_seam_scale.append(
                    (float(self.previous["raw_x"]) - float(record["raw_x"]))
                    - (direction_x_offset(bool(self.previous["direction"]))
                       - direction_x_offset(bool(record["direction"]))))
                if (self.x_loop_mode == "blend"
                        and loop_dx is not None and abs(loop_dx) <= MAX_TRUSTED_RESIDUAL_PX):
                    applied_dx = (adjacent_dx + LOOP_CLOSURE_WEIGHT * loop_dx) / (
                        1.0 + LOOP_CLOSURE_WEIGHT)
                    dx_source = "adjacent+loop"
                else:
                    # adjacent-first: the i,i+2 loop pair is SAME-direction, so its dx is
                    # blind to the T/F lane-origin offset. Blending it in at weight 0.5
                    # dilutes the only direction-sensitive measurement to 2/3 and replaces
                    # the missing third with a term carrying no information about it - the
                    # residual then survives preferentially on the direction-crossing
                    # seams. Use the adjacent measurement alone whenever it is trusted.
                    applied_dx = adjacent_dx
                    dx_source = "adjacent"
            elif loop_dx is not None and abs(loop_dx) <= MAX_TRUSTED_RESIDUAL_PX:
                applied_dx = loop_dx
                dx_source = "loop"
            elif adjacent_dx is not None:
                dx_source = "rejected(encoder)"   # suspicious shift: keep dead-reckoning
            else:
                dx_source = "encoder"             # no trusted windows: dead-reckoning
            if not self.x_feedback:
                applied_dx = 0.0
                dx_source = "open loop"
            else:
                applied_dx *= self.x_gain
            self.refine_x -= applied_dx
            new_canvas_x = self._set_canvas_x(record)
            if new_canvas_x < 0:
                # the correction can move this strip past the reserved left edge
                self._grow_left(-new_canvas_x)
                self._set_canvas_x(record)
            record["adjacent_x_refine_px"] = self.refine_x

        record["adjacent_y_refine_px"] = self.refine_y

        # local_pose: chain the per-window residual, referenced to the final placement.
        # `moved` is how far this strip travelled after the pair was measured. In sub-pixel
        # mode the move is exact, so the window chain is left with only each window's
        # deviation from the median - the rigid part is fully absorbed by the placement.
        # Only THIS strip's move counts. The batch version also subtracts the neighbour's
        # move because both of its records were measured at the model-free placement; here
        # the neighbour was already moved before this pair was measured, so its move is baked
        # into `refine_y` and subtracting it again leaks the neighbour's residual into the
        # window chain - which then random-walks into the +-4 px clamp.
        if self.previous is not None and pair_rows:
            if self.subpixel:
                frac_gap = provisional_frac - float(self.previous.get("canvas_y_frac_px", 0.0))
                shift = frac_gap - applied_dy
            else:
                shift = float(int(record["canvas_y"])
                              - int(record["canvas_y_before_adjacent_refine"]))



            per_window: dict[int, list[float]] = {}
            for row in pair_rows:
                if not valid_phase(row):
                    continue
                enriched = dict(row)
                enriched["estimated_final_residual_pre_y_px"] = float(row["phase_dy_px_pre_rotation"]) + shift
                enriched["a_canvas_y"] = int(self.previous["canvas_y"])
                enriched["b_canvas_y"] = int(record["canvas_y"])
                self.residual_rows.append(enriched)
                per_window.setdefault(int(row["window_index"]), []).append(
                    enriched["estimated_final_residual_pre_y_px"])
            fallback = (statistics.median([v for values in per_window.values() for v in values])
                        if per_window else 0.0)
            limit = float(MAX_LOCAL_CORRECTION_PX)
            if self.feedback:
                self.window_correction = [
                    max(-limit, min(limit, self.window_correction[w]
                                    - (statistics.median(per_window[w]) if w in per_window else fallback)))
                    for w in range(WINDOW_COUNT)
                ]
        record["window_correction_px"] = list(self.window_correction)

        # ---- 车道向的逐窗链, 与上面那条 y 链逐行对应 ----
        # `_measure_pair` 已经把 (b_frac_x - a_frac_x) 加进了 median_dx, 但逐窗的
        # phase_dx 是裸值, 所以这里补同一个 frac_gap; 再减掉已经施加的 applied_dx,
        # 剩下的就是该窗口相对刚体摆放的偏差。测量时 record 的 x 小数部分还是 0
        # (由 _place 置零, _set_canvas_x 之后才写入真值), 与 _measure_pair 读到的一致。
        if self.previous is not None and pair_rows and self.x_feedback and self.x_local_pose:
            frac_gap_x = 0.0 - float(self.previous.get("canvas_x_frac_px", 0.0))
            shift_x = frac_gap_x - applied_dx
            per_window_x: dict[int, list[float]] = {}
            for row in pair_rows:
                if not valid_phase(row):
                    continue
                if float(row.get("lane_grad", 0.0)) < self.x_gate_lane_grad:
                    continue          # 没有跨车道结构的窗口定不住 dx
                per_window_x.setdefault(int(row["window_index"]), []).append(
                    float(row["phase_dx_px_pre_rotation"]) + shift_x)
            if per_window_x:
                fallback_x = statistics.median(
                    [v for values in per_window_x.values() for v in values])
                for w in range(WINDOW_COUNT):
                    self.x_window_obs[w].append(
                        statistics.median(per_window_x[w]) if w in per_window_x else fallback_x)
                limit_x = float(MAX_LOCAL_CORRECTION_PX)
                for w in range(WINDOW_COUNT):
                    v = self.x_window_obs[w]
                    if len(v) < X_WINDOW_MIN_OBS:
                        mode, val = "chain", -float(sum(v))
                    else:
                        arr = np.asarray(v, dtype=float)
                        same = max(float((arr > 0).mean()), float((arr < 0).mean()))
                        se = float(arr.std(ddof=1)) / math.sqrt(len(arr))
                        if same >= X_WINDOW_SAME_SIGN and abs(arr.mean()) > X_WINDOW_SIGNIF * se:
                            # 每条带共有的固有畸变: 按绝对量修一次, 不随帧数增长
                            mode, val = "fixed", -float(arr.mean())
                        else:
                            # 零均值抖动: 差分链累积等价于取平均, 天然有界
                            mode, val = "chain", -float(arr.sum())
                    self.x_window_mode[w] = mode
                    self.window_correction_x[w] = max(-limit_x, min(limit_x, val))
        record["window_correction_x_px"] = list(self.window_correction_x)
        record["window_correction_x_mode"] = list(self.x_window_mode)



        # the clamp applies to the CORRECTION only; the fractional placement is not a
        # correction and must not be clipped, so it is added after
        paste_frac = float(record["canvas_y_frac_px"])
        warp_values = [value + paste_frac for value in self.window_correction]

        # the strip was already rectified for the pair measurement; reuse it instead of
        # rectifying a second time (the warp returns a new array, the cached one is untouched)
        _t = time.perf_counter()
        corrected = warp_strip(self.cache.get(record), warp_values)
        _tick("warp", time.perf_counter() - _t)
        # lane-direction sub-pixel placement, the mirror of `paste_frac` above. Done before
        # the seam crop so the replicated edge column falls in the discarded strip.
        lane_frac = float(record.get("canvas_x_frac_px", 0.0))
        if lane_frac or any(self.window_correction_x):
            _t = time.perf_counter()
            if any(self.window_correction_x):
                # 逐窗车道向修正 + 亚像素小数, 一次 remap 解决
                corrected = warp_strip_local_x(
                    corrected, [v + lane_frac for v in self.window_correction_x])
            else:
                corrected = shift_strip_lane(corrected, lane_frac)
            _tick("lane_shift", time.perf_counter() - _t)
        seam_inset = int(record["seam_inset_px"])
        if seam_inset > 0:
            corrected = corrected[:, : corrected.shape[1] - seam_inset]
        _t = time.perf_counter()
        col, row = self._paste(record, corrected)
        _tick("paste", time.perf_counter() - _t)
        del corrected

        if _PROFILE:
            total = sum(_FRAME_T.values())
            parts = "  ".join(f"{k}={v*1000:.0f}ms" for k, v in sorted(_FRAME_T.items()))
            print(f"[prof {index:3d}] total~{total*1000:.0f}ms  {parts}")
            _FRAME_T.clear()

        frame = {
            "index": index,
            "direction": bool(record["direction"]),
            "filename": record["filename"],
            "zero_msp_special": bool(record["zero_msp_special"]),
            "repair_method": record["repair_method"],
            "predicted_dy_px": predicted_dy,
            "measured_dy_px": measured_dy,
            "residual_dy_px": residual_dy,
            "measured_dx_px": adjacent_dx,
            "applied_dx_px": applied_dx,
            "dx_source": dx_source,
            "adjacent_x_refine_px": float(self.refine_x),
            "canvas_x_frac_px": round(float(record.get("canvas_x_frac_px", 0.0)), 4),
            # lane extent of this strip after the seam crop: the evaluator needs it to know
            # where each seam actually falls in the saved canvas
            "paste_width": int(record["paste_width"]),
            "seam_inset_px": int(record["seam_inset_px"]),
            "lane_grad_windows": [round(float(r.get("lane_grad", 0.0)), 2)
                                  for r in pair_rows if valid_phase(r)],
            "dx_windows": [round(float(r["phase_dx_px_pre_rotation"]), 2)
                           for r in pair_rows if valid_phase(r)],
            "loop_residual_dy_px": loop_residual,
            "loop_windows": loop_windows,
            "loop_reject_reason": loop_reject,
            "applied_dy_px": applied_dy,
            "dy_source": dy_source,
            "reject_reason": reject_reason,
            "trusted_windows": trusted_windows,
            "skew_s_used": skew_s_used,
            "antisym_used": antisym_used,
            "skew_angle_deg_used": math.degrees(math.atan(skew_s_used)),
            "fit_pairs": len(self.fit_observations),
            "fit_source": self.fit_source,
            "skew_model_y_px": float(record["skew_model_y_px"]),
            "adjacent_y_refine_px": float(record["adjacent_y_refine_px"]),
            "canvas_y_frac_px": float(record["canvas_y_frac_px"]),
            "buffer_col": col,
            "buffer_row": row,
            "max_abs_window_correction_px": max(abs(v) for v in self.window_correction),
            "window_correction_x_px": [round(v, 3) for v in self.window_correction_x],
            "window_correction_x_mode": list(self.x_window_mode),
            "max_abs_window_correction_x_px": max(abs(v) for v in self.window_correction_x),
        }
        self.frames.append(frame)
        self.records.append(record)
        self.grandparent = self.previous
        self.previous = record
        return frame

    # ---------------- finish ----------------

    def finish(self, output_tif: Path) -> dict[str, Any]:
        if self._buffer is None or self._min_col is None:
            raise RuntimeError("no strip was pushed")
        cropped = self._buffer[self._min_row : self._max_row, self._min_col : self._max_col]
        image = Image.fromarray(cropped)
        if ROTATE_FINAL_CCW_90:
            rotated = image.transpose(Image.Transpose.ROTATE_90)
            image.close()
            image = rotated
        output_tif.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_tif, compression="tiff_lzw", dpi=(300, 300))
        size = image.size
        image.close()
        self._buffer = None

        # rewrite the recorded positions into the saved image's frame so the evaluator and
        # the batch runs share one coordinate convention
        for record, frame in zip(self.records, self.frames):
            record["canvas_x"] = int(frame["buffer_col"]) - int(self._min_col)
            record["canvas_y"] = int(frame["buffer_row"]) - int(self._min_row)
        final_by_index = {int(r["index"]): r for r in self.records}
        for row in self.residual_rows:
            row["a_canvas_x"] = final_by_index[int(row["a_index"])]["canvas_x"]
            row["b_canvas_x"] = final_by_index[int(row["b_index"])]["canvas_x"]
            row["a_canvas_y"] = final_by_index[int(row["a_index"])]["canvas_y"]
            row["b_canvas_y"] = final_by_index[int(row["b_index"])]["canvas_y"]
        return {"path": str(output_tif), "size": list(size)}





def apply_paste_model(args: argparse.Namespace) -> None:
    """`--paste-model field` = the field version's placement policy, nothing else changed.

    The rectification, the canvas layout, the seam inset and the evaluator stay exactly as
    the research version has them, so an A/B against the default isolates the placement
    policy: no feedback, whole-row paste, nominal encoder scale, no skew model.
    """
    if args.paste_model != "field":
        return
    args.no_feedback = True
    args.integer_paste = True
    args.nominal_scale = True
    args.no_loop_closure = True
    args.fixed_model = True
    if args.skew_s is None:
        args.skew_s = 0.0
    if args.antisym is None:
        args.antisym = 0.0


def _yaml_requires_online_skew_zero(paths: list) -> list[str]:
    """哪几份 yaml 自带 cross_term（schema v7 的跨轴剪切）。

    cross_term 描述的扫描向倾斜与本程序的在线 skew 模型（s·u）是**同一个自由度**。
    两边都开 = 双计：相邻链的 dy 残差多出 ~2×s×步进（本数据 ≈ 5px），会把 2.5px
    信任门的配对测量整批拒掉。所以带 v7 标定时在线 skew 冷启动必须从 0 开始。
    只做文本探测，不拉 800KB 的 yaml 解析。
    """
    hits: list[str] = []
    for p in paths:
        try:
            txt = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"cross_term:\s*\n\s*other_col", txt):
            hits.append(str(p))
    return hits


def resolve_prior(args: argparse.Namespace) -> tuple[float, float, str]:
    """The cold-start model. With the online fit on, it only covers the first few frames."""
    given = args.skew_s is not None and args.antisym is not None
    v7 = _yaml_requires_online_skew_zero([args.true_yaml, args.false_yaml])
    if given:
        if v7 and (float(args.skew_s) != 0.0 or float(args.antisym) != 0.0):
            print(f"[warn] 标定自带 cross_term 但在线 skew 先验非零: {v7}")
            print(f"       同一个扫描向倾斜会被建模两次（双计）。除非故意做 A/B，"
                  f"否则应加 --skew-s 0 --antisym 0")
        return float(args.skew_s), float(args.antisym), "given on the command line"
    if v7:
        print(f"[info] 标定自带 cross_term，在线 skew 冷启动自动归零（双计保护）: {v7}")
        return 0.0, 0.0, "zeroed: calibration carries cross_term"
    if args.fixed_model:
        raise SystemExit("--fixed-model needs both --skew-s and --antisym")
    return (COLD_START_SKEW_S, COLD_START_ANTISYM,
            f"cold start; the online fit takes over after {SKEW_FIT_MIN_PAIRS} pairs")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, required=True,
                   help="acquisition folder: the .tif frames plus LocalImageInfos.json")
    p.add_argument("--true-yaml", type=Path, required=True)
    p.add_argument("--false-yaml", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--json", type=Path, default=None,
                   help="override the auto-discovered image-info JSON")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=None, help="default: the last frame present")
    p.add_argument("--sat-mask", action=argparse.BooleanOptionalAction, default=False,
                   help="把窗内贴顶(>=%d)像素及其邻域的梯度用非饱和区均值填充后再做相关。"
                        "默认关（=与上游数值逐位一致）；打开后测量值会变，方否更好要看成图。"
                        "stitch0905 坑2" % SAT_THRESH)
    p.add_argument("--max-sat-frac", type=float, default=1.0,
                   help="窗内贴顶(>=%d)像素及其邻域的比例上限，超过的窗不进 dx/dy 中位数。"
                        "1.0=不启用（默认，只把 sat_frac 写进 CSV）。stitch0905 坑2" % SAT_THRESH)
    p.add_argument("--gate-peak-margin", type=float, default=0.0,
                   help="旁峰（高度>=主峰70%%）与主峰的距离小于此 px 就判该窗不可信。"
                        "0=不启用（默认，只报 rival_dist_px）。stitch0905 坑3/5")
    p.add_argument("--reject-degenerate", action="store_true",
                   help="拒掉“列翻转后响应与正向同分”的窗（无图案处的照明包络是左右对称的，"
                        "同分是退化不是匹配）。默认关。stitch0905 坑4")
    p.add_argument("--encoder-scale", choices=("fitted", "yaml-nominal"), default="fitted",
                   help="fitted=用标定的编码器尺度 D_STEP_X/D_MSP_Y（默认）；yaml-nominal=两边都用"
                        "从 **yaml 自己的 dpi** 推的 K_Coef（=现场版口径，不再硬编 300）。"
                        "等价于旧的 --nominal-scale，但 DPI 是从输入推的")
    p.add_argument("--skew-s", type=float, default=None, help="cold-start skew slope")
    p.add_argument("--antisym", type=float, default=None, help="cold-start antisymmetric term")
    p.add_argument("--fixed-model", action="store_true",
                   help="do not refit s/A online; use the cold-start values throughout")
    p.add_argument("--no-loop-closure", action="store_true",
                   help="place each frame against its neighbour only, without the i,i+2 constraint")
    p.add_argument("--integer-paste", action="store_true",
                   help="quantise the placement to whole rows")
    p.add_argument("--no-feedback", action="store_true",
                   help="measure every pair but feed nothing back: the strip stays where the "
                        "encoders put it (the field version's placement policy)")
    p.add_argument("--nominal-scale", action="store_true",
                   help="derive both axes from the nominal 300 DPI K_Coef instead of the "
                        "fitted encoder scales (the field version's constants)")
    p.add_argument("--paste-model", choices=("research", "field"), default="research",
                   help="'field' is shorthand for --no-feedback --integer-paste "
                        "--nominal-scale with a zero skew model, i.e. vsDriverbox "
                        "ImageStitch's placement policy on this script's rectification")
    p.add_argument("--workers", type=int, default=0,
                   help="parallel workers; 0 = original serial path. >0 enables the "
                        "accelerated pipeline (identical placement decisions)")
    p.add_argument("--d-step-x", type=float, default=None,
                   help="override the Step encoder scale (default 847.9656, fitted on "
                        "the OLD machine). Per-machine constant: fit it from the "
                        "acquisition itself (e.g. line-endpoint ground truth) when "
                        "stitching a NEW machine")
    p.add_argument("--x-offset-false", type=float, default=None,
                   help="override the False-direction x origin offset (default 2.9081, "
                        "OLD machine). Together with the registered YAML's offset this "
                        "sets the T/F lane origin difference")
    p.add_argument("--x-feedback", action="store_true",
                   help="close the lane-direction (x) loop: measure each pair's residual "
                        "lane offset with the same trusted windows that feed the y chain "
                        "and correct the placement, mirroring the y refine. Without it the "
                        "x placement stays pure encoder dead-reckoning (original behaviour)")
    p.add_argument("--x-loop-mode", choices=("adjacent-first", "blend"),
                   default="adjacent-first",
                   help="how --x-feedback combines the two constraints. 'adjacent-first' "
                        "(default here) uses the adjacent pair alone when it is trusted and "
                        "falls back to the i,i+2 loop only when it is not; 'blend' is the "
                        "original (adjacent + 0.5*loop)/1.5. The loop pair is SAME-direction, "
                        "so blending dilutes the only measurement that sees the T/F lane "
                        "offset and leaves a residual on the direction-crossing seams")
    p.add_argument("--x-gate-lane-grad", type=float, default=0.0,
                   help="minimum mean |d/dlane| a window must have before its dx counts "
                        "(0 = off, original behaviour). The 2-D phase_response cannot tell "
                        "a window that only has strokes running ALONG the lane from one "
                        "that can actually localise a lane shift; on a sparse white-paper "
                        "target the ungated dx median swings ~1 px between runs of the "
                        "same placement. Windows below the gate are dropped from the dx "
                        "median only; the dy chain is untouched")
    p.add_argument("--x-window-top-half", action=argparse.BooleanOptionalAction, default=False,
                   help="take the dx median over the half of the trusted windows with the "
                        "highest across-lane gradient instead of all of them. NOT a net win "
                        "on this batch: it fixes seam 6_7 (-1.10 -> -0.10 px against the "
                        "line-endpoint truth) but regresses seam 2_3 (-0.12 -> +0.88), so it "
                        "is off by default. Kept because it isolates the cause - the flat "
                        "windows really do drag the dx median")
    p.add_argument("--subpixel-x", action=argparse.BooleanOptionalAction, default=True,
                   help="place strips at fractional columns in the lane direction: the "
                        "remainder goes into canvas_x_frac_px and is applied to the pixels "
                        "by a 1-D lerp before the paste. The y chain has always done this; "
                        "without it every seam keeps up to 0.5 px of pure rounding, which is "
                        "the floor the constants and the feedback run into (seam 4_5)")
    p.add_argument("--x-local-pose", action=argparse.BooleanOptionalAction, default=False,
                   help="车道向也做 7 窗局部修正（y 那条链一直有，x 之前只有一个标量）。"
                        "逐窗相位相关实测缝的车道向误差沿列极差 0.75~1.63 px，闭环只能修"
                        "掉均值。**默认关**：本批数据上净收益很小（缝上 rms −4.7%%），且"
                        "w6 那类每条带共有的畸变要走固定项分支才不会累积失控，判据只在"
                        "一次采集上验证过。需要 --x-feedback")
    p.add_argument("--x-gain", type=float, default=1.0,
                   help="车道向闭环增益：施加 applied_dx = gain * measured_dx。代码默认 1.0 "
                        "（量到多少修多少），但这个假定从没在成图上验过。扫 gain 能直接量出"
                        "闭环的真实增益：若最优点远离 1.0（例如过修正到 2 倍或反号），那残余"
                        "的 0.5~1 px 就不是底噪而是增益错。只影响施加量，CSV 里的 "
                        "measured_dx_px 仍是裸测量值")
    p.add_argument("--seam-inset", type=int, default=SEAM_INSET_PX,
                   help="缝相对条带车道向尾边的位置（px）。默认 256 把缝放在车道 "
                        "y 99.72 mm —— 正好压在标定支撑区下界 100.0 上, 缝外侧那 256 px "
                        "两个方向都没有测量, 全是线性外推, 于是边缘斜率有 21.87 mm 的杠杆 "
                        "(0.098 px/mm 的斜率变动就把缝推了 2.1 px, 见 README 5.9.5)。"
                        "加大到 384 可把缝移到 y≈110.6, T 侧进入实测区 10.6 mm、"
                        "F 侧(出厂支撑 109.77)也进去 0.8 mm。代价: i,i+2 回路重叠从 "
                        "~316 px 降到 ~188 px, 回路约束变弱")
    p.add_argument("--rectify-backend", choices=("shm", "process", "thread"), default="shm",

                   help="shm: shared-memory pipeline, rectify+window process pools, no "
                        "large IPC (recommended); process/thread: legacy prefetch backends")
    p.add_argument("--gpu-warp", action=argparse.BooleanOptionalAction, default=True,
                   help="run the final local-pose warp on the GPU when torch+cuda is "
                        "available (canvas pixels may differ from the CPU warp by "
                        "1-2/255 from interpolation rounding; decisions unaffected)")
    p.add_argument("--worker-cv2-threads", type=int, default=0,
                   help="process/thread backends only: cap each worker's OpenCV threads")
    return p.parse_args()


def _measure_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把 stitch0905 相关的新诊断量汇总（默认这些门都不参与计算，所以先要看它们到底
    有没有在响）。按缝统计：饱和比例、旁峰距离、翻转同分数。"""
    import statistics as _st
    per: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        pair = str(r.get("pair", "?"))
        d = per.setdefault(pair, {"sat": [], "rival": [], "degen": [], "resp": []})
        d["sat"].append(_row_float(r, "sat_frac", 0.0))
        rv = r.get("rival_dist_px")
        if rv not in ("", None):
            d["rival"].append(_row_float(r, "rival_dist_px", 9e9))
        d["degen"].append(_row_float(r, "degenerate", 0.0))
        d["resp"].append(_row_float(r, "phase_response", float("nan")))
    out = {"gates_active": {"max_sat_frac": MAX_SAT_FRAC, "gate_peak_margin_px": GATE_PEAK_MARGIN_PX,
                             "reject_degenerate": REJECT_DEGENERATE}}
    agg = {k: [] for k in ("sat", "rival", "degen", "resp")}
    for pair, d in sorted(per.items()):
        e = {"windows": len(d["sat"]),
             "sat_frac_max": round(max(d["sat"]), 4) if d["sat"] else None,
             "degenerate_windows": int(sum(d["degen"])),
             "response_med": round(_st.median(d["resp"]), 4) if d["resp"] else None}
        if d["rival"]:
            e["rival_dist_min_px"] = round(min(d["rival"]), 2)
            agg["rival"].append(min(d["rival"]))
        for k in ("sat", "degen", "resp"):
            agg[k].extend(d[k])
        out.setdefault("per_pair", {})[pair] = e
    if agg["sat"]:
        out["worst"] = {"sat_frac_max": round(max(agg["sat"]), 4),
                        "sat_windows_over_10pct": int(sum(1 for v in agg["sat"] if v > 0.10)),
                        "n_windows": len(agg["sat"]),
                        "degenerate_windows": int(sum(agg["degen"])),
                        "min_rival_dist_px": (round(min(agg["rival"]), 2)
                                              if agg["rival"] else None)}
    return out


def main() -> None:
    args = parse_args()
    apply_paste_model(args)

    global D_STEP_X, X_OFFSET_FALSE_PX
    if args.d_step_x is not None:
        D_STEP_X = float(args.d_step_x)
    if args.x_offset_false is not None:
        X_OFFSET_FALSE_PX = float(args.x_offset_false)
    # stitch0905 加固开关（默认值=不改原行为，只多报诊断量）
    global MAX_SAT_FRAC, GATE_PEAK_MARGIN_PX, REJECT_DEGENERATE, K_COEF_ACTIVE, SAT_MASK_ON
    MAX_SAT_FRAC = float(args.max_sat_frac)
    GATE_PEAK_MARGIN_PX = float(args.gate_peak_margin)
    REJECT_DEGENERATE = bool(args.reject_degenerate)
    SAT_MASK_ON = bool(args.sat_mask)
    if SAT_MASK_ON:
        os.environ["STITCH_SAT_MASK"] = "1"      # 让窗口进程池也拿到同一开关
        print("[info] 窗口特征已启用饱和掩蔽（--sat-mask）：会改变相关结果，不是默认行为")
    if args.encoder_scale == "yaml-nominal":
        args.nominal_scale = True
    dpi_t = yaml_output_dpi(args.true_yaml)
    dpi_f = yaml_output_dpi(args.false_yaml)
    if dpi_t is None or dpi_f is None or abs(dpi_t - dpi_f) > 1e-6:
        if args.encoder_scale == "yaml-nominal":
            raise SystemExit("--encoder-scale yaml-nominal 需要两份 yaml 都带 output_defaults.dpi")
    else:
        K_COEF_ACTIVE = 25.4 / float(dpi_t) * 10000.0
        if args.encoder_scale == "yaml-nominal":
            print(f"[info] 编码器尺度 K_Coef = {K_COEF_ACTIVE:.4f} counts/px "
                  f"(由 yaml dpi={dpi_t:g} 推，不假设 300)")
    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        raise SystemExit(f"--data-dir {data_dir} is not a directory")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    info_json = discover_info_json(data_dir, args.json)
    all_info = load_json(info_json, 0)
    end = int(args.end) if args.end is not None else last_available_index(data_dir, all_info)
    start = int(args.start)
    if end <= start:
        raise SystemExit(f"need at least two frames; got start={start}, end={end}")
    if len(all_info) <= end:
        raise SystemExit(f"{info_json.name} has {len(all_info)} entries, cannot read frame {end}")

    skew_s, antisym, prior_source = resolve_prior(args)
    print(f"[info] data dir   {data_dir}")
    print(f"[info] info json  {info_json.name}  ({len(all_info)} entries)")
    print(f"[info] yaml       true={args.true_yaml.name}  false={args.false_yaml.name}")
    print(f"[info] frames     {start}..{end}")
    print(f"[info] cold start s = {skew_s:+.6e} "
          f"(theta = {math.degrees(math.atan(skew_s)):+.5f} deg), A = {antisym:+.4f} px "
          f"[{prior_source}]")
    print(f"[info] online fit: {'off (fixed model)' if args.fixed_model else 'on'}   "
          f"loop closure: {'off' if args.no_loop_closure else f'on (weight {LOOP_CLOSURE_WEIGHT})'}   "
          f"paste: {'whole rows' if args.integer_paste else 'sub-pixel'}")
    print(f"[info] paste model {args.paste_model}   "
          f"feedback: {'off (open loop)' if args.no_feedback else 'on'}   "
          f"scale: {'nominal K_Coef' if args.nominal_scale else 'fitted encoder'}")

    feed = CausalInfoFeed(all_info)

    # ---- acceleration setup (--workers > 0) ----
    t_wall0 = time.perf_counter()
    executor = None
    window_executor = None
    shm_cache = None
    prefetch_cache = None
    global _WINDOW_POOL, _PAIR_POOL, _QUIET_REMAP, _GPU_WARP
    if args.workers > 0:
        from concurrent.futures import ThreadPoolExecutor
        if args.rectify_backend == "shm":
            # shared-memory pipeline: rectify workers write into shm blocks, window
            # measurement runs in a process pool over zero-copy views of the same
            # blocks. No 69 MB array is ever pickled across a process boundary.
            true_cal = load_calibration_yaml(args.true_yaml)
            false_cal = load_calibration_yaml(args.false_yaml)
            executor = ProcessPoolExecutor(
                max_workers=max(2, args.workers // 2),
                initializer=_worker_init,
                initargs=(str(args.true_yaml.resolve()), str(args.false_yaml.resolve()), 2),
            )
            window_executor = ProcessPoolExecutor(
                max_workers=args.workers,
                initializer=_window_pool_init,
                initargs=(2,),
            )
            shm_cache = ShmRectifiedCache(
                executor, window_executor,
                args.true_yaml.resolve(), args.false_yaml.resolve(),
                target_grid_shape(true_cal), target_grid_shape(false_cal), max_size=4)
            _QUIET_REMAP = True
            backend_note = (f"shm pipeline: {max(2, args.workers // 2)} rectify procs + "
                            f"{args.workers} window procs (zero-copy)")
        else:
            if args.rectify_backend == "thread":
                executor = ThreadPoolExecutor(max_workers=args.workers)
                _QUIET_REMAP = True
                backend_note = f"{args.workers} rectify threads (in-process)"
            else:
                executor = ProcessPoolExecutor(
                    max_workers=args.workers,
                    initializer=_worker_init,
                    initargs=(str(args.true_yaml.resolve()), str(args.false_yaml.resolve()),
                              int(args.worker_cv2_threads)),
                )
                backend_note = f"{args.workers} rectify processes"
            prefetch_cache = PrefetchRectifiedCache(
                executor, args.true_yaml.resolve(), args.false_yaml.resolve(), max_size=4)
            _WINDOW_POOL = ThreadPoolExecutor(max_workers=8)
        _PAIR_POOL = ThreadPoolExecutor(max_workers=1)
        if args.gpu_warp:
            try:
                _GPU_WARP = GpuWarp()
                warp_note = " + GPU warp"
            except Exception as exc:  # torch/cuda unavailable
                print(f"[info] GPU warp unavailable ({exc}); CPU warp")
                warp_note = " + CPU warp"
        else:
            warp_note = " + CPU warp"
        print(f"[info] ACCELERATED: {backend_note}{warp_note} "
              f"(lookahead {args.workers + 2}) + concurrent loop pair")

    stitcher = StreamingStitcher(
        data_dir, feed,
        load_calibration_yaml(args.true_yaml), load_calibration_yaml(args.false_yaml),
        args.true_yaml, args.false_yaml, skew_s, antisym,
        subpixel=not bool(args.integer_paste),
        online_fit=not bool(args.fixed_model),
        loop_closure=not bool(args.no_loop_closure),
        feedback=not bool(args.no_feedback),
        nominal_scale=bool(args.nominal_scale),
        rectified_cache=shm_cache if shm_cache is not None else prefetch_cache,
        x_feedback=bool(args.x_feedback),
        x_loop_mode=str(args.x_loop_mode),
        x_gate_lane_grad=float(args.x_gate_lane_grad),
        x_window_top_half=bool(args.x_window_top_half),
        subpixel_x=bool(args.subpixel_x),
        x_local_pose=bool(args.x_local_pose),
        x_gain=float(args.x_gain),
        seam_inset_px=int(args.seam_inset),
    )


    # Arrival and placement are decoupled: a frame goes into a FIFO when it arrives and is
    # placed as soon as `can_place()` says its metadata is repairable from what has already
    # arrived. Placement stays strictly in order because the pair measurement needs the
    # previous frame on the canvas.
    pending: deque[int] = deque()
    held_frames: dict[int, int] = {}
    submitted_upto = start - 1
    active_cache = shm_cache if shm_cache is not None else prefetch_cache

    def submit_prefetch(upto: int) -> None:
        """Keep a bounded set of rectification jobs in flight ahead of consumption."""
        nonlocal submitted_upto
        if active_cache is None:
            return
        limit = min(upto, end)
        while submitted_upto < limit:
            submitted_upto += 1
            entry = all_info[submitted_upto]
            active_cache.submit(
                submitted_upto,
                resolve_image_path(data_dir, entry, submitted_upto),
                bool(entry["Info"]["Direction"]),
            )

    try:
        for index in range(start, end + 1):
            feed.arrive(index)
            pending.append(index)
            submit_prefetch(index + args.workers + 2 if args.workers > 0 else index)
            while pending:
                head = pending[0]
                ok, why = stitcher.can_place(head)
                if not ok:
                    if head not in held_frames:
                        print(f"[frame {head:>3}] held: {why}")
                    held_frames[head] = held_frames.get(head, 0) + 1
                    break
                pending.popleft()
                waited = held_frames.pop(head, 0)
                frame = stitcher.push(head)
                frame["frames_held"] = waited
                detail = (f"predicted {frame['predicted_dy_px']:+.3f} residual "
                          f"{frame['residual_dy_px']:+.3f}"
                          if frame["measured_dy_px"] is not None else
                          f"source={frame['dy_source']}"
                          + (f" ({frame['reject_reason']})" if frame["reject_reason"] else ""))
                loop = (f" loop {frame['loop_residual_dy_px']:+.3f}"
                        if frame["loop_residual_dy_px"] is not None else "")
                latency = f"  (held {waited} frames)" if waited else ""
                print(f"[frame {head:>3}] {detail}{loop}  applied {frame['applied_dy_px']:+.3f}  "
                      f"refine {frame['adjacent_y_refine_px']:+.3f}  "
                      f"s {frame['skew_s_used']:.4e} A {frame['antisym_used']:+.3f} "
                      f"({frame['fit_source']}, {frame['fit_pairs']} pairs){latency}")
        if pending:
            raise RuntimeError(
                f"frames {list(pending)} never became placeable; last block: "
                f"{stitcher.can_place(pending[0])[1]}"
            )

        output_tif = output_dir / f"stitched_{start}_{end}_stream.tif"
        verify = stitcher.finish(output_tif)
    finally:
        # ---- acceleration teardown + timing (runs even on failure, so no worker
        # process is left waiting on a dead parent) ----
        wall_seconds = time.perf_counter() - t_wall0
        if _WINDOW_POOL is not None:
            _WINDOW_POOL.shutdown(wait=True)
        if _PAIR_POOL is not None:
            _PAIR_POOL.shutdown(wait=True)
        if shm_cache is not None:
            shm_cache.close()
        if window_executor is not None:
            window_executor.shutdown(wait=True)
        if executor is not None:
            executor.shutdown(wait=True)

    write_csv(output_dir / "stream_frame_log.csv", stitcher.frames)
    write_csv(output_dir / "estimated_final_window_residuals_before_local_pose.csv",
              stitcher.residual_rows)
    if stitcher.loop_rows:
        write_csv(output_dir / "loop_closure_pairs.csv", stitcher.loop_rows)

    refines = [float(f["adjacent_y_refine_px"]) for f in stitcher.frames]
    models = [float(f["skew_model_y_px"]) for f in stitcher.frames]
    fell_back = [int(f["index"]) for f in stitcher.frames if f["dy_source"] == "model"]
    applied = [abs(float(f["applied_dy_px"])) for f in stitcher.frames[1:]]
    third = max(1, len(applied) // 3)

    def rms(values: list[float]) -> float:
        return (sum(v * v for v in values) / len(values)) ** 0.5 if values else 0.0

    summary = {
        "status": "ok",
        "model": "standalone_streaming_online_skew_fit_plus_loop_closure",
        "data_dir": str(data_dir),
        "info_json": str(info_json),
        "true_yaml": str(args.true_yaml.resolve()),
        "false_yaml": str(args.false_yaml.resolve()),
        "frame_range": [start, end],
        "paste": "integer_rows" if args.integer_paste else "subpixel",
        "online_fit": stitcher.online_fit,
        "loop_closure": stitcher.loop_closure,
        "loop_closure_weight": LOOP_CLOSURE_WEIGHT,
        "prior_skew_s_px_per_px": skew_s,
        "prior_antisym_px": antisym,
        "prior_source": prior_source,
        "fitted_skew_s_px_per_px": stitcher.skew_s,
        "fitted_skew_angle_deg": math.degrees(math.atan(stitcher.skew_s)),
        "fitted_antisym_px": stitcher.antisym,
        "fit_source": stitcher.fit_source,
        "fit_pairs": len(stitcher.fit_observations),
        "skew_model_last_px": models[-1],
        "chain_residual_last_px": refines[-1],
        "chain_residual_max_abs_px": max(abs(v) for v in refines),
        "x_feedback": stitcher.x_feedback,
        "x_loop_mode": stitcher.x_loop_mode,
        "x_gate_lane_grad": stitcher.x_gate_lane_grad,
        "subpixel_x": stitcher.subpixel_x,
        "seam_inset_px": stitcher.seam_inset_px,

        "x_constant_refit": stitcher.x_constant_refit(),
        "x_refine_chain_last_px": round(float(stitcher.refine_x), 4),
        "applied_dy_rms_px": rms(applied),
        "applied_dy_rms_first_third_px": rms(applied[:third]),
        "applied_dy_rms_last_third_px": rms(applied[-third:]),
        "loop_pairs_used": sum(1 for f in stitcher.frames
                               if f["loop_residual_dy_px"] is not None),
        "links_carried_by_model": fell_back,
        "max_startup_hold_frames": max((int(f.get("frames_held", 0)) for f in stitcher.frames),
                                       default=0),
        "output_tif": str(output_tif),
        "verify": verify,
        "workers": int(args.workers),
        "rectify_backend": str(args.rectify_backend),
        "gpu_warp": _GPU_WARP is not None,
        "measure_diagnostics": _measure_diagnostics(stitcher.residual_rows),
        "wall_seconds": round(wall_seconds, 2),
        "seconds_per_frame": round(wall_seconds / max(1, len(stitcher.frames)), 3),
    }
    (output_dir / "stream_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== done ===")
    print(f"  learnt model         s = {stitcher.skew_s:+.6e} "
          f"(theta = {math.degrees(math.atan(stitcher.skew_s)):+.5f} deg), "
          f"A = {stitcher.antisym:+.4f} px  [{stitcher.fit_source}, "
          f"{len(stitcher.fit_observations)} pairs]")
    print(f"  skew model last      {models[-1]:+.4f} px")
    print(f"  residual chain last  {refines[-1]:+.4f} px, max |chain| "
          f"{max(abs(v) for v in refines):.4f} px")
    print(f"  |applied| rms        {rms(applied):.4f} px   "
          f"first third {rms(applied[:third]):.4f} -> last third {rms(applied[-third:]):.4f}")
    print(f"  loop pairs used      {summary['loop_pairs_used']} / {max(0, len(stitcher.frames) - 2)}")
    print(f"  links carried by model {fell_back}")
    print(f"  tif    {output_tif}")
    print(f"  verify {verify}")
    print(f"  wall   {wall_seconds:.1f} s  ({wall_seconds / max(1, len(stitcher.frames)):.2f} s/frame, "
          f"workers={args.workers})")


if __name__ == "__main__":
    main()
