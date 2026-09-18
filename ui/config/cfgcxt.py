# -*- coding: utf-8 -*- 

"""
    File        : cfgcxt.py
    Brief       : Global context for configuration and thread synchronization
    Author      : Jim
    Date        : 2026/5/16
    Copyright(c):
    Note        :
"""

import threading
import json
import os
import ctypes
import sys

class ConfigContext(object):
    def __init__(self):
        # Default configuration values to ensure consistency across environments
        self.config = {
            "listen_mode": "TCP/IP",
            "data_listen_addr": "127.0.0.1",
            "data_listen_port": "9111",
            "data_listen_dir": r"D:\vsDriverbox\hot",
            "hot_poll_interval": "100",
            "forward_mode": "TCP/IP",
            "forward_target_addr": "127.0.0.1",
            "forward_target_port": "9100",
            "forward_target_delay": "300",
            "forward_target_timeout": "5",
            "print_length": "100000",
            "print_width": "1800",
            "buffer_size": "10240",
            "log_dir": r"D:\vsDriverbox\log",
            "log_limit": "10240",
            "log_img_mode": False,
            "log_img_dir": r"D:\vsDriverbox\log\img",
            "cam_buffer_count": "10",
            "data_recv_addr": "127.0.0.1",
            "data_recv_port": "9120",
            "capture_img_len": "100",
            "capture_img_height": "2048",
            # 2026-09-12 起改用 20260903 那对（target_grid_shape = 30785 x 2240，
            # 现场机器实际使用的标定；旧的那对 4_registered/3_hflip_registered 是
            # 30781 x 2238，与现场报错里的 h=30785 对不上）。
            # 两份 yaml 已拷进 calib\，会被 vsDriverBox.spec 的 ('calib/*.yaml','calib') 打包。
            "calib_file": r"calib\4_final_calib.yaml",
            # Reverse-pass calibration. Empty = keep the legacy behaviour of
            # faking the reverse pass by flipping the raw scan axis.
            "calib_file_false": r"calib\5_final_calib.yaml",
            "capture_save_dir": r"D:\vsDriverbox\cap",
            "rip_send_dir": r"D:\vsDriverbox\rip",
            "cap_line_timeout": "5000",
            "cap_frame_timeout": "0",
            "board_comm_addr": "192.168.1.99",
            "board_comm_port": "502",
            "board_comm_timeout": "3000",
            "board_comm_retry": "3",
            "light_serial_port": "COM3",
            "light_baudrate": "19200",
            "light_comm_timeout": "1000",
            "light_brightness": "100",
            "light_use_enabled": True,
            "dpi": "300",
            "cal_sel": "new",
            "stitch_left_ref": "2461790",
            "stitch_right_ref": "29057700",
            "img_stitch_offset": "629",
            "canvas_start_pos": "7906",
            "canvas_end_pos": "21259",
            "overlap_offset_pix": "500",
            "stitch_timeout": "60",
            "language": "zh_CN",
            "export_calib_img": False,
            # Close the loop on the seam: measure every strip against the
            # previous one and correct the paste instead of trusting the
            # encoder alone. Off = legacy open-loop paste.
            "seam_refine": True,
            # ---- 流式拼接器（离线拼接用，见 drivers/camera/StreamStitch.py）----
            # 逐机常数：Step 编码器尺度 / 反向帧 x 原点偏移 / 缝内缩(px)。
            # 缺省值 = 2026-09-10 新机器 8 帧数据上验证过的那组；
            # 旧机器（20260627 批）用 847.965622809793 / 2.908141050525 / 256。
            "stream_d_step_x": "846.0527400801201",
            "stream_x_offset_false": "5.2406",
            "stream_seam_inset": "384",
            "stream_workers": "8",
            # 成图后做边缘视差补偿（stitch_stream_finalv2）；无强边时自动退回未补偿图
            "stream_parallax": True,
            # fastcore 加速内核（可分离建图，数值等价）+ 砍纯诊断 FFT；缺省开
            "stream_fast": True,
            "stream_no_diag": True,
            # 最终 warp 走 GPU（需现场装 torch+CUDA；像素与 CPU 可差 <=3/255，
            # 交付验证参考图是 CPU 产物，故缺省关）
            "stream_gpu_warp": False,
            # 实时打印转发路径也走流式拼接引擎（StreamRealtime）；
            # 带口径（宽度/相位/y_step）与旧路径一致，缝质量 C 级。
            # False = 回退旧引擎（SeamRefine 闭环）
            "stream_realtime": True
        }
        # Define synchronization events for business threads
        self.events = {
            'camera': threading.Event(),
            'board': threading.Event(),
            'light': threading.Event()
        }
        
        # Determine persistent config path
        # 1. Installation directory path (read-only default)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.install_config_path = os.path.join(base_dir, "src", ".syscfg")

        # 2. Preferred AppData path (Roaming) for user configuration (Standard Windows practice)
        appdata_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "VisionDriverBox")
        self.user_config_path = os.path.join(appdata_dir, ".syscfg")

        # 3. Fallback to D drive path for legacy compatibility if it exists
        self.legacy_config_path = r"D:\vsDriverbox\.syscfg"

    def load(self):
        """Load configuration from disk into memory
        Tries User AppData first, then legacy D drive, then falls back to installation directory.
        """
        # Try user config first, then legacy, then install path
        paths_to_try = [self.user_config_path, self.legacy_config_path, self.install_config_path]
        
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data:
                            self.config.update(data)
                            # If we successfully loaded from any path, we stop
                            return
                except Exception:
                    continue

    def save(self, new_data):
        """Save new configuration to disk and update memory cache
        Always saves to User AppData to avoid permission issues.
        Uses atomic write (temp file + rename) to prevent corruption.
        """
        self.config.update(new_data)
        temp_path = self.user_config_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.user_config_path), exist_ok=True)
            
            # Atomic write: dump to temp file first
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            # Move temp file to actual config path
            if os.path.exists(self.user_config_path):
                os.remove(self.user_config_path)
            os.rename(temp_path, self.user_config_path)
            
            # Set file as hidden on Windows
            if os.name == 'nt':
                FILE_ATTRIBUTE_HIDDEN = 0x02
                ctypes.windll.kernel32.SetFileAttributesW(self.user_config_path, FILE_ATTRIBUTE_HIDDEN)
            return True
        except Exception as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            return False

    def notify_all(self):
        """Set all events to notify business threads

        :param: None
        :return: None
        :raises: None
        :note:: Fan-out notification mechanism
        """
        for event in self.events.values():
            event.set()

config_context = ConfigContext()
