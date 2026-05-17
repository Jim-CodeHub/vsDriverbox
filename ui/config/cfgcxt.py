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

class ConfigContext(object):
    def __init__(self):
        self.config = {}
        # Define synchronization events for business threads
        self.events = {
            'camera': threading.Event(),
            'board': threading.Event(),
            'light': threading.Event()
        }
        # Hidden config file path: ../../src/.sys_cfg
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", ".syscfg")

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
