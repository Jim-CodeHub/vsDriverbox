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
            "data_listen_addr": "127.0.0.1",
            "data_listen_port": "9111",
            "forward_target_addr": "127.0.0.1",
            "forward_target_port": "9100",
            "print_length": "100000",
            "print_width": "1800",
            "buffer_size": "10240",
            "log_dir": r"D:\vsDriverbox\log",
            "log_limit": "10240",
            "cam_buffer_count": "10",
            "data_recv_addr": "127.0.0.1",
            "data_recv_port": "9120",
            "capture_img_len": "100",
            "calib_file": r"D:\vsDriverbox\calib.yaml",
            "capture_save_dir": r"D:\vsDriverbox\cap",
            "rip_send_dir": r"D:\vsDriverbox\rip",
            "board_comm_addr": "192.168.1.99",
            "board_comm_port": "502",
            "board_comm_timeout": "3000",
            "board_comm_retry": "3",
            "light_serial_port": "COM3",
            "light_baudrate": "19200",
            "light_comm_timeout": "1000",
            "dpi": "300",
            "stitch_left_ref": "2461790",
            "stitch_right_ref": "29057700",
            "img_stitch_offset": "629",
            "canvas_start_pos": "7906",
            "canvas_end_pos": "21259",
            "overlap_offset_pix": "500"
        }
        # Define synchronization events for business threads
        self.events = {
            'camera': threading.Event(),
            'board': threading.Event(),
            'light': threading.Event()
        }
        
        # Determine persistent config path
        if getattr(sys, 'frozen', False):
            # If bundled, store in the same directory as the executable
            base_dir = os.path.dirname(sys.executable)
        else:
            # If running as script, use the project structure
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            
        self.config_path = os.path.join(base_dir, "src", ".syscfg")

    def load(self):
        """Load configuration from disk into memory

        :param: None
        :return: None
        :raises: None
        :note:: Uses default configuration if loading fails
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config.clear()
                    self.config.update(data)
            except Exception:
                # Silently fail, using default values elsewhere
                pass

    def save(self, new_data):
        """Save new configuration to disk and update memory cache

        :param new_data: New configuration dictionary
        :return: True for success, False for failure
        :raises: None
        :note:: Sets configuration file as hidden on Windows
        """
        self.config.clear()
        self.config.update(new_data)
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            # Set file as hidden on Windows
            if os.name == 'nt':
                FILE_ATTRIBUTE_HIDDEN = 0x02
                ctypes.windll.kernel32.SetFileAttributesW(self.config_path, FILE_ATTRIBUTE_HIDDEN)
            return True
        except Exception as e:
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
