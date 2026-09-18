#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""stitch_stream_finalv2.py — 一步产出**已补偿跨方向边缘视差**的成图。

= stitch_stream_final.py（拼接，几何的唯一权威实现）+ 边缘视差补偿（本文件自带）

为什么要合成一个脚本
--------------------
上一版是"跑 stitch_stream_final.py 出 stitch/，再跑 tools/edge_parallax_compensate.py
出 stitch_fixed/"，两步、两个目录、容易把中间产物当成品。本脚本合成一条命令，补偿逻辑
全部内联，只保留一个外部依赖。

关于 k（README §13 里标着"待标定"的那个量）
------------------------------------------
纸边处有高度突变（承台 0 → 纸面 h）。镜头主光线若不严格垂直（非远心，有倾角 θ），
高度 h 的物体看起来会横向位移：

    d = h · tan(θ)          d_px = h_mm · tan(θ) · ppm(11.811)
    k = d_px / h_mm   [px/mm]        tan(θ) = k / 11.811

README 原计划：垫 0.1/0.2/0.5 mm 垫片在纸边下重扫 → 量"台阶 vs 厚度"的斜率得到 k →
以后只要知道纸厚就能**算出**该修多少。

本脚本**绕开 k**：不去预测，直接在成图上把每条缝、每条边的台阶量出来。k 剩下的唯一用途
是给量出的 P(e) 一个 mm 刻度（判断"这条边的台阶有多高"、值不值得动硬件），它不再是
补偿的前置条件。

补偿为什么必须是"每边、局部、带过渡"
------------------------------------
决定性证据（README §13 自己的数）：同一条缝上，**纸内部笔迹 e_scan = −0.08 px，而纸边
台阶 +1.03 px**。纸内部没跟着纸边一起动 => 效果局限在纸边附近，**整行/整带平移必然错**
（那正是 §13 已实测否定的做法）。所以本脚本只在该条边附近施加位移，几百 px 内
raised-cosine 衰减到 0。

本机实测：缝上台阶 |rms| 0.768 → 0.031 px，max 2.075 → 0.075 px；代价是 11% 的列被
重采样、被修正列锐度 −4.3%，而**核外发生变化的列 = 0**（纸内部逐字节没动）。

依赖
----
只依赖同目录的 `stitch_stream_final.py`（拼接器）。**故意不复制它的 3187 行**：README 自己
定过"map 的生成语义只能有一份权威实现，复制出来早晚和它悄悄分叉"，而且拼接器一旦升级，
本脚本自动跟上。补偿部分（含缝定位）全部内联。
只想对已有结果做补偿时用 `--from-run <目录>`，此时不需要任何外部脚本。

用法
----
    # 一步：拼接 + 补偿
    python stitch_stream_finalv2.py --output-dir out_v2 \
        --data-dir ..\20260903180520 \
        --true-yaml calib\4_final_calib.yaml --false-yaml calib\5_final_calib.yaml \
        --workers 8 --d-step-x 846.0527400801201 --x-offset-false 5.2406 \
        --seam-inset 384 --x-feedback

    # 只对已有结果做补偿（不重新拼接）
    python stitch_stream_finalv2.py --from-run stitch --output-dir out_v2

    # 只要拼接、不要补偿
    python stitch_stream_finalv2.py --output-dir out_base ... --no-parallax

产出（--output-dir）
--------------------
    stitched_<s>_<e>_stream.tif        补偿后的成图（同名同规格，可直接喂 tools/*.py）
    stream_frame_log.csv 等            从拼接产物原样拷来（评估器靠它们定位缝）
    edge_parallax_report.json          逐缝逐边的量测 / 施加量 / 复核
    edge_parallax_verify.txt           修正前后台阶对比
    _base_stitch/                      未补偿的中间产物（A/B 用；--no-keep-base 删除）
    zoom_<col>_<seam>_before/after.png 最严重几处的放大图
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

CHUNK_ROWS = 128


# ══════════════════════════════════════════════ 边的跟踪与量测

def half_max_crossings(profile: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """50% 交叉（亚像素，线性插值）。

    判据必须写成"含零穿越"而不是 `s[i-1]*s[i] < 0`：后者在**某个像素灰度正好等于阈值**时
    乘积为 0、不算变号，交叉点丢失、整段跟踪就在这里断掉（实测 row 4533 灰度正好 = 阈值
    95，于是那一行的量测整条变成 NaN）。tools/sheet_edge_step.py 里是同一个写法，
    README §13 表中那批"跟踪失败"有一半就是这个原因，不是真的没边。
    """
    t = 0.5 * (lo + hi)
    s = profile - t
    out = []
    for i in range(1, len(s)):
        if not ((s[i - 1] < 0 <= s[i]) or (s[i - 1] > 0 >= s[i])):
            continue
        den = s[i - 1] - s[i]
        out.append((i - 0.5) if den == 0 else (i - 1) + s[i - 1] / den)
    return np.asarray(out, dtype=float)


def strong_crossings(prof: np.ndarray, lo: float, hi: float, min_sep: int,
                     contrast_frac: float = 0.5, margin: int = 60) -> list[float]:
    keep: list[float] = []
    for e in half_max_crossings(prof, lo, hi):
        i = int(round(e))
        if i < margin or i >= len(prof) - margin:
            continue
        left = prof[max(0, i - margin):max(0, i - 10)].mean()
        right = prof[min(len(prof) - 1, i + 10):min(len(prof) - 1, i + margin)].mean()
        if abs(right - left) < contrast_frac * (hi - lo):
            continue
        if keep and e - keep[-1] < min_sep:
            continue
        keep.append(float(e))
    return keep


def locate_near(prof: np.ndarray, lo: float, hi: float, target: float,
                tol: float) -> float | None:
    xs = half_max_crossings(prof, lo, hi)
    if xs.size == 0:
        return None
    j = int(np.argmin(np.abs(xs - target)))
    return float(xs[j]) if abs(xs[j] - target) <= tol else None


def edge_track(img: np.ndarray, start_row: int, end_row: int, hint: float,
               lo: float, hi: float, win: int = 12) -> tuple[np.ndarray, np.ndarray]:
    rows = np.arange(start_row, end_row, 1 if end_row > start_row else -1)
    pos = np.full(len(rows), np.nan)
    cur = float(hint)
    for i, r in enumerate(rows):
        a, b = int(round(cur)) - win, int(round(cur)) + win + 1
        if a < 0 or b >= img.shape[1]:
            break
        xs = half_max_crossings(img[r, a:b].astype(np.float32), lo, hi)
        if xs.size == 0:
            break
        j = int(np.argmin(np.abs(xs + a - cur)))
        cur = float(xs[j] + a)
        pos[i] = cur
    return rows, pos


def edge_width_10_90(prof: np.ndarray, col: float, lo: float, hi: float,
                     win: int = 80) -> float:
    """边的 10~90% 上升宽度（px），用来定核函数的平台半宽。"""
    i = int(round(col))
    seg = prof[max(0, i - win):min(len(prof), i + win)]
    if seg.size < 6:
        return 20.0
    rising = seg[-1] >= seg[0]
    v10, v90 = lo + 0.1 * (hi - lo), lo + 0.9 * (hi - lo)

    def cross(level: float) -> float | None:
        s = seg - level
        for k in range(1, len(s)):
            if (s[k - 1] < 0 <= s[k]) if rising else (s[k - 1] > 0 >= s[k]):
                return (k - 1) + s[k - 1] / (s[k - 1] - s[k])
        return None

    c10, c90 = cross(v10), cross(v90)
    return float(abs(c90 - c10)) if (c10 is not None and c90 is not None) else 20.0


def measure_step(img: np.ndarray, seam: int, ce: float, lo: float, hi: float,
                 win: int = 120, gap: int = 8, tol: float = 60.0, tries: int = 3):
    """量某条边在某条缝上的列向台阶。返回 (step, 拟合残差, 边列) 或 None。

    同一个"边"附近常有多个 50% 交叉（纸边旁常伴一条暗线），只取"离目标列最近的那一个"
    会在两条交叉相距十几 px 时挑错，表现为整段跟踪失败（实测 21813 附近有 21807 / 21821
    两条，挑到 21807 必然失败）。所以取最近的 tries 个候选两两组合，返回**能跟踪且拟合
    残差最小**的那一组。
    """
    h = img.shape[0]

    def prof_at(r: int) -> np.ndarray:
        r = int(np.clip(r, 4, h - 5))
        return img[r - 3:r + 4].mean(axis=0).astype(np.float32)

    def cands_at(r: int) -> list[float]:
        xs = half_max_crossings(prof_at(r), lo, hi)
        xs = xs[np.abs(xs - ce) <= tol]
        return sorted((float(x) for x in xs), key=lambda x: abs(x - ce))[:tries]

    ca, cb = cands_at(seam - 200), cands_at(seam + 200)
    if not ca or not cb or seam - gap - 1 - win < 0 or seam + gap + 1 + win >= h:
        return None

    def fit(rr, cc):
        k, b = np.polyfit(rr, cc, 1)
        resid = float(np.sqrt(np.mean((cc - (k * rr + b)) ** 2)))
        return float(k), float(b), resid

    best = None
    for ha in ca:
        for hb in cb:
            ra, pa = edge_track(img, seam - gap - 1, seam - gap - 1 - win, ha, lo, hi)
            rb, pb = edge_track(img, seam + gap + 1, seam + gap + 1 + win, hb, lo, hi)
            oa, ob = np.isfinite(pa), np.isfinite(pb)
            if oa.sum() < win * 0.5 or ob.sum() < win * 0.5:
                continue
            ka, ba, rva = fit(ra[oa], pa[oa])
            kb, bb, rvb = fit(rb[ob], pb[ob])
            ya, yb = ka * seam + ba, kb * seam + bb
            cand = (float(yb - ya), max(rva, rvb), float(0.5 * (ya + yb)))
            if best is None or cand[1] < best[1]:
                best = cand
    return best


# ══════════════════════════════════════════════ 版面：缝 / 条带

def seam_rows(run_dir: Path, img: np.ndarray) -> list[dict]:
    """每条缝在成图里的行号：由 frame log 推出候选，再吸附到图上真实的不连续行。

    与 tools/eval_line_smoothness.py 的 seam_rows 同一算法，内联以免多一个文件依赖。
    条带 index 递增而 buffer_col 递减，所以 index 越大行号越小；推导容易差一个常数，
    故再用行方向梯度峰值吸附一次。
    """
    with open(run_dir / "stream_frame_log.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or "paste_width" not in rows[0]:
        return []
    col = [int(x["buffer_col"]) for x in rows]
    base = min(col)
    prof = np.abs(np.diff(img[:, ::37].astype(np.float32), axis=0)).mean(axis=1)
    out = []
    for k in range(len(rows) - 1):
        guess = (col[k] - base) + int(rows[k + 1]["seam_inset_px"])
        lo, hi = max(1, guess - 40), min(len(prof), guess + 40)
        snapped = int(lo + int(np.argmax(prof[lo:hi]))) if hi > lo else guess
        out.append({"pair": f"{k}_{k + 1}", "row": snapped, "row_from_log": guess})
    return out


def layout(run: Path, img: np.ndarray, log_rows: list[dict]):
    """返回 (缝按行升序, 条带行范围, 条带->方向)。"""
    seams = sorted(seam_rows(run, img), key=lambda s: s["row"])
    dirs = {int(r["index"]): str(r["direction"]).strip().lower() == "true"
            for r in log_rows}
    h = img.shape[0]
    below_of: dict[int, int] = {}
    for s in seams:
        a, _b = (int(v) for v in s["pair"].split("_"))
        below_of[int(s["row"])] = a
    bounds: dict[int, tuple[int, int]] = {}
    top = 0
    for seam_row in sorted(below_of):          # 行升序 -> 条带号降序
        k = below_of[seam_row]
        bounds[k + 1] = (top, seam_row)
        top = seam_row
    bounds[0] = (top, h)
    return seams, bounds, dirs


def detect_edges(img: np.ndarray, bounds: dict[int, tuple[int, int]],
                 min_sep: int = 200, min_hits: int = 3) -> tuple[list[float], int]:
    """在每条带内部（远离缝 ±150 行）找强边，跨条带聚类成"贯穿卷长"的纸边。"""
    found: list[float] = []
    for _k, (t, b) in sorted(bounds.items()):
        a, c = t + 150, b - 150
        if c - a < 80:
            continue
        prof = img[a:c].mean(axis=0).astype(np.float32)
        lo, hi = float(np.percentile(prof, 1)), float(np.percentile(prof, 99))
        if hi - lo < 40:
            continue
        found.extend(strong_crossings(prof, lo, hi, min_sep))
    found.sort()
    clusters: list[list[float]] = []
    for e in found:
        if clusters and e - clusters[-1][-1] <= 80:
            clusters[-1].append(e)
        else:
            clusters.append([e])
    return [float(np.median(cl)) for cl in clusters if len(cl) >= min_hits], len(found)


# ══════════════════════════════════════════════ 核函数与施加

def kernel_terms(col: np.ndarray, centers: list[float], amps: list[float],
                 plateaus: list[float], ramp: float) -> np.ndarray:
    """每条边一个位移核：|u| <= plateau 恒为 1，之后 raised-cosine 在 ramp px 内衰减到 0。"""
    field = np.zeros(col.shape, dtype=np.float32)
    for c, amp, plat in zip(centers, amps, plateaus):
        if amp == 0.0:
            continue
        t = np.clip((np.abs(col - float(c)) - float(plat)) / float(ramp), 0.0, 1.0)
        field += float(amp) * 0.5 * (1.0 + np.cos(np.pi * t))
    return field


def apply_field(img: np.ndarray, bounds: dict[int, tuple[int, int]],
                disp: dict[int, np.ndarray]) -> np.ndarray:
    """逐条带施加逐列位移场；位移 D 把位于 x 的内容搬到 x + D。

    不用 cv2.remap：它有 `cols < SHRT_MAX(32767)` 的硬限制，成图宽 34559 超了。
    位移只有 ±2 px 量级，直接做亚像素 gather 更简单：
        D = i + f (i 整数部分, 0 <= f < 1)
        out[j] = (1-f) * in[j-i] + f * in[j-i-1]
    """
    out = np.empty_like(img)
    w = img.shape[1]
    ar = np.arange(w, dtype=np.int64)
    for k, (t, b) in sorted(bounds.items()):
        d = disp.get(k)
        if d is None or not np.any(d):
            out[t:b] = img[t:b]
            continue
        i_part = np.floor(d).astype(np.int64)
        f_part = (d - i_part).astype(np.float32)
        idx_a = np.clip(ar - i_part, 0, w - 1)
        idx_b = np.clip(idx_a - 1, 0, w - 1)
        wa = (1.0 - f_part).astype(np.float32)
        for y0 in range(t, b, CHUNK_ROWS):
            y1 = min(y0 + CHUNK_ROWS, b)
            block = img[y0:y1]
            out[y0:y1] = np.clip(
                block[:, idx_a].astype(np.float32) * wa[None, :]
                + block[:, idx_b].astype(np.float32) * f_part[None, :] + 0.5,
                0, 255).astype(img.dtype)
    return out


# ══════════════════════════════════════════════ 补偿

def compensate(img: np.ndarray, run: Path, log_rows: list[dict], a) -> tuple[np.ndarray, dict]:
    h, w = img.shape
    seams, bounds, dirs = layout(run, img, log_rows)
    print(f"  {len(seams)} 条缝: " + "  ".join(f"{s['pair']}@{s['row']}" for s in seams))
    if len(seams) < 2:
        raise SystemExit("缝定位失败（frame log 里没有 paste_width？）")

    edges, n_raw = detect_edges(img, bounds, a.min_sep, a.min_hits)
    print(f"  贯穿卷长的强边 {len(edges)} 条（{n_raw} 次命中，>= {a.min_hits} 次）: "
          + "  ".join(f"{e:.0f}" for e in edges))
    if not edges:
        raise SystemExit("没有找到可用的强边，放弃（不要拿噪声去修图）")

    mid = bounds[4][0] + 150 if 4 in bounds else bounds[max(bounds)][0] + 150
    prof_mid = img[mid - 3:mid + 4].mean(axis=0).astype(np.float32)
    lo_mid, hi_mid = float(np.percentile(prof_mid, 1)), float(np.percentile(prof_mid, 99))
    widths = [edge_width_10_90(prof_mid, e, lo_mid, hi_mid) for e in edges]

    # ---- 逐缝逐边量台阶 ----
    obs: list[dict] = []
    for s in seams:
        a_i, _b_i = (int(v) for v in s["pair"].split("_"))
        seam, below = int(s["row"]), a_i
        tau = 1.0 if dirs[below] else -1.0
        r = int(np.clip(seam - 200, 4, h - 5))
        pr = img[r - 3:r + 4].mean(axis=0).astype(np.float32)
        lo, hi = float(np.percentile(pr, 1)), float(np.percentile(pr, 99))
        for ce in edges:
            m = measure_step(img, seam, ce, lo, hi)
            if m is None:
                obs.append({"pair": s["pair"], "seam": seam, "edge": ce,
                            "tau": tau, "ok": False, "why": "跟踪失败"})
                continue
            step, resid, col = m
            ok = resid <= a.max_resid and abs(step) <= a.max_abs_step
            obs.append({"pair": s["pair"], "seam": seam, "edge": ce, "col": col,
                        "tau": tau, "step": round(step, 3), "resid": round(resid, 3),
                        "ok": bool(ok),
                        "why": "" if ok else ("拟合残差过大" if resid > a.max_resid
                                              else "台阶过大(跳线)")})
    good = [o for o in obs if o["ok"]]
    print(f"  有效量测 {len(good)} / {len(obs)}")
    if not good:
        raise SystemExit("没有任何有效量测，放弃（不要拿噪声去修图）")

    # ---- 池化 P(e)：tau*step 在所有缝上的中位数（对离群点稳）----
    print("  每条边的视差幅值 P(e)（同一张纸的左右边应反号）")
    print(f"    {'边列':>9}{'P px':>9}{'n':>4}{'宽':>7}  各缝 tau*step")
    pooled: dict[float, float] = {}
    for ei, ce in enumerate(edges):
        vals = [o["tau"] * o["step"] for o in good if abs(o["edge"] - ce) < 1e-6]
        pooled[ce] = float(np.median(vals)) if vals else 0.0
        print(f"    {ce:9.1f}{pooled[ce]:+9.3f}{len(vals):>4}{widths[ei]:7.1f}  "
              + "  ".join(f"{v:+.2f}" for v in vals))

    # ---- 每缝的修正场 ----
    # 符号约定（别再推一遍）：step = yb - ya（下侧边列 - 上侧边列）。位移 D 把位于 x 的特征
    # 搬到 x + D，故"下侧相对上侧"的位移须为 -step。代码里 D[below] = D[above] - field，
    # 所以 field 必须等于 **+step**。复核段会验证：符号错了 after 会是 before 的 2 倍。
    col_axis = np.arange(w, dtype=np.float32)
    fields: dict[int, np.ndarray] = {}
    applied: list[dict] = []
    for s in seams:
        a_i, _b_i = (int(v) for v in s["pair"].split("_"))
        seam, below = int(s["row"]), a_i
        tau = 1.0 if dirs[below] else -1.0
        centers, amps, plats = [], [], []
        for ei, ce in enumerate(edges):
            o = next((x for x in good if x["seam"] == seam
                      and abs(x["edge"] - ce) < 1e-6), None)
            # 有干净量测就用它（折角精确归零）；敢这么做是因为修正被关在边附近的核里，
            # 核内除这条边外没有别的可看特征。池化值只作回退与物理量报告。
            use = o["step"] if o is not None else tau * pooled[ce]
            src = "measured" if o is not None else "pooled(本缝无有效量测)"
            if abs(use) < a.dead_band:
                continue        # 不为看不见的量付插值锐度
            centers.append(o["col"] if o is not None else ce)
            amps.append(use)
            plats.append(float(np.clip(a.plateau_scale * widths[ei], 8.0, 120.0)))
            applied.append({"pair": s["pair"], "seam": seam,
                            "edge_col": round(centers[-1], 1),
                            "measured_step_px": None if o is None else o["step"],
                            "used_step_px": round(use, 3), "source": src,
                            "applied_relative_px": round(-use, 3),
                            "pooled_P_px": round(pooled[ce], 3),
                            "plateau_px": round(plats[-1], 1), "ramp_px": a.ramp})
        if centers:
            fields[below] = kernel_terms(col_axis, centers, amps, plats, a.ramp)

    # D[top] = 0 ; D[k] = D[k+1] - field(该缝下方为 k)
    disp: dict[int, np.ndarray] = {}
    cur = np.zeros(w, dtype=np.float32)
    for k in range(max(bounds), -1, -1):
        disp[k] = cur
        if k - 1 >= 0:
            cur = cur - fields.get(k - 1, np.zeros(w, dtype=np.float32))
    if a.integer:
        for k in disp:
            disp[k] = np.round(disp[k]).astype(np.float32)
    print("  各条带最大施加位移(px): " + "  ".join(
        f"{k}:{np.abs(disp[k]).max():.2f}" for k in sorted(disp)))

    fixed = apply_field(img, bounds, disp)

    # ---- 复核 ----
    print("  复核（同一批边，修正后重新量）")
    print(f"    {'缝':>6}{'边列':>10}{'before':>9}{'after':>9}")
    verify, before_all, after_all = [], [], []
    for s in seams:
        seam = int(s["row"])
        r = int(np.clip(seam - 200, 4, h - 5))
        pr = fixed[r - 3:r + 4].mean(axis=0).astype(np.float32)
        lo, hi = float(np.percentile(pr, 1)), float(np.percentile(pr, 99))
        for ce in edges:
            b0 = next((x for x in good if x["seam"] == seam
                       and abs(x["edge"] - ce) < 1e-6), None)
            if b0 is None:
                continue
            m = measure_step(fixed, seam, ce, lo, hi)
            aft = m[0] if m else float("nan")
            print(f"    {s['pair']:>6}{b0['col']:10.1f}{b0['step']:+9.3f}{aft:+9.3f}")
            verify.append({"pair": s["pair"], "seam": seam,
                           "edge_col": round(b0["col"], 1),
                           "before_px": b0["step"],
                           "after_px": None if m is None else round(aft, 3)})
            if m is not None:
                before_all.append(b0["step"])
                after_all.append(aft)
    summary: dict = {"edges": edges,
                     "edge_widths_10_90_px": [round(x, 2) for x in widths],
                     "pooled_P_px": {f"{k:.1f}": round(v, 3) for k, v in pooled.items()},
                     "measurements": obs, "applied": applied, "verify": verify,
                     "n_valid_measurements": len(good)}
    if before_all:
        b, f_ = np.array(before_all), np.array(after_all)
        summary["step_rms_before_px"] = round(float(np.sqrt((b ** 2).mean())), 3)
        summary["step_rms_after_px"] = round(float(np.sqrt((f_ ** 2).mean())), 3)
        summary["step_max_before_px"] = round(float(np.abs(b).max()), 3)
        summary["step_max_after_px"] = round(float(np.abs(f_).max()), 3)
        print(f"    |台阶| rms  {summary['step_rms_before_px']:.3f} -> "
              f"{summary['step_rms_after_px']:.3f} px   "
              f"max {summary['step_max_before_px']:.3f} -> "
              f"{summary['step_max_after_px']:.3f} px   (n={len(b)})")

    # ---- 代价与对照：纸内部必须逐字节不动 ----
    anydisp = np.zeros(w, dtype=bool)
    for k in disp:
        anydisp |= np.abs(disp[k]) > 0
    # 逐块比，别造出两个 558 MB 的 int16 临时数组
    changed = np.zeros(w, dtype=bool)
    for y0 in range(0, h, 512):
        changed |= (fixed[y0:y0 + 512] != img[y0:y0 + 512]).any(axis=0)
    outside = int((changed & ~anydisp).sum())
    summary["resampled_cols"] = int(anydisp.sum())
    summary["changed_cols"] = int(changed.sum())
    summary["changed_cols_outside_kernel"] = outside
    print(f"  代价与对照: 重采样列 {int(anydisp.sum())}/{w}"
          f" ({100.0 * anydisp.sum() / w:.1f}%)，实际变化 {int(changed.sum())} 列，"
          f"其中落在核外 = {outside}（应为 0）")
    if outside:
        print("  !! 有列在核外也变了，检查核的支撑范围")

    def sharp(src, m, rows_step=4):
        return float(np.abs(np.diff(src[::rows_step][:, m].astype(np.float32),
                                    axis=1)).mean())

    if anydisp.any() and (~changed).any():
        s_b, s_a = sharp(img, anydisp), sharp(fixed, anydisp)
        summary["sharpness_changed_pct"] = round(100 * (s_a / s_b - 1), 1)
        print(f"    锐度(平均 |dI/dcol|) 被修正列 {s_b:.3f} -> {s_a:.3f}"
              f"  ({100 * (s_a / s_b - 1):+.1f}%)；"
              f"未动列 {sharp(img, ~changed):.3f} -> {sharp(fixed, ~changed):.3f}（应不变）")
    return fixed, summary


# ══════════════════════════════════════════════ 入口

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--from-run", type=Path, default=None,
                   help="已有拼接结果目录；给了就跳过拼接，只做补偿")
    # ---- 拼接（透传给 stitch_stream_final.py）----
    p.add_argument("--data-dir", type=Path)
    p.add_argument("--true-yaml", type=Path)
    p.add_argument("--false-yaml", type=Path)
    p.add_argument("--stitcher", type=Path,
                   default=Path(__file__).resolve().parent / "stitch_stream_final.py")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--d-step-x", type=float, default=None)
    p.add_argument("--x-offset-false", type=float, default=None)
    p.add_argument("--seam-inset", type=int, default=None)
    p.add_argument("--x-feedback", action="store_true")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--stitcher-extra", default="",
                   help="原样追加到拼接器命令行的额外参数，如 \"--encoder-scale yaml-nominal\"")
    p.add_argument("--no-parallax", action="store_true", help="只拼接不补偿")
    p.add_argument("--no-keep-base", action="store_true", help="删掉未补偿的中间产物")
    # ---- 补偿 ----
    p.add_argument("--ramp", type=float, default=300.0,
                   help="核从平台衰减到 0 的距离(px)。越大越平滑，但受影响(重采样)的列越多")
    p.add_argument("--plateau-scale", type=float, default=2.0,
                   help="平台半宽 = 该边 10~90%% 宽度 × 此系数")
    p.add_argument("--dead-band", type=float, default=0.15,
                   help="|位移| 小于此值就不修：不为看不见的量付插值锐度")
    p.add_argument("--integer", action="store_true",
                   help="位移取整：完全不插值(零锐度损失)，但每条边会残留 <=0.5 px")
    p.add_argument("--max-resid", type=float, default=0.5,
                   help="两侧直线拟合残差上限(px)，超过判不可信")
    p.add_argument("--max-abs-step", type=float, default=4.0,
                   help="|台阶| 上限(px)，超过判为跟踪跳线")
    p.add_argument("--min-sep", type=int, default=200, help="边的最小间距(px)")
    p.add_argument("--min-hits", type=int, default=3, help="边至少在几条带里被找到")
    p.add_argument("--crops", type=int, default=3, help="输出几处最严重位置的放大图")
    # ---- 加速（透传给 fastcore / 拼接器）----
    p.add_argument("--fast", action="store_true",
                    help="拼接阶段用加速内核：可分离矫正建图（数值等价，3.6x）+ 分块并行")
    p.add_argument("--no-diag", action="store_true",
                    help="--fast 时再砍掉窗口里的纯诊断 FFT（dx/dy 一个数不变，"
                         "只是 CSV 少几个诊断值）。实测 1.8x")
    p.add_argument("--gpu", action="store_true",
                    help="--fast 时把 remap 放 GPU。注意实测 T4 上比 CPU 慢，默认别开")
    return p


def run_stitcher(a) -> Path:
    base = a.output_dir / "_base_stitch"
    base.mkdir(parents=True, exist_ok=True)
    if a.fast:                      # 只换矫正内核 + 可选去诊断 FFT，数值不变
        try:
            import fastcore
            fastcore.install(use_gpu=bool(a.gpu), no_diag=bool(a.no_diag))
        except Exception as exc:
            print(f"[warn] fastcore 装载失败，退回原路径: {exc}")
    if not a.stitcher.is_file():
        raise SystemExit(f"找不到拼接器 {a.stitcher}（用 --stitcher 指过去）")
    for key in ("data_dir", "true_yaml", "false_yaml"):
        if getattr(a, key) is None:
            raise SystemExit(f"缺少 --{key.replace('_', '-')}（或改用 --from-run 跳过拼接）")
    cmd = [sys.executable, str(a.stitcher),
           "--data-dir", str(a.data_dir),
           "--true-yaml", str(a.true_yaml),
           "--false-yaml", str(a.false_yaml),
           "--output-dir", str(base),
           "--start", str(a.start), "--workers", str(a.workers)]
    for flag, val in (("--end", a.end), ("--d-step-x", a.d_step_x),
                      ("--x-offset-false", a.x_offset_false),
                      ("--seam-inset", a.seam_inset), ("--json", a.json)):
        if val is not None:
            cmd += [flag, str(val)]
    if a.x_feedback:
        cmd.append("--x-feedback")
    if a.stitcher_extra.strip():
        cmd += a.stitcher_extra.strip().split()
    print("\n[1/2] 拼接\n  $ " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"拼接器退出码 {r.returncode}")
    return base


def main() -> int:
    a = build_parser().parse_args()
    a.output_dir = a.output_dir.resolve()
    a.output_dir.mkdir(parents=True, exist_ok=True)

    ran_stitcher = a.from_run is None
    run = run_stitcher(a) if ran_stitcher else a.from_run.resolve()
    tifs = sorted(run.glob("stitched_*_stream.tif"))
    if not tifs:
        raise SystemExit(f"{run} 里没有 stitched_*_stream.tif")
    src_tif = tifs[0]
    log_rows = list(csv.DictReader(open(run / "stream_frame_log.csv", encoding="utf-8-sig")))

    print(f"\n[2/2] 边缘视差补偿\n  输入 {src_tif}")
    img = np.asarray(Image.open(src_tif))
    print(f"  成图 {img.shape[0]} x {img.shape[1]}")

    if a.no_parallax:
        for f in run.iterdir():
            if f.is_file():
                shutil.copy2(f, a.output_dir / f.name)
        print(f"\n[--no-parallax] 只拼接不补偿 -> {a.output_dir}")
        return 0

    fixed, rep = compensate(img, run, log_rows, a)

    Image.fromarray(fixed).save(a.output_dir / src_tif.name,
                                compression="tiff_lzw", dpi=(300, 300))
    for f in run.iterdir():                    # 评估器要靠这些定位缝
        if f.is_file() and f.name != src_tif.name:
            shutil.copy2(f, a.output_dir / f.name)
    rep = {"source": str(src_tif),
           "params": {k: str(v) for k, v in vars(a).items()}, **rep}
    (a.output_dir / "edge_parallax_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["缝\t边列\t修正前(px)\t修正后(px)"]
    for v in rep["verify"]:
        lines.append(f"{v['pair']}\t{v['edge_col']}\t{v['before_px']:+.3f}\t"
                     f"{'' if v['after_px'] is None else format(v['after_px'], '+.3f')}")
    (a.output_dir / "edge_parallax_verify.txt").write_text("\n".join(lines), encoding="utf-8")

    for x in sorted(rep["applied"], key=lambda t: -abs(t["used_step_px"]))[:a.crops]:
        c, sm = int(round(x["edge_col"])), int(x["seam"])
        for tag, src in (("before", img), ("after", fixed)):
            crop = src[max(0, sm - 150):sm + 151, max(0, c - 200):c + 201]
            Image.fromarray(crop).save(a.output_dir / f"zoom_{c}_{sm}_{tag}.png")

    if ran_stitcher and a.no_keep_base:
        shutil.rmtree(run, ignore_errors=True)

    print(f"\n[out] {a.output_dir}")
    print(f"  {src_tif.name}                补偿后成图")
    print(f"  edge_parallax_report.json / edge_parallax_verify.txt")
    if ran_stitcher and not a.no_keep_base:
        print(f"  _base_stitch/                未补偿的中间产物（A/B 用）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
