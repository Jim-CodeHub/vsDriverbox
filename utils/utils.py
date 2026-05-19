# -*- coding: utf-8 -*- 

"""
    File        : utils.py
    Brief       :
    Author      : Jim
    Date        : 2026/5/16
    Copyright(c):
    Note        :
"""

import os, logging, threading, sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from ui.config.cfgcxt import config_context

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # For development, use the project root (one level up from utils/)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)

class Logger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(Logger, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir=None, max_total_mb=1024):
        if self._initialized:
            return

        self.log_dir = log_dir if log_dir else r"D:\vsDriverbox\log"
        self.max_total_bytes = max_total_mb * 1024 * 1024
        self.max_file_bytes = 10 * 1024 * 1024
        self.logger = logging.getLogger("vsDriverbox")
        self.logger.setLevel(logging.INFO)

        self._initialized = True

    def _setup_handler(self):
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception:
                return

        # New format: YYYYMMDD_HHMMSS.log (no 'app_' prefix, includes seconds)
        log_file = os.path.join(self.log_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

        handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_bytes,
            backupCount=100,
            encoding='utf-8'
        )

        formatter = logging.Formatter('[%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        self.logger.addHandler(handler)

    def check_and_clean_logs(self):
        """Check and clean logs, ensure total size doesn't exceed limit

        :param: None
        :return: None
        :raises: None
        :note:: Automatically removes oldest log files
        """
        try:
            if not os.path.exists(self.log_dir):
                return

            files = []
            total_size = 0
            for f in os.listdir(self.log_dir):
                if f.endswith(".log"):
                    path = os.path.join(self.log_dir, f)
                    f_info = os.stat(path)
                    files.append((path, f_info.st_mtime, f_info.st_size))
                    total_size += f_info.st_size

            files.sort(key=lambda x: x[1])

            while total_size > self.max_total_bytes and files:
                oldest_file, _, f_size = files.pop(0)
                try:
                    os.remove(oldest_file)
                    total_size -= f_size
                except Exception:
                    break
        except Exception:
            pass

    def sync_config(self, config_dict, force=False):
        """Update logger settings from configuration dictionary

        :param config_dict: Configuration dictionary
        :param force: Whether to force create a new log file even if config hasn't changed
        :return: None
        :raises: None
        :note:: If critical parameters change, will reconstruct Handler and perform a cleanup
        """
        log_dir = config_dict.get('log_dir', self.log_dir)
        max_mb = int(config_dict.get('log_limit', self.max_total_bytes // (1024 * 1024)))

        new_max_total_bytes = max_mb * 1024 * 1024

        # Always setup handler if it doesn't exist yet, or if config changed, or if forced
        if force or not self.logger.hasHandlers() or log_dir != self.log_dir or new_max_total_bytes != self.max_total_bytes:
            self.log_dir = log_dir
            self.max_total_bytes = new_max_total_bytes
            self._setup_handler()
            self.check_and_clean_logs()

    def info(self, msg):
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)

    def warn(self, msg):
        self.logger.warning(msg)


# Global instances
logger = Logger()
config = config_context.config
