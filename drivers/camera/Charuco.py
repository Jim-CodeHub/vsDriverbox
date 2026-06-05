#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立模块：读取 YAML 标定参数并快速校正图像。

不依赖 step6 或其他 step 文件。对外提供 rectify_charuco_image()，
输入 yaml 路径与图像路径（或 ndarray），返回单通道灰度校正图。

示例：
    import cv2
    from charuco_rectify import rectify_charuco_image  # 或 from 123_charuco import ...

    gray = rectify_charuco_image("4_calib.yaml", "6.tif")
    cv2.imwrite("6_rectified.tif", gray)

依赖：
    pip install numpy opencv-python pyyaml tifffile pillow scipy pandas
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import cv2
import numpy as np
import pandas as pd

try:
    import yaml
except Exception as exc:
    raise RuntimeError("缺少 PyYAML，请执行：pip install pyyaml") from exc

try:
    import tifffile
except Exception as exc:
    raise RuntimeError("缺少 tifffile，请执行：pip install tifffile") from exc

try:
    from PIL import Image
except Exception as exc:
    raise RuntimeError("缺少 Pillow，请执行：pip install pillow") from exc

try:
    from scipy.interpolate import PchipInterpolator, RBFInterpolator
    from scipy.stats import theilslopes
except Exception as exc:
    raise RuntimeError("缺少 scipy，请执行：pip install scipy") from exc

PathLike = Union[str, Path]


# ==================== 工具函数 ====================

def load_image_unchanged(image_path: Path) -> np.ndarray:
    """读取 TIFF 等图像，并保留原始位深。"""
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    return image


def to_jsonable(value):
    """将 NumPy 类型转换为 JSON 可写入类型。"""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def interpolation_flag(name: str) -> int:
    """将插值方法名称转换为 OpenCV 标志。"""
    table = {
        "nearest": cv2.INTER_NEAREST,
        "linear": cv2.INTER_LINEAR,
        "cubic": cv2.INTER_CUBIC,
        "lanczos": cv2.INTER_LANCZOS4,
    }
    return table[name]


def allocate_output(image: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    """创建与输入图像位深和通道数一致的输出数组。"""
    if image.ndim == 2:
        return np.zeros((out_h, out_w), dtype=image.dtype)
    if image.ndim == 3:
        return np.zeros((out_h, out_w, image.shape[2]), dtype=image.dtype)
    raise ValueError(f"Unsupported image shape: {image.shape}")


def make_preview(image: np.ndarray, max_side: int = 1800) -> np.ndarray:
    """生成便于查看的 8-bit PNG 预览图。"""
    if image.ndim == 3 and image.shape[2] == 4:
        work = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        work = image.copy()

    if work.dtype != np.uint8:
        work_float = work.astype(np.float32)
        finite = work_float[np.isfinite(work_float)]
        if finite.size == 0:
            work_u8 = np.zeros_like(work_float, dtype=np.uint8)
        else:
            lo, hi = np.percentile(finite, [1.0, 99.0])
            if hi <= lo:
                hi = lo + 1.0
            work_u8 = np.clip((work_float - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    else:
        work_u8 = work

    h, w = work_u8.shape[:2]
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        work_u8 = cv2.resize(work_u8, new_size, interpolation=cv2.INTER_AREA)
    return work_u8


def ensure_grayscale(image: np.ndarray) -> np.ndarray:
    """将彩色图转为单通道灰度；已是灰度则原样返回。"""
    img = np.asarray(image)
    if img.ndim == 2:
        return img
    if img.ndim == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 3 and img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    raise ValueError(f"不支持的图像通道布局: shape={img.shape}")


def _convert_bgr_for_standard_file(image: np.ndarray) -> np.ndarray:
    """将 OpenCV 的 BGR/BGRA 顺序转换为常见文件格式使用的 RGB/RGBA 顺序。"""
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    return image


def save_image_with_dpi(path: PathLike, image: np.ndarray, dpi: int = 300) -> Path:
    """保存图像并写入 DPI 元数据。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if dpi <= 0:
        raise ValueError("dpi 必须 > 0。")

    suffix = output_path.suffix.lower()
    standard = _convert_bgr_for_standard_file(ensure_grayscale(np.asarray(image)))
    if suffix in {".tif", ".tiff"}:
        tifffile.imwrite(
            str(output_path),
            standard,
            resolution=(float(dpi), float(dpi)),
            resolutionunit="INCH",
            metadata=None,
            bigtiff=bool(standard.nbytes >= 4 * 1024**3),
        )
    elif suffix == ".png":
        Image.fromarray(standard).save(str(output_path), dpi=(float(dpi), float(dpi)))
    else:
        raise ValueError(f"暂不支持写入 DPI 的文件格式：{suffix}。请使用 TIFF 或 PNG。")
    return output_path


# ==================== 核心校准类 ====================

@dataclass
class RobustAxisModel:
    """稳健轴模型，用于物理坐标到像素坐标的映射。"""
    
    physical_col: str
    pixel_col: str
    knots_physical_mm: np.ndarray
    knots_source_px: np.ndarray
    left_slope_px_per_mm: float
    right_slope_px_per_mm: float
    edge_fit_points: int

    def __post_init__(self) -> None:
        self.knots_physical_mm = np.asarray(self.knots_physical_mm, dtype=np.float64)
        self.knots_source_px = np.asarray(self.knots_source_px, dtype=np.float64)
        if len(self.knots_physical_mm) < 2:
            raise ValueError("稳健一维模型至少需要 2 个节点。")
        if len(self.knots_physical_mm) != len(self.knots_source_px):
            raise ValueError("物理坐标节点和像素节点长度不一致。")
        if not np.all(np.diff(self.knots_physical_mm) > 0):
            raise ValueError("物理坐标节点必须严格递增。")

        self._pchip = PchipInterpolator(
            self.knots_physical_mm,
            self.knots_source_px,
            extrapolate=False,
        )

        # 建立逆映射：原图像素 -> 物理坐标
        increasing = self.knots_source_px[-1] >= self.knots_source_px[0]
        if increasing:
            monotonic_px = np.maximum.accumulate(self.knots_source_px)
            px_sorted = monotonic_px
            phys_sorted = self.knots_physical_mm
        else:
            monotonic_px = np.minimum.accumulate(self.knots_source_px)
            px_sorted = monotonic_px[::-1]
            phys_sorted = self.knots_physical_mm[::-1]

        unique_px, unique_index = np.unique(px_sorted, return_index=True)
        unique_phys = phys_sorted[unique_index]
        if len(unique_px) < 2:
            raise ValueError("无法建立逆映射：像素节点不足。")
        self._inverse_px_sorted = unique_px
        self._inverse_phys_sorted = unique_phys
        self._inverse_pchip = PchipInterpolator(unique_px, unique_phys, extrapolate=False)

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
        """物理坐标 -> 原始扫描图像素坐标。"""
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

    def inverse(self, source_px: np.ndarray) -> np.ndarray:
        """原始扫描图像素坐标 -> 物理坐标。"""
        y = np.asarray(source_px, dtype=np.float64)
        result = np.empty_like(y, dtype=np.float64)

        px_low = float(self._inverse_px_sorted[0])
        px_high = float(self._inverse_px_sorted[-1])
        phys_at_low = float(self._inverse_phys_sorted[0])
        phys_at_high = float(self._inverse_phys_sorted[-1])

        slope_low = self.left_slope_px_per_mm if abs(phys_at_low - self.phys_min) <= abs(phys_at_low - self.phys_max) else self.right_slope_px_per_mm
        slope_high = self.left_slope_px_per_mm if abs(phys_at_high - self.phys_min) <= abs(phys_at_high - self.phys_max) else self.right_slope_px_per_mm

        low = y < px_low
        high = y > px_high
        middle = ~(low | high)

        if np.any(middle):
            result[middle] = self._inverse_pchip(y[middle])
        if np.any(low):
            result[low] = phys_at_low + (y[low] - px_low) / slope_low
        if np.any(high):
            result[high] = phys_at_high + (y[high] - px_high) / slope_high
        return result

    def to_yaml_dict(self) -> Dict[str, object]:
        return {
            "physical_col": self.physical_col,
            "pixel_col": self.pixel_col,
            "knots_physical_mm": self.knots_physical_mm.tolist(),
            "knots_source_px": self.knots_source_px.tolist(),
            "left_slope_px_per_mm": float(self.left_slope_px_per_mm),
            "right_slope_px_per_mm": float(self.right_slope_px_per_mm),
            "edge_fit_points": int(self.edge_fit_points),
            "inside_support_model": "PCHIP",
            "outside_support_model": "robust_linear_extrapolation",
        }

    @classmethod
    def from_yaml_dict(cls, data: Dict[str, object]) -> "RobustAxisModel":
        return cls(
            physical_col=str(data["physical_col"]),
            pixel_col=str(data["pixel_col"]),
            knots_physical_mm=np.asarray(data["knots_physical_mm"], dtype=np.float64),
            knots_source_px=np.asarray(data["knots_source_px"], dtype=np.float64),
            left_slope_px_per_mm=float(data["left_slope_px_per_mm"]),
            right_slope_px_per_mm=float(data["right_slope_px_per_mm"]),
            edge_fit_points=int(data["edge_fit_points"]),
        )


@dataclass
class TaperedRBFGridResidualModel:
    """RBF 残差模型，用于校正残差。"""
    
    grid_x_mm: np.ndarray
    grid_y_mm: np.ndarray
    correction_x_grid_px: np.ndarray
    correction_y_grid_px: np.ndarray
    smoothing: float
    neighbors: int
    taper_mm: float
    support_x_min: float
    support_x_max: float
    support_y_min: float
    support_y_max: float
    grid_step_mm: float

    def __post_init__(self) -> None:
        self.grid_x_mm = np.asarray(self.grid_x_mm, dtype=np.float64)
        self.grid_y_mm = np.asarray(self.grid_y_mm, dtype=np.float64)
        self.correction_x_grid_px = np.asarray(self.correction_x_grid_px, dtype=np.float32)
        self.correction_y_grid_px = np.asarray(self.correction_y_grid_px, dtype=np.float32)
        expected_shape = (len(self.grid_y_mm), len(self.grid_x_mm))
        if self.correction_x_grid_px.shape != expected_shape or self.correction_y_grid_px.shape != expected_shape:
            raise ValueError("RBF 残差网格尺寸不匹配。")
        if len(self.grid_x_mm) < 2 or len(self.grid_y_mm) < 2:
            raise ValueError("RBF 残差网格至少需要 2 x 2 个节点。")

    def __call__(self, points_mm: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        points = np.asarray(points_mm, dtype=np.float64)
        x = points[:, 0]
        y = points[:, 1]
        step_x = float(self.grid_x_mm[1] - self.grid_x_mm[0])
        step_y = float(self.grid_y_mm[1] - self.grid_y_mm[0])

        map_x_all = ((x - self.grid_x_mm[0]) / step_x).astype(np.float32)
        map_y_all = ((y - self.grid_y_mm[0]) / step_y).astype(np.float32)

        correction_x = np.zeros(len(points), dtype=np.float32)
        correction_y = np.zeros(len(points), dtype=np.float32)
        query_batch = 30000
        for start in range(0, len(points), query_batch):
            end = min(start + query_batch, len(points))
            map_x = map_x_all[start:end].reshape(-1, 1)
            map_y = map_y_all[start:end].reshape(-1, 1)
            correction_x[start:end] = cv2.remap(
                self.correction_x_grid_px,
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            ).reshape(-1)
            correction_y[start:end] = cv2.remap(
                self.correction_y_grid_px,
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            ).reshape(-1)
        return correction_x.astype(np.float64), correction_y.astype(np.float64)

    def to_yaml_dict(self) -> Dict[str, object]:
        return {
            "type": "rbf_tapered_grid",
            "kernel": "thin_plate_spline",
            "smoothing": float(self.smoothing),
            "neighbors": int(self.neighbors),
            "taper_mm": float(self.taper_mm),
            "grid_step_mm": float(self.grid_step_mm),
            "support_region_mm": {
                "x_min": float(self.support_x_min),
                "x_max": float(self.support_x_max),
                "y_min": float(self.support_y_min),
                "y_max": float(self.support_y_max),
            },
            "grid_x_mm": self.grid_x_mm.tolist(),
            "grid_y_mm": self.grid_y_mm.tolist(),
            "correction_x_grid_px": self.correction_x_grid_px.tolist(),
            "correction_y_grid_px": self.correction_y_grid_px.tolist(),
        }

    @classmethod
    def from_yaml_dict(cls, data: Dict[str, object]) -> "TaperedRBFGridResidualModel":
        support = data["support_region_mm"]
        return cls(
            grid_x_mm=np.asarray(data["grid_x_mm"], dtype=np.float64),
            grid_y_mm=np.asarray(data["grid_y_mm"], dtype=np.float64),
            correction_x_grid_px=np.asarray(data["correction_x_grid_px"], dtype=np.float32),
            correction_y_grid_px=np.asarray(data["correction_y_grid_px"], dtype=np.float32),
            smoothing=float(data["smoothing"]),
            neighbors=int(data["neighbors"]),
            taper_mm=float(data["taper_mm"]),
            support_x_min=float(support["x_min"]),
            support_x_max=float(support["x_max"]),
            support_y_min=float(support["y_min"]),
            support_y_max=float(support["y_max"]),
            grid_step_mm=float(data["grid_step_mm"]),
        )


@dataclass
class LineScanPlanarCalibration:
    """线阵相机固定工作平面标定参数。"""
    
    square_size_mm: float
    pixels_per_square: int
    axis_mapping: Dict[str, object]
    source_x_model: RobustAxisModel
    source_y_model: RobustAxisModel
    support_region_mm: Dict[str, float]
    residual_model: Optional[TaperedRBFGridResidualModel]
    fit_residual_px: Dict[str, object]
    reference_image_shape: Tuple[int, ...]
    reference_full_ranges_mm: Dict[str, float]
    output_dpi: int
    schema_version: int = 1

    @property
    def pixels_per_mm(self) -> float:
        return float(self.pixels_per_square) / float(self.square_size_mm)

    def to_yaml_dict(self) -> Dict[str, object]:
        return {
            "schema_version": int(self.schema_version),
            "calibration_type": "line_scan_planar",
            "square_size_mm": float(self.square_size_mm),
            "pixels_per_square": int(self.pixels_per_square),
            "axis_mapping": self.axis_mapping,
            "source_x_model": self.source_x_model.to_yaml_dict(),
            "source_y_model": self.source_y_model.to_yaml_dict(),
            "support_region_mm": self.support_region_mm,
            "residual_model": self.residual_model.to_yaml_dict() if self.residual_model is not None else None,
            "fit_residual_px": self.fit_residual_px,
            "reference_image_shape": list(int(v) for v in self.reference_image_shape),
            "reference_full_ranges_mm": self.reference_full_ranges_mm,
            "output_defaults": {
                "dpi": int(self.output_dpi),
            },
        }

    @classmethod
    def from_yaml_dict(cls, data: Dict[str, object]) -> "LineScanPlanarCalibration":
        """从 YAML 字典加载（支持 schema_version 1 和 2）"""
        schema_version = int(data.get("schema_version", 1))
        
        # 处理不同版本的字段位置
        if schema_version >= 2:
            # schema_version 2: board.square_size_mm, source_x_axis_model, etc.
            board = data.get("board", {})
            square_size_mm = float(board.get("square_size_mm", 20.0))
            pixels_per_square = int(board.get("pixels_per_square", 236))
            
            axis_mapping = dict(data.get("axis_mapping", {}))
            
            source_x_model = RobustAxisModel.from_yaml_dict(data["source_x_axis_model"])
            source_y_model = RobustAxisModel.from_yaml_dict(data["source_y_axis_model"])
            
            support_region_mm = dict(data.get("calibrated_support_region_mm", {}))
            residual_model = _load_residual_model_from_yaml(
                data.get("residual_correction", {"type": "none"})
            )
            fit_residual_px = dict(data.get("fit_residual_px", {}))
            
            reference = data.get("reference", {})
            reference_image_shape = tuple(int(v) for v in reference.get("image_shape", [0, 0]))
            reference_full_ranges_mm = dict(reference.get("full_extrapolated_region_mm", {}))
            
            output_defaults = data.get("output_defaults", {})
            output_dpi = int(output_defaults.get("dpi", 300))
        else:
            # schema_version 1: 原始格式
            square_size_mm = float(data.get("square_size_mm", 20.0))
            pixels_per_square = int(data.get("pixels_per_square", 236))
            
            axis_mapping = dict(data.get("axis_mapping", {}))
            
            source_x_model = RobustAxisModel.from_yaml_dict(data["source_x_model"])
            source_y_model = RobustAxisModel.from_yaml_dict(data["source_y_model"])
            
            support_region_mm = dict(data.get("support_region_mm", {}))
            residual_model = _load_residual_model_from_yaml(data.get("residual_model"))
            fit_residual_px = dict(data.get("fit_residual_px", {}))
            
            reference_image_shape = tuple(int(v) for v in data.get("reference_image_shape", [0, 0]))
            reference_full_ranges_mm = dict(data.get("reference_full_ranges_mm", {}))
            
            output_defaults = data.get("output_defaults", {})
            output_dpi = int(output_defaults.get("dpi", 300))
        
        return cls(
            square_size_mm=square_size_mm,
            pixels_per_square=pixels_per_square,
            axis_mapping=axis_mapping,
            source_x_model=source_x_model,
            source_y_model=source_y_model,
            support_region_mm=support_region_mm,
            residual_model=residual_model,
            fit_residual_px=fit_residual_px,
            reference_image_shape=reference_image_shape,
            reference_full_ranges_mm=reference_full_ranges_mm,
            output_dpi=output_dpi,
            schema_version=schema_version,
        )


# ==================== YAML 加载 ====================

def _load_residual_model_from_yaml(residual_data: Optional[Dict[str, object]]) -> Optional[TaperedRBFGridResidualModel]:
    """仅当 residual 段为 rbf_tapered_grid 时加载；type=none 或缺失时返回 None。"""
    if not residual_data or not isinstance(residual_data, dict):
        return None
    residual_type = str(residual_data.get("type", "rbf_tapered_grid"))
    if residual_type == "none":
        return None
    if residual_type == "rbf_tapered_grid":
        return TaperedRBFGridResidualModel.from_yaml_dict(residual_data)
    raise ValueError(f"不支持的 residual 类型: {residual_type}")


def load_calibration_yaml(path: PathLike) -> LineScanPlanarCalibration:
    """从 YAML 中读取线阵相机固定工作平面参数。"""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"找不到 YAML：{input_path}")
    with open(input_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return LineScanPlanarCalibration.from_yaml_dict(data)


# ==================== 校正相关函数 ====================

def infer_full_physical_ranges(
    image_shape: Tuple[int, ...],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
) -> Dict[str, float]:
    """根据原图四条边界反推出包含无角点区域在内的完整物理范围。"""
    h, w = image_shape[:2]
    source_x_start = float(source_x_model.inverse(np.array([-0.5]))[0])
    source_x_end = float(source_x_model.inverse(np.array([w - 0.5]))[0])
    source_y_start = float(source_y_model.inverse(np.array([-0.5]))[0])
    source_y_end = float(source_y_model.inverse(np.array([h - 0.5]))[0])

    axis_ranges = {
        source_x_model.physical_col: (source_x_start, source_x_end),
        source_y_model.physical_col: (source_y_start, source_y_end),
    }
    x_start, x_end = axis_ranges["x_mm"]
    y_start, y_end = axis_ranges["y_mm"]
    return {
        "source_x_phys_start": source_x_start,
        "source_x_phys_end": source_x_end,
        "source_y_phys_start": source_y_start,
        "source_y_phys_end": source_y_end,
        "x_mm_min": float(min(x_start, x_end)),
        "x_mm_max": float(max(x_start, x_end)),
        "y_mm_min": float(min(y_start, y_end)),
        "y_mm_max": float(max(y_start, y_end)),
    }


def fixed_step_vector(start: float, end: float, pixels_per_mm: float) -> np.ndarray:
    """生成固定物理步长序列。"""
    span_mm = abs(float(end) - float(start))
    intervals = max(1, int(math.ceil(span_mm * pixels_per_mm)))
    sign = 1.0 if end >= start else -1.0
    return float(start) + sign * np.arange(intervals + 1, dtype=np.float64) / float(pixels_per_mm)


def build_output_vectors(
    full_ranges: Dict[str, float],
    pixels_per_mm: float,
    orientation: str,
) -> Dict[str, np.ndarray]:
    if orientation == "raw":
        return {
            "orientation": np.array(["raw"], dtype=object),
            "col_phys": fixed_step_vector(full_ranges["source_x_phys_start"], full_ranges["source_x_phys_end"], pixels_per_mm),
            "row_phys": fixed_step_vector(full_ranges["source_y_phys_start"], full_ranges["source_y_phys_end"], pixels_per_mm),
        }
    return {
        "orientation": np.array(["board"], dtype=object),
        "col_x_mm": fixed_step_vector(full_ranges["x_mm_min"], full_ranges["x_mm_max"], pixels_per_mm),
        "row_y_mm": fixed_step_vector(full_ranges["y_mm_min"], full_ranges["y_mm_max"], pixels_per_mm),
    }


def generate_map_chunk(
    vectors: Dict[str, np.ndarray],
    row_start: int,
    row_end: int,
    image_shape: Tuple[int, ...],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    residual_model: Optional[TaperedRBFGridResidualModel],
    clip_map_to_image: bool,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
    orientation = str(vectors["orientation"][0])
    if orientation == "board":
        board_x_mm, board_y_mm = np.meshgrid(vectors["col_x_mm"], vectors["row_y_mm"][row_start:row_end])
    else:
        col_grid, row_grid = np.meshgrid(vectors["col_phys"], vectors["row_phys"][row_start:row_end])
        if source_x_model.physical_col == "x_mm":
            board_x_mm, board_y_mm = col_grid, row_grid
        else:
            board_y_mm, board_x_mm = col_grid, row_grid

    source_x_input = board_x_mm if source_x_model.physical_col == "x_mm" else board_y_mm
    source_y_input = board_x_mm if source_y_model.physical_col == "x_mm" else board_y_mm
    map_x = source_x_model(source_x_input)
    map_y = source_y_model(source_y_input)

    if residual_model is not None:
        correction_x, correction_y = residual_model(np.column_stack([board_x_mm.ravel(), board_y_mm.ravel()]))
        map_x += correction_x.reshape(map_x.shape)
        map_y += correction_y.reshape(map_y.shape)

    raw_stats = {
        "raw_map_x_min": float(np.min(map_x)),
        "raw_map_x_max": float(np.max(map_x)),
        "raw_map_y_min": float(np.min(map_y)),
        "raw_map_y_max": float(np.max(map_y)),
    }

    if clip_map_to_image:
        h, w = image_shape[:2]
        map_x = np.clip(map_x, 0.0, float(w - 1))
        map_y = np.clip(map_y, 0.0, float(h - 1))

    return map_x.astype(np.float32), map_y.astype(np.float32), raw_stats


def remap_full_image_in_chunks(
    image: np.ndarray,
    vectors: Dict[str, np.ndarray],
    source_x_model: RobustAxisModel,
    source_y_model: RobustAxisModel,
    residual_model: Optional[TaperedRBFGridResidualModel],
    interpolation: int,
    chunk_rows: int,
    clip_map_to_image: bool,
) -> Tuple[np.ndarray, Dict[str, float]]:
    orientation = str(vectors["orientation"][0])
    if orientation == "board":
        out_h, out_w = len(vectors["row_y_mm"]), len(vectors["col_x_mm"])
    else:
        out_h, out_w = len(vectors["row_phys"]), len(vectors["col_phys"])

    output = allocate_output(image, out_h, out_w)
    stats = {
        "raw_map_x_min": math.inf,
        "raw_map_x_max": -math.inf,
        "raw_map_y_min": math.inf,
        "raw_map_y_max": -math.inf,
        "used_map_x_min": math.inf,
        "used_map_x_max": -math.inf,
        "used_map_y_min": math.inf,
        "used_map_y_max": -math.inf,
    }

    for y0 in range(0, out_h, chunk_rows):
        y1 = min(y0 + chunk_rows, out_h)
        map_x, map_y, raw_stats = generate_map_chunk(
            vectors=vectors,
            row_start=y0,
            row_end=y1,
            image_shape=image.shape,
            source_x_model=source_x_model,
            source_y_model=source_y_model,
            residual_model=residual_model,
            clip_map_to_image=clip_map_to_image,
        )
        output[y0:y1] = cv2.remap(
            image,
            map_x,
            map_y,
            interpolation=interpolation,
            borderMode=cv2.BORDER_REPLICATE,
        )

        for key in ["raw_map_x_min", "raw_map_y_min"]:
            stats[key] = min(stats[key], raw_stats[key])
        for key in ["raw_map_x_max", "raw_map_y_max"]:
            stats[key] = max(stats[key], raw_stats[key])
        stats["used_map_x_min"] = min(stats["used_map_x_min"], float(np.min(map_x)))
        stats["used_map_x_max"] = max(stats["used_map_x_max"], float(np.max(map_x)))
        stats["used_map_y_min"] = min(stats["used_map_y_min"], float(np.min(map_y)))
        stats["used_map_y_max"] = max(stats["used_map_y_max"], float(np.max(map_y)))
        print(f"[remap] rows={y0:6d}..{y1:6d} / {out_h}")

    return output, {key: float(value) for key, value in stats.items()}


@dataclass
class RectificationOptions:
    """执行图像矫正时使用的参数。"""
    
    orientation: str = "raw"
    interpolation: str = "cubic"
    chunk_rows: int = 256
    clip_map_to_image: bool = True
    output_dpi: int = 300
    preview_max_side: int = 1800

    def validate(self) -> None:
        if self.output_dpi <= 0:
            raise ValueError("output_dpi 必须 > 0。")


@dataclass
class RectificationResult:
    """图像矫正后的结果。"""
    
    corrected_image: np.ndarray
    output_shape: Tuple[int, int]
    full_ranges_mm: Dict[str, float]
    map_stats: Dict[str, float]
    orientation: str


def rectify_image_array(
    image: np.ndarray,
    calibration: LineScanPlanarCalibration,
    options: Optional[RectificationOptions] = None,
) -> RectificationResult:
    """使用已拟合的参数矫正 NumPy 图像数组。"""
    opts = options or RectificationOptions(output_dpi=calibration.output_dpi)
    opts.validate()

    full_ranges = infer_full_physical_ranges(image.shape, calibration.source_x_model, calibration.source_y_model)
    vectors = build_output_vectors(full_ranges, calibration.pixels_per_mm, opts.orientation)

    effective_chunk_rows = int(opts.chunk_rows)
    if calibration.residual_model is not None and effective_chunk_rows > 128:
        effective_chunk_rows = 128

    corrected, map_stats = remap_full_image_in_chunks(
        image=image,
        vectors=vectors,
        source_x_model=calibration.source_x_model,
        source_y_model=calibration.source_y_model,
        residual_model=calibration.residual_model,
        interpolation=interpolation_flag(opts.interpolation),
        chunk_rows=effective_chunk_rows,
        clip_map_to_image=opts.clip_map_to_image,
    )
    return RectificationResult(
        corrected_image=corrected,
        output_shape=(int(corrected.shape[0]), int(corrected.shape[1])),
        full_ranges_mm=full_ranges,
        map_stats=map_stats,
        orientation=opts.orientation,
    )


def rectify_image_file(
    image_path: PathLike,
    calibration: LineScanPlanarCalibration,
    corrected_output_path: PathLike,
    preview_output_path: Optional[PathLike] = None,
    options: Optional[RectificationOptions] = None,
) -> RectificationResult:
    """读取扫描图、执行矫正并保存 TIFF。"""
    image = load_image_unchanged(Path(image_path))
    opts = options or RectificationOptions(output_dpi=calibration.output_dpi)
    result = rectify_image_array(
        image=image,
        calibration=calibration,
        options=opts,
    )
    
    # 将校正图向左旋转90度（逆时针）
    rotated_image = cv2.rotate(result.corrected_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    
    save_image_with_dpi(corrected_output_path, rotated_image, dpi=opts.output_dpi)
    if preview_output_path is not None:
        preview = make_preview(rotated_image, max_side=opts.preview_max_side)
        save_image_with_dpi(preview_output_path, preview, dpi=opts.output_dpi)

    print(f"[done] {image_path} -> {corrected_output_path}  shape={rotated_image.shape}  dpi={opts.output_dpi}")
    
    # 返回结果时也使用旋转后的图像
    result.corrected_image = rotated_image
    result.output_shape = (int(rotated_image.shape[0]), int(rotated_image.shape[1]))
    return result


# ==================== 对外接口 ====================

def rectify_charuco_image(
    yaml_path: PathLike,
    image: Union[PathLike, np.ndarray],
    orientation: str = "raw",
    interpolation: str = "cubic",
    chunk_rows: int = 256,
    clip_map_to_image: bool = True,
    rotate_counterclockwise_90: bool = True,
) -> np.ndarray:
    """
    使用标定 YAML 校正线阵扫描图，返回单通道灰度 ndarray (H, W)。

    参数:
        yaml_path: 标定参数 YAML 路径（如 xxx_calib.yaml）
        image: 待校正图像路径，或已读取的 BGR/灰度 ndarray
        orientation: 输出方向，"raw" 或 "board"
        interpolation: 重映射插值，nearest / linear / cubic / lanczos
        chunk_rows: 分块 remap 行数
        clip_map_to_image: 是否将映射裁剪到输入图像范围
        rotate_counterclockwise_90: 是否与 GUI 标定流程一致，逆时针旋转 90°

    返回:
        校正后的灰度图，shape 为 (height, width)
    """
    calibration = load_calibration_yaml(yaml_path)
    if isinstance(image, (str, Path)):
        img = load_image_unchanged(Path(image))
    else:
        img = np.asarray(image)

    opts = RectificationOptions(
        orientation=orientation,
        interpolation=interpolation,
        chunk_rows=chunk_rows,
        clip_map_to_image=clip_map_to_image,
        output_dpi=int(calibration.output_dpi),
    )
    result = rectify_image_array(img, calibration, options=opts)
    out = result.corrected_image
    if rotate_counterclockwise_90:
        out = cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return ensure_grayscale(out)
