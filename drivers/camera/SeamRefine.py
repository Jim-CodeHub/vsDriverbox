# -*- coding: utf-8 -*-
r"""Closed-loop seam refinement for Camera.ImageStitch.

Why this exists
---------------
`ImageStitch` places every strip from the encoder reading alone. The residual
that leaves at each seam was measured on 35 frames at median 0.24-2.49 px
depending on the calibration, and it cannot be removed by a constant: the term
that dominates it is proportional to the strip advance, and the hand-tuned
`x_invert` only absorbs the direction-antisymmetric part (and only for the
calibration it was tuned against - swap the calibration and it is wrong again).

The fix measures instead of assuming. Two things are added:

1. Every strip is matched against its predecessor in the band the two provably
   share, and the offset is fed back into which column the strip is cut at.
   That band already exists inside the rectified strip - `_stitch_unit` simply
   discards it - so nothing extra has to be rectified.
2. What the integer cut cannot express (the sub-pixel remainder) plus the way
   the offset varies from one end of the seam to the other is applied as a
   single smooth column warp, one `cv2.remap` per strip.

Measured on frames 0-34 with the registered pair (`residual_correction: none`):
median |dx| 2.489 -> 0.191 px, rms 2.689 -> 0.259, windows over 1 px
89.0% -> 0.0%, median along-seam spread 0.746 -> 0.464.

Nothing here is a machine constant. `skew_s` and `antisym` start at zero and are
re-fitted after every trusted pair, so a different machine needs no new number.

Deliberate choice: the placement is measured with phase correlation, while the
offline evaluator scores with NCC plus a slant self-calibration. Keeping the two
different is what stops an A/B from simply optimising its own score function.
"""

import statistics

import cv2
import numpy as np

# --- measurement -----------------------------------------------------------
WINDOWS = 7                     # column bands along the seam
CROP_MARGIN = 32                # px trimmed off each end of a band
MIN_TRUSTED_WINDOWS = 3
MIN_RESPONSE = 0.12
MAX_ABS_PHASE = 20.0
MAX_TRUSTED_CORRECTION_PX = 8.0  # beyond this the measurement is not believed

# --- model -----------------------------------------------------------------
FIT_MIN_PAIRS = 4
MAX_MODEL_PREDICTION_PX = 8.0    # sanity bound on the fitted model's output

# --- warp ------------------------------------------------------------------
MAX_LOCAL_CORRECTION_PX = 4.0    # clamp on the per-window DEVIATION only
WARP_CHUNK_ROWS = 256


def _normalize_feature(patch):
    """Gradient magnitude, mean-removed and unit-variance.

    Phase correlation on raw grey levels locks onto the illumination profile
    rather than the fabric; on the gradient magnitude it locks onto the weave.
    """
    if patch is None or patch.size == 0:
        return None
    patch32 = patch.astype(np.float32)
    gx = cv2.Sobel(patch32, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(patch32, cv2.CV_32F, 0, 1, ksize=3)
    feature = cv2.magnitude(gx, gy)
    feature -= float(np.mean(feature))
    std = float(np.std(feature))
    if std < 1e-3:
        return None
    return feature / std


def _phase_one(a, b):
    fa = _normalize_feature(a)
    fb = _normalize_feature(b)
    if fa is None or fb is None:
        return float("nan"), float("nan"), float("nan")
    (dx, dy), response = cv2.phaseCorrelate(fa, fb)
    return float(dx), float(dy), float(response)


def _trusted(dx, dy, response):
    if np.isnan(response):
        return False
    return (response >= MIN_RESPONSE
            and abs(dx) <= MAX_ABS_PHASE
            and abs(dy) <= MAX_ABS_PHASE)


def smooth_window_values(values):
    """Three-point moving average, endpoints held.

    Keeps the warp field from having a step between adjacent windows, which
    would show up as a visible kink along the seam.
    """
    out = []
    for i, value in enumerate(values):
        neighbours = [value]
        if i > 0:
            neighbours.append(values[i - 1])
        if i + 1 < len(values):
            neighbours.append(values[i + 1])
        out.append(float(sum(neighbours) / len(neighbours)))
    return out


def apply_column_warp(image, knots, cut_lo, cut_hi):
    """Shift content along the column axis by a smooth field.

    `knots` are the displacements at `len(knots)` evenly spaced positions across
    [cut_lo, cut_hi); positive values move content to the RIGHT. Outside that
    span the end values are held, which only affects columns that get cut away.

    Applied BEFORE the canvas cut so the columns pulled in at the edges are real
    content rather than replicated border. Done in row chunks to keep the
    coordinate maps small.
    """
    if not any(knots):
        return image
    height, width = image.shape[:2]
    smoothed = smooth_window_values(list(knots))
    knots_x = np.linspace(float(cut_lo), float(cut_hi - 1),
                          num=len(smoothed), dtype=np.float64)
    xs = np.arange(width, dtype=np.float64)
    delta = np.interp(xs, knots_x, np.asarray(smoothed, dtype=np.float64))
    src_x = (xs - delta).astype(np.float32)

    out = np.empty_like(image)
    for r0 in range(0, height, WARP_CHUNK_ROWS):
        r1 = min(height, r0 + WARP_CHUNK_ROWS)
        block = image[r0:r1]
        rows = r1 - r0
        map_x = np.broadcast_to(src_x[None, :], (rows, width)).copy()
        map_y = np.broadcast_to(
            np.arange(rows, dtype=np.float32)[:, None], (rows, width)).copy()
        out[r0:r1] = cv2.remap(block, map_x, map_y, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
    return out


class SeamRefine(object):
    r"""Per-roll state for the closed loop. One instance per ImageStitch.

    Usage from `stitch_from_ram`, in order:

        pred  = refiner.predict(forward, direction)      # integer column shift
        probe = <cut the strip at pred, take the probe band>
        dx    = refiner.measure(probe)                   # against the last fresh
        final, knots = refiner.resolve(pred, dx)
        fresh = <cut the strip at final, warped by knots>
        refiner.commit(fresh)

    `reset()` must be called whenever `step_Reset()` is, i.e. at the start of a
    roll: `prev_fresh` from the previous roll is not the same fabric.
    """

    def __init__(self, subpixel=True, local_warp=True, online_fit=True):
        self.subpixel = bool(subpixel)
        self.local_warp = bool(local_warp)
        self.online_fit = bool(online_fit)
        self.reset()

    def reset(self):
        self.skew_s = 0.0
        self.antisym = 0.0
        self.fit_source = "cold start (s=0, A=0)"
        self.fit_observations = []
        self.refine = 0.0            # carries the fractional remainder
        self.prev_fresh = None
        self.window_field = [0.0] * WINDOWS
        self.last = {}               # diagnostics for the most recent strip

    # -- 1. predict ---------------------------------------------------------
    def predict(self, forward, direction):
        """Integer column shift to cut at before the pair is measured."""
        sigma = 1.0 if direction else -1.0
        model = self.skew_s * float(forward) + self.antisym * sigma
        self._sigma = sigma
        self._model = model if self.prev_fresh is not None else 0.0
        self._forward = float(forward)
        self._target = self.refine + self._model
        return int(round(self._target))

    # -- 2. measure ---------------------------------------------------------
    def measure(self, probe):
        """Median along-seam offset against the previous strip's fresh band.

        `dx` follows phaseCorrelate's convention: probe content sits at
        (ref column + dx), so adding round(dx) to the cut offset moves probe
        content onto ref. Returns None when the pair is not trustworthy.
        """
        ref = self.prev_fresh
        self._per_window = {}
        if ref is None or probe is None or ref.shape != probe.shape:
            self._reject = "no comparable predecessor"
            return None
        rows, cols = ref.shape[:2]
        r0, r1 = CROP_MARGIN, rows - CROP_MARGIN
        if r1 - r0 < 64:
            self._reject = "shared band too short"
            return None
        n_windows = 0
        for w in range(WINDOWS):
            c0 = int(round(cols * w / WINDOWS)) + CROP_MARGIN
            c1 = int(round(cols * (w + 1) / WINDOWS)) - CROP_MARGIN
            if c1 - c0 < 128:
                continue
            n_windows += 1
            dx, dy, response = _phase_one(ref[r0:r1, c0:c1], probe[r0:r1, c0:c1])
            if _trusted(dx, dy, response):
                self._per_window[w] = float(dx)
        if len(self._per_window) < MIN_TRUSTED_WINDOWS:
            self._reject = "only %d/%d windows passed" % (
                len(self._per_window), n_windows)
            self._per_window = {}
            return None
        dx = float(statistics.median(self._per_window.values()))
        if abs(dx) > MAX_TRUSTED_CORRECTION_PX:
            self._reject = "|dx| %+.2fpx exceeds %.1fpx" % (
                dx, MAX_TRUSTED_CORRECTION_PX)
            self._per_window = {}
            return None
        self._reject = ""
        return dx

    # -- 3. resolve ---------------------------------------------------------
    def resolve(self, extra_pred, dx):
        """Final integer column shift plus the warp field to apply with it.

        The field is solved directly, never chained, because the measurement was
        taken against the neighbour AS PASTED - its own offset and warp are
        already baked into `prev_fresh`. For window w:

            required left-shift = extra_pred + dx_w
            actual  left-shift  = extra_final - F[w]
            =>  F[w] = extra_final - extra_pred - dx_w

        Split into the rigid sub-pixel remainder (bounded by +-1 px by
        construction, and NOT clamped - it is a placement, not a correction) and
        the local scatter, which is clamped.
        """
        applied = 0.0 if dx is None else float(dx)
        if dx is not None:
            self._observe_and_refit(self._model + applied)

        target = self._target + applied
        extra_final = int(round(target))
        # ABSOLUTE cumulative placement, NOT a per-strip delta - do not "fix"
        # this by subtracting extra_final. `_stitch_unit` adds extra_col_shift to
        # a FIXED cut window (cut_lo = x_s_cut + shift), so the value handed to
        # it has to be the total offset of this strip from the nominal window.
        # Keeping only the fractional remainder would throw away every earlier
        # correction and reintroduce the full drift (~2.7 px per strip on the
        # measured machine). Empirically: shift climbs 0 -> +93 over 34 strips
        # while the median seam error stays at 0.19 px.
        self.refine = target


        f_const = (float(extra_final - extra_pred) - applied) if self.subpixel else 0.0
        limit = MAX_LOCAL_CORRECTION_PX
        if self.local_warp and self._per_window:
            deviations = [
                max(-limit, min(limit, -(self._per_window[w] - applied)))
                if w in self._per_window else 0.0
                for w in range(WINDOWS)
            ]
        else:
            deviations = [0.0] * WINDOWS
        self.window_field = [f_const + d for d in deviations]

        self.last = {
            "sigma": self._sigma,
            "model_px": self._model,
            "extra_pred_px": int(extra_pred),
            "extra_final_px": int(extra_final),
            "dx_measured_px": dx,
            "dx_source": "model" if dx is None else "measured",
            "reject_reason": self._reject,
            "applied_px": applied,
            "refine_px": self.refine,
            "warp_const_px": f_const,
            "max_abs_deviation_px": max([abs(d) for d in deviations] or [0.0]),
            "n_deviations_at_clamp": sum(1 for d in deviations
                                         if abs(d) >= limit - 1e-9),
            "skew_s_used": self.skew_s,
            "antisym_used": self.antisym,
            "fit_pairs": len(self.fit_observations),
            "fit_source": self.fit_source,
        }
        knots = self.window_field if (self.subpixel or self.local_warp) else None
        return extra_final, knots

    # -- 4. commit ---------------------------------------------------------
    def commit(self, fresh):
        """Remember what was actually pasted; the next strip measures against it."""
        self.prev_fresh = fresh

    # -- online fit --------------------------------------------------------
    def _observe_and_refit(self, model_free):
        """Refit `dy = s*forward + A*sigma` after every trusted pair.

        `model_free` is what the pair would have measured with no model applied,
        i.e. prediction + measured residual. Nothing already pasted is revised -
        a better model only makes the NEXT strips land closer.
        """
        self.fit_observations.append((self._forward, self._sigma, float(model_free)))
        if not self.online_fit or len(self.fit_observations) < FIT_MIN_PAIRS:
            return
        fwd = np.array([o[0] for o in self.fit_observations], dtype=np.float64)
        sig = np.array([o[1] for o in self.fit_observations], dtype=np.float64)
        target = np.array([o[2] for o in self.fit_observations], dtype=np.float64)
        if len(set(sig.tolist())) < 2:
            self.fit_source = "cold start (only one transition seen)"
            return
        solution, _residuals, _rank, _sv = np.linalg.lstsq(
            np.column_stack([fwd, sig]), target, rcond=None)
        s_fit, a_fit = float(solution[0]), float(solution[1])
        worst = abs(s_fit * float(np.median(fwd))) + abs(a_fit)
        if not np.isfinite(worst) or worst > MAX_MODEL_PREDICTION_PX:
            self.fit_source = "rejected (|prediction| %.2fpx out of range)" % worst
            return
        self.skew_s, self.antisym = s_fit, a_fit
        self.fit_source = "fitted"
