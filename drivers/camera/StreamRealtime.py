# -*- coding: utf-8 -*-
"""StreamRealtime.py — 实时打印转发路径的流式拼接引擎适配器。

把 stitch_stream_final.StreamingStitcher（离线拼接的几何权威实现）接进
Camera.ImageStitch 的实时路径，替换旧的"固定画布 + 裁剪窗"引擎。

两套引擎的坐标关系（2026-09-10 用双引擎同帧校正实测，T/F 两个方向均验证，
peak 0.89+）：

    旧引擎条带 (swath 行, travel 列) = 流式条带 (travel 行, swath 列)
    旧 swath 行 r   <-> 流式 swath 列 (SW-1 - r)   【镜像】
    旧 travel 列 c   <-> 流式 travel 行 c (+0/1)    【同向】

转发带的切法（与旧引擎 stitch_from_ram 逐带同口径，零额外延迟）：
    旧带 k = 条带 k 的 swath 行 [h-f_k-up, h-up) × travel 列 [canvas_start, +W)
    其中 f_k = round((Step_k - Step_{k-1})/K)（旧引擎口径），up = hold_pix。
    在流式画布缓冲（行=travel，列=swath/前进向，列随织物前进而递减）里：
    行窗口 [t0, t0+W)（t0 首帧用旧引擎摆放常数锚定，之后固定——流式的
    双向闭环让织物在缓冲里位置稳定，比旧路径更跟布），列
    [cx_k + SW-1-r_hi, cx_k + SW-1-r_lo) 反向 + 转置。
    -> 带内容/织物相位/y_step 与旧路径完全同口径，只有缝质量变成 C 级。

内存有界：转发完即裁掉右侧旧画布列（只删高位列，坐标簿记零调整；
配对测量只读缓存条带的相对坐标，不受影响）。
"""
from __future__ import annotations

import os
import sys
from collections import OrderedDict

import cv2
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import stitch_stream_final as S  # noqa: E402

# 实时模式下没有文件：带 RealtimePath 键的条目走虚拟路径，其余回落原实现
# （离线路径的 JSON 条目没有这个键，行为不变）。
_orig_resolve_image_path = S.resolve_image_path


def _rt_resolve_image_path(data_dir, entry, index):
    rt = entry.get("RealtimePath")
    if rt is not None:
        return str(rt)
    return _orig_resolve_image_path(data_dir, entry, index)


S.resolve_image_path = _rt_resolve_image_path


class _InMemCache:
    """实时用的已校正条带缓存：raw 帧由调用方喂入，按需校正（LRU 4 条）。

    预校正线程：帧到达即后台校正（cv2.remap 释放 GIL，可与逐窗相位相关
    真正并行），push 取用时等待结果——实时路径的关键提速。
    """

    def __init__(self, true_cal, false_cal, prefetch=True):
        self._cals = (true_cal, false_cal)
        self._raws = {}
        self._rect = OrderedDict()
        self._futures = {}
        self._pool = None
        if prefetch:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rt-rectify')

    def _rectify(self, index, image, direction):
        img = image if direction else cv2.flip(image, 1)
        out = S.rectify_image_array(img, self._cals[0 if direction else 1],
                                    S.RECTIFY_OPTIONS)
        return S.ensure_grayscale(out)

    def put_raw(self, index, image, direction):
        self._raws[index] = image
        if self._pool is not None:
            self._futures[index] = self._pool.submit(self._rectify, index, image, direction)

    def drop_raw(self, index):
        self._raws.pop(index, None)
        fut = self._futures.pop(index, None)
        if fut is not None and not fut.done():
            fut.cancel()

    def get(self, record):
        index = int(record["index"])
        if index in self._rect:
            img = self._rect.pop(index)
            self._rect[index] = img
            return img
        fut = self._futures.pop(index, None)
        if fut is not None:
            out = fut.result()
        else:
            direction = bool(record["direction"])
            out = self._rectify(index, self._raws[index], direction)
        self._rect[index] = out
        while len(self._rect) > 4:
            self._rect.popitem(last=False)
        return out

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None


class StreamRealtime(object):
    """实时流式拼接。用法（每帧一次，按到达顺序）：

        rt = StreamRealtime(true_yaml, false_yaml, ...)
        for frame in frames:
            bands = rt.feed_frame(image, step, direction, msp)
            for band, y_step in bands:   # MSP=0 首帧会积压几帧后一起释放
                forward(band, y_step)    # 与旧路径 (fresh, y_step) 同口径
    """

    # 滚动裁剪：当前带右缘之外再保留的画布列数（前进向）
    _KEEP_COLS = 6000

    def __init__(self, true_yaml, false_yaml, *,
                 d_step_x, x_offset_false, seam_inset,
                 canvas_start, canvas_width, hold_pix,
                 x_base_L, x_base_R, x_invert, DPI=300,
                 log_cb=None):
        self._yaml = (os.fspath(true_yaml), os.fspath(false_yaml))
        self._d_step_x = float(d_step_x)
        self._x_offset_false = float(x_offset_false)
        self._seam_inset = int(seam_inset)
        self._canvas_start = int(canvas_start)
        self._canvas_width = int(canvas_width)
        self._hold_pix = int(hold_pix)
        self._x_base = (int(x_base_L), int(x_base_R))
        self._x_invert = int(x_invert)
        self._K = (25.4 / float(DPI)) * 10000.0
        self._log_cb = log_cb
        self._reset_state()

    # ------------------------------------------------------------------ state

    def _reset_state(self):
        if getattr(self, '_cache', None) is not None:
            self._cache.close()
        self._stitcher = None
        self._feed = None
        self._cache = None
        self._infos = []
        self._index = 0            # 下一个到达的帧号
        self._next_to_place = 0    # 下一个待摆放的帧号
        self._step_copy = 0.0      # 旧引擎口径的 StepCopy
        self._t0 = None            # travel 向固定窗口（缓冲行）

    def reset(self):
        self._reset_state()

    def _log(self, msg):
        if self._log_cb:
            self._log_cb(str(msg))

    # ------------------------------------------------------------------ feed

    def _init_stitcher(self):
        # 加速内核（数值等价，见 fastcore.py 的对照说明）：实时路径必须在
        # 本进程内安装——Camera 跑在 ProcessProxy 子进程里，主进程装过不算
        try:
            import fastcore
            fastcore.install(use_gpu=False, no_diag=True)
        except Exception as exc:
            self._log("StreamRealtime: fastcore unavailable (%s); "
                      "using the original (slower) path" % exc)
        # 逐机常数注入（v1 用模块全局，与离线 CLI 同一机制）
        S.D_STEP_X = self._d_step_x
        S.X_OFFSET_FALSE_PX = self._x_offset_false
        true_cal = S.load_calibration_yaml(self._yaml[0])
        false_cal = S.load_calibration_yaml(self._yaml[1])
        self._cache = _InMemCache(true_cal, false_cal)
        self._feed = S.CausalInfoFeed(self._infos)
        # v7 标定自带 cross_term：在线 skew 冷启动归零（双计保护，与离线一致）
        zeroed = S._yaml_requires_online_skew_zero([self._yaml[0], self._yaml[1]])
        if zeroed:
            skew_s, antisym = 0.0, 0.0
        else:
            skew_s, antisym = S.COLD_START_SKEW_S, S.COLD_START_ANTISYM
        self._stitcher = S.StreamingStitcher(
            data_dir='.', feed=self._feed,
            true_calibration=true_cal, false_calibration=false_cal,
            true_yaml=self._yaml[0], false_yaml=self._yaml[1],
            skew_s=skew_s, antisym=antisym,
            subpixel=True, online_fit=True, loop_closure=True, feedback=True,
            rectified_cache=self._cache,
            x_feedback=True, x_loop_mode='adjacent-first',
            subpixel_x=True, x_local_pose=False,
            seam_inset_px=self._seam_inset)
        self._log("StreamRealtime: engine ready (d_step_x=%.4f, x_offset_false=%.4f, "
                  "seam_inset=%d)" % (self._d_step_x, self._x_offset_false, self._seam_inset))

    def feed_frame(self, image, step, direction, msp):
        """喂入一帧（按到达顺序），返回本帧释放出的 [(band, y_step), ...]。"""
        if self._stitcher is None:
            self._init_stitcher()
        self._infos.append({"Info": {"Step": float(step),
                                     "Direction": bool(direction),
                                     "MotionStartPoint": float(msp)},
                            "RealtimePath": "rt://%d.tif" % self._index})
        self._feed.arrive(self._index)
        self._cache.put_raw(self._index, image, bool(direction))

        bands = []
        while self._next_to_place <= self._index:
            ok, _why = self._stitcher.can_place(self._next_to_place)
            if not ok:
                break
            self._stitcher.push(self._next_to_place)
            band = self._cut_band(self._next_to_place)
            if band is not None:
                bands.append(band)
            self._cache.drop_raw(self._next_to_place - 3)
            self._next_to_place += 1
        self._index += 1
        return bands

    # ------------------------------------------------------------------ band

    def _anchor_t0(self):
        """首帧锚定 travel 向固定窗口（等价旧引擎 frame-0 摆放后的画布窗口）。"""
        rec0 = self._stitcher.records[0]
        d0 = bool(rec0["direction"])
        base = int(self._x_base[0 if d0 else 1] / self._K)
        align0 = round(float(rec0["original_msp"]) / self._K) - base
        e0 = align0 + (0 if d0 else self._x_invert)
        self._t0 = int(rec0["canvas_y"]) + self._canvas_start + e0
        self._log("StreamRealtime: window anchored t0=%d (canvas_y0=%d, "
                  "canvas_start=%d, E0=%d)" % (self._t0, rec0["canvas_y"],
                                               self._canvas_start, e0))

    def _cut_band(self, k):
        """从流式画布缓冲切出第 k 带（旧引擎口径），并滚动裁剪缓冲。"""
        if self._t0 is None:
            self._anchor_t0()
        st = self._stitcher
        rec = st.records[k]
        buffer = st._buffer
        if buffer is None:
            return None

        # 旧引擎口径的带宽 f_k（含首帧 lead-in）
        step = float(self._infos[k]["Info"]["Step"])
        f_k = int(round((step - self._step_copy) / self._K))
        self._step_copy = step
        if f_k <= 0:
            return None

        sw = int(rec["corrected_width"])           # 条带 swath 向宽度
        r_hi = sw - self._hold_pix                 # 旧 fresh = [h-f-up, h-up)
        r_lo = max(0, sw - self._hold_pix - f_k)
        f_k = r_hi - r_lo
        cx = int(rec["canvas_x"])
        c0 = cx + (sw - 1 - r_hi)                  # swath 镜像后的列范围
        c1 = cx + (sw - 1 - r_lo)
        if c0 < 0 or c1 > buffer.shape[1]:
            return None

        t0 = self._t0
        W = self._canvas_width
        H_buf = buffer.shape[0]

        # travel 窗口（越界补零，语义同旧引擎的 np.pad）
        row_lo = max(0, t0)
        row_hi = min(H_buf, t0 + W)
        if row_hi <= row_lo:
            return None
        block = buffer[row_lo:row_hi, c0:c1]        # (W', f_k)
        # 前进向反序（缓冲列随织物前进而递减）后转置 -> (f_k, W')
        band = block[:, ::-1].T.copy()
        if band.shape[1] != W:
            padded = np.zeros((f_k, W), dtype=buffer.dtype)
            col_lo = max(0, -t0)
            take = min(W - col_lo, band.shape[1])
            padded[:, col_lo:col_lo + take] = band[:, :take]
            band = padded

        # 滚动裁剪：只删右侧（高位）已转发旧列 —— col↔raw_x = col + x_of_col0，
        # 删高位列不改变任何现存坐标，簿记零调整
        keep_n = c1 + self._KEEP_COLS
        if buffer.shape[1] > keep_n:
            st._buffer = buffer[:, :keep_n].copy()
            if st._max_col is not None:
                st._max_col = min(int(st._max_col), keep_n)

        return band, f_k
