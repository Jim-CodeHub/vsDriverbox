# -*- coding: utf-8 -*-
"""StreamStitch.py — 把 delivery 的流式拼接器接进 vsDriverbox 的离线拼接。

被合入的三个脚本（与 testdata 里的验证副本逐字节一致，放在**项目根目录**）：
    stitch_stream_final.py     基础拼接（几何的唯一权威实现）
    stitch_stream_finalv2.py   基础拼接 + 边缘视差补偿（一步出成图）
    fastcore.py                加速内核（可分离建图，数值等价）

为什么放在项目根目录而不是 drivers/camera/
------------------------------------------
fastcore 通过**模块名** `import stitch_stream_final` 给拼接器打补丁，并且要在
多进程 worker（Windows spawn，各自重新 import）里重新打补丁。若作为包内模块
（drivers.camera.stitch_stream_final）导入，worker 里 `import stitch_stream_final`
会失败、补丁装不上（已实测）。放在根目录后模块名与 delivery 一致，父进程和
spawn 出的 worker 都能按原名导入同一个模块，脚本零修改即可工作。

设计要点
--------
- **进程内调用**：改写 sys.argv 后直接调 v1 / v2 的 main()，不再套子进程。
  打包成 exe 后 sys.executable 指向 exe 自身，"python 脚本.py" 式的子进程在
  现场会失效；进程内调用在源码 / exe 两种模式下行为一致。v1 自己的
  --workers N 并行管线在主进程里正常 spawn（main.py 已有 freeze_support()）。
- **加速默认开启**（delivery 同款）：fast=True 时先 fastcore.install()
  （可分离建图 + 砍纯诊断 FFT，数值等价，见该文件的对照说明），装不上就
  自动退回原路径并记日志。GPU warp 默认关：CPU warp 确定性更好、不需要
  torch（交付验证的参考图就是 CPU warp 产物；要开有 stream_gpu_warp 键）。
- **两步编排**：先 v1（基础拼接）出 `_base_stitch/`，再 v2 `--from-run` 做
  边缘视差补偿；补偿失败（例如整卷没有贯穿的强边）自动退回未补偿的基础图。
- **逐机常数**从配置读（键见 cfgcxt.py），缺省值是新机器的验证值；旧机器
  （20260627 批）用脚本内置缺省（d_step_x=847.9656 / x_offset_false=2.9081 /
  seam_inset=256），见 README 或 stream_summary.json。

用法（进程内）：
    from drivers.camera import StreamStitch
    result = StreamStitch.run_stream_stitch(
        data_dir=r"D:\vsDriverbox\cap\20260903180520",
        true_yaml=r"calib\4_final_calib.yaml",
        false_yaml=r"calib\5_final_calib.yaml",
        log_cb=logger.info)
    canvas = result["canvas"]      # np.ndarray，同旧 stitch_from_json 的返回
"""
from __future__ import annotations

import os
import shutil
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# 逐机常数的缺省值：新机器（2026-09-03 采集）实测
DEFAULT_D_STEP_X = 846.0527400801201
DEFAULT_X_OFFSET_FALSE = 5.2406
DEFAULT_SEAM_INSET = 384
DEFAULT_WORKERS = 8


def resolve_calib_path(path):
    """与 Camera.ImageStitch._resolve_calib_path 相同的相对路径解析。"""
    if not path or os.path.isabs(path) or os.path.exists(path):
        return path
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(base, path)
    return candidate if os.path.exists(candidate) else path


class _LineForwarder:
    """把 print() 输出按行转发给 log_cb，让拼接进度进应用日志。"""

    def __init__(self, log_cb):
        self._log_cb = log_cb
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip() and self._log_cb:
                self._log_cb(line)

    def flush(self):
        if self._buf.strip() and self._log_cb:
            self._log_cb(self._buf)
        self._buf = ""


def _call_cli_main(module, argv, log_cb=None):
    """进程内以 CLI 参数调用脚本的 main()（临时改写 sys.argv）。"""
    old_argv = sys.argv
    stdout = sys.stdout
    try:
        sys.argv = [module.__name__] + [str(a) for a in argv]
        if log_cb is not None:
            sys.stdout = _LineForwarder(log_cb)
        return module.main()
    finally:
        sys.argv = old_argv
        sys.stdout = stdout


def _install_fastcore(no_diag, log_cb=None):
    """装上 fastcore 加速内核（数值等价）；装不上自动退回原路径。"""
    try:
        import fastcore
        fastcore.install(use_gpu=False, no_diag=bool(no_diag))
        return True
    except Exception as exc:
        if log_cb:
            log_cb("StreamStitch: fastcore unavailable (%s); "
                   "falling back to the original path" % exc)
        return False


def run_stream_stitch(data_dir, true_yaml, false_yaml, output_dir=None, *,
                      start=0, end=None, workers=DEFAULT_WORKERS,
                      d_step_x=DEFAULT_D_STEP_X,
                      x_offset_false=DEFAULT_X_OFFSET_FALSE,
                      seam_inset=DEFAULT_SEAM_INSET,
                      x_feedback=True, parallax=True,
                      fast=True, no_diag=True, gpu_warp=False,
                      log_cb=None):
    """离线流式拼接一个采集目录，返回画布与产物路径。

    :param data_dir:    采集目录（.tif 帧 + LocalImageInfos.json）
    :param true_yaml:   Direction=True 标定（相对路径按安装目录解析）
    :param false_yaml:  Direction=False 标定（反转帧，先 hflip）
    :param output_dir:  产物目录；缺省 <data_dir>/stitch_stream
    :param start/end:   起止帧号；end=None 表示最后一帧
    :param workers:     并行进程数（0=串行）
    :param d_step_x:    Step 编码器尺度（逐机常数）
    :param x_offset_false: 反向帧的 x 原点偏移（逐机常数）
    :param seam_inset:  缝相对条带车道向尾边的位置(px)
    :param x_feedback: 车道向闭环
    :param parallax:    成图后做边缘视差补偿（无强边时自动退回未补偿图）
    :param fast:        fastcore 加速内核（可分离建图，数值等价）
    :param no_diag:     fast 模式下同时砍掉窗口纯诊断 FFT（dx/dy 不变）
    :param gpu_warp:    最终局部形变 warp 走 GPU（需 torch+CUDA；像素与
                        CPU warp 可差 <=3/255，交付验证参考图是 CPU 产物，
                        默认关）
    :param log_cb:      日志回调（接收拼接器的逐行输出）
    :return: dict(canvas=..., tif_path=..., compensated=..., output_dir=...)
    """
    import stitch_stream_final as v1
    import stitch_stream_finalv2 as v2

    data_dir = os.path.abspath(data_dir)
    true_yaml = resolve_calib_path(true_yaml)
    false_yaml = resolve_calib_path(false_yaml)
    for name, p in (("data_dir", data_dir), ("true_yaml", true_yaml),
                    ("false_yaml", false_yaml)):
        if not p or not os.path.exists(p):
            raise FileNotFoundError("stream stitch: %s not found: %r" % (name, p))

    if output_dir is None:
        output_dir = os.path.join(data_dir, "stitch_stream")
    output_dir = os.path.abspath(output_dir)
    if os.path.isdir(output_dir):          # 清掉上次运行的残留，
        shutil.rmtree(output_dir)          # 旧 tif/日志会让 --from-run 挑错文件
    base_dir = os.path.join(output_dir, "_base_stitch")
    os.makedirs(base_dir, exist_ok=True)

    if log_cb:
        log_cb("StreamStitch: data=%s true=%s false=%s" %
               (data_dir, os.path.basename(str(true_yaml)),
                os.path.basename(str(false_yaml))))

    # ---- 第 1 步：基础拼接（v1，几何唯一权威实现） ----
    if fast:
        _install_fastcore(no_diag, log_cb=log_cb)
    argv = ["--data-dir", data_dir,
            "--true-yaml", true_yaml,
            "--false-yaml", false_yaml,
            "--output-dir", base_dir,
            "--start", start,
            "--workers", workers,
            "--d-step-x", d_step_x,
            "--x-offset-false", x_offset_false,
            "--seam-inset", seam_inset,
            "--no-gpu-warp" if not gpu_warp else "--gpu-warp"]
    if end is not None:
        argv += ["--end", end]
    if x_feedback:
        argv.append("--x-feedback")
    try:
        _call_cli_main(v1, argv, log_cb=log_cb)
    except SystemExit as exc:
        # v1 用 SystemExit 报数据错误（帧数不足等）；它不是 Exception 子类，
        # 不转的话会穿透调用方的 except Exception，表现为线程静默死亡
        raise RuntimeError("stream stitch failed: %s" % exc) from exc

    base_tifs = sorted(f for f in os.listdir(base_dir)
                       if f.startswith("stitched_") and f.endswith("_stream.tif"))
    if not base_tifs:
        raise RuntimeError("stream stitch: no stitched_*.tif produced in %s" % base_dir)

    # ---- 第 2 步：边缘视差补偿（v2 --from-run；失败自动退回基础图） ----
    final_dir = base_dir
    compensated = False
    if parallax:
        try:
            _call_cli_main(v2, ["--from-run", base_dir, "--output-dir", output_dir],
                           log_cb=log_cb)
            final_dir = output_dir
            compensated = True
        except SystemExit as exc:
            if log_cb:
                log_cb("StreamStitch: parallax compensation unavailable "
                       "(%s); keeping the base stitch" % exc)
            _prune_failed_parallax(output_dir)
        except Exception as exc:
            if log_cb:
                log_cb("StreamStitch: parallax compensation failed (%s); "
                       "keeping the base stitch" % exc)
            _prune_failed_parallax(output_dir)

    tif_path = os.path.join(final_dir, base_tifs[0])
    canvas = np.array(Image.open(tif_path))
    if log_cb:
        log_cb("StreamStitch: done %s, canvas %s, compensated=%s" %
               (tif_path, canvas.shape, compensated))
    return dict(canvas=canvas, tif_path=tif_path, compensated=compensated,
                output_dir=output_dir)


def _prune_failed_parallax(output_dir):
    """补偿半途写过 output_dir 的话清掉，保证返回的是干净的基础图。"""
    for f in os.listdir(output_dir):
        if f != "_base_stitch":
            p = os.path.join(output_dir, f)
            if os.path.isfile(p):
                os.remove(p)
