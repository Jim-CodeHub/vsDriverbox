# -*- coding: utf-8 -*-
"""env_smoke_stitch.py — 用打包环境跑一遍离线拼接，检查库版本漂移（非硬件路径）。

用法: python _diag/env_smoke_stitch.py [数据集名 20260627|20260903] [workers]
"""
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import numpy as np
import cv2
import scipy


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "20260903"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4

    print(f"numpy={np.__version__} cv2={cv2.__version__} scipy={scipy.__version__}")

    data_dir = os.path.join(_ROOT, "testdata", ds, "stitch")
    calib_dir = os.path.join(_ROOT, "testdata", ds, "calib")

    if ds == "20260627":
        true_yaml = os.path.join(calib_dir, "4_final_calib.yaml")
        false_yaml = os.path.join(calib_dir, "3_final_calib.yaml")
        d_step_x, x_offset_false, seam_inset = 847.965622809793, 2.908141050525, 256
    else:
        true_yaml = os.path.join(calib_dir, "4_final_calib.yaml")
        false_yaml = os.path.join(calib_dir, "5_final_calib.yaml")
        d_step_x, x_offset_false, seam_inset = 846.0527400801201, 5.2406, 384

    assert os.path.isdir(data_dir), data_dir
    assert os.path.isfile(true_yaml), true_yaml
    assert os.path.isfile(false_yaml), false_yaml

    import drivers.camera.StreamStitch as SS

    # output_dir 用一个全新不重名的目录：run_stream_stitch 开头会对已存在的
    # output_dir 调 shutil.rmtree()，本环境里 rmtree 被沙箱 shim 接管会失败。
    stamp = time.strftime("%H%M%S")
    out_dir = os.path.join(_ROOT, "_diag", f"_smoke_{ds}_{stamp}")

    os.makedirs(os.path.join(_ROOT, "_diag", "_smoke_logs"), exist_ok=True)
    # 注意：StreamStitch 会把 sys.stdout 重定向到 log_cb，
    # 所以 log_cb 里绝对不能再 print，否则无限递归。写文件。
    log_path = os.path.join(_ROOT, "_diag", "_smoke_logs", f"{ds}_{stamp}.log")
    log_fp = open(log_path, "w", encoding="utf-8")

    def _log(m):
        log_fp.write(str(m) + "\n")
        log_fp.flush()

    t0 = time.time()
    result = SS.run_stream_stitch(
        data_dir=data_dir,
        true_yaml=true_yaml,
        false_yaml=false_yaml,
        output_dir=out_dir,
        workers=workers,
        d_step_x=d_step_x,
        x_offset_false=x_offset_false,
        seam_inset=seam_inset,
        parallax=True,
        fast=True,
        no_diag=True,
        gpu_warp=False,
        log_cb=_log,
    )
    log_fp.close()
    canvas = result["canvas"]
    print(f"[OK] {ds}: canvas={canvas.shape} dtype={canvas.dtype} "
          f"cost={time.time()-t0:.1f}s")
    print(f"     tif   = {result.get('tif_path')}")
    print(f"     log   = {log_path}")


if __name__ == "__main__":
    main()
