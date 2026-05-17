# -*- coding: utf-8 -*-

"""
    File        : config.py
    Brief       : Parameter Settings UI for Vision Driver Box based on 111111111111111.png
    Author      : Jim
    Date        : 2026/5/16
    Copyright(c):
    Note        :
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from .cfgcxt import config_context

class ConfigUI:
    def __init__(self, root=None):
        if root is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(root)
            
        self.root.title("参数设置")
        self.root.geometry("1100x580")
        self.root.resizable(True, True)
        
        self.entries = {}
        
        # Validation commands
        self.v_int = (self.root.register(self._validate_int), '%P')
        self.v_float = (self.root.register(self._validate_float), '%P')
        
        # Style configuration
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("Microsoft YaHei", 9))
        self.style.configure("TButton", font=("Microsoft YaHei", 9))
        self.style.configure("TLabelframe.Label", font=("Microsoft YaHei", 10, "bold"))
        
        self._create_widgets()
        self.load_ui_data()
        
    def _create_widgets(self):
        # Main container with three uniform columns
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Configure uniform columns
        for i in range(3):
            main_container.columnconfigure(i, weight=1, uniform="group1")
        main_container.rowconfigure(0, weight=1)
            
        # --- Column 0: Print & Log ---
        col0 = ttk.Frame(main_container)
        col0.grid(row=0, column=0, sticky=tk.NSEW, padx=5)
        col0.columnconfigure(0, weight=1)
        col0.rowconfigure(0, weight=1, uniform="row_group")
        col0.rowconfigure(1, weight=1, uniform="row_group")
        
        # 1. Print Settings
        print_frame = ttk.LabelFrame(col0, text="打印设置", padding="5")
        print_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(print_frame, "数据监听地址:", "127.0.0.1", 0, key="data_listen_addr")
        self._add_entry(print_frame, "数据监听端口:", "9111", 1, key="data_listen_port", vcmd=self.v_int)
        self._add_entry(print_frame, "转发目标地址:", "127.0.0.1", 2, key="forward_target_addr")
        self._add_entry(print_frame, "转发目标端口:", "9100", 3, key="forward_target_port", vcmd=self.v_int)
        self._add_entry(print_frame, "打印长度设置:", "100000", 4, unit="mm", key="print_length", vcmd=self.v_int)
        self._add_entry(print_frame, "打印宽度设置:", "1800", 5, unit="mm", key="print_width", vcmd=self.v_int)
        self._add_entry(print_frame, "缓冲字节设置:", "10240", 6, unit="KB", key="buffer_size", vcmd=self.v_int)
        
        # 2. Log Configuration
        log_frame = ttk.LabelFrame(col0, text="日志配置", padding="5")
        log_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_browse_entry(log_frame, "日志存储目录:", 0, default_val=r"D:\vsDriverbox\log", key="log_dir")
        self._add_entry(log_frame, "日志存储上限:", "10240", 1, unit="MB", key="log_limit", vcmd=self.v_int)
        
        # --- Column 1: Camera & Stitching ---
        col1 = ttk.Frame(main_container)
        col1.grid(row=0, column=1, sticky=tk.NSEW, padx=5)
        col1.columnconfigure(0, weight=1)
        col1.rowconfigure(0, weight=1, uniform="row_group")
        col1.rowconfigure(1, weight=1, uniform="row_group")
        
        # 3.1 Camera Settings
        cam_settings_frame = ttk.LabelFrame(col1, text="相机设置", padding="5")
        cam_settings_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(cam_settings_frame, "相机缓冲区数:", "10", 0, key="cam_buffer_count", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, "数据接收地址:", "127.0.0.1", 1, key="data_recv_addr")
        self._add_entry(cam_settings_frame, "数据接收端口:", "9120", 2, key="data_recv_port", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, "采集图像长度:", "100", 3, unit="cm", key="capture_img_len", vcmd=self.v_float)
        self._add_browse_entry(cam_settings_frame, "标定文件选择:", 4, is_file=True, default_val=r"D:\vsDriverbox\calib.yaml", key="calib_file", filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        self._add_browse_entry(cam_settings_frame, "采集存储目录:", 5, default_val=r"D:\vsDriverbox\cap", key="capture_save_dir")
        self._add_browse_entry(cam_settings_frame, "白图发送目录:", 6, default_val=r"D:\vsDriverbox\rip", show_status=False, key="rip_send_dir")
        
        # 3.2 Stitching Settings
        stitch_frame = ttk.LabelFrame(col1, text="拼接设置", padding="5")
        stitch_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(stitch_frame, "拼接左侧基准:", "2461790", 0, key="stitch_left_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, "拼接右侧基准:", "29057700", 1, key="stitch_right_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, "图像拼接偏移:", "629", 2, unit="pix", key="img_stitch_offset", vcmd=self.v_int)
        self._add_entry(stitch_frame, "画布开始位置:", "7906", 3, key="canvas_start_pos", vcmd=self.v_int)
        self._add_entry(stitch_frame, "画布结束位置:", "21259", 4, key="canvas_end_pos", vcmd=self.v_int)
        self._add_entry(stitch_frame, "重叠偏移像素:", "500", 5, key="overlap_offset_pix", vcmd=self.v_int)
        self._add_entry(stitch_frame, "DPI:", "300", 6, key="dpi", vcmd=self.v_int)
        
        # --- Column 2: Board & Light ---
        col2 = ttk.Frame(main_container)
        col2.grid(row=0, column=2, sticky=tk.NSEW, padx=5)
        col2.columnconfigure(0, weight=1)
        col2.rowconfigure(0, weight=1, uniform="row_group")
        col2.rowconfigure(1, weight=1, uniform="row_group")
        
        # 3.3 Board Settings
        board_frame = ttk.LabelFrame(col2, text="板卡设置", padding="5")
        board_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(board_frame, "通讯地址设置:", "192.168.1.99", 0, key="board_comm_addr")
        self._add_entry(board_frame, "通讯端口设置:", "502", 1, key="board_comm_port", vcmd=self.v_int)
        self._add_entry(board_frame, "通讯超时设置:", "3000", 2, unit="ms", key="board_comm_timeout", vcmd=self.v_int)
        self._add_entry(board_frame, "通讯重试次数:", "3", 3, unit="次", key="board_comm_retry", vcmd=self.v_int)
        
        # 3.4 Light Settings
        light_frame = ttk.LabelFrame(col2, text="灯光设置", padding="5")
        light_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(light_frame, "串口端口设置:", "COM3", 0, key="light_serial_port")
        self._add_entry(light_frame, "波特率设置:", "19200", 1, key="light_baudrate", vcmd=self.v_int)
        self._add_entry(light_frame, "通讯超时设置:", "1000", 2, unit="ms", key="light_comm_timeout", vcmd=self.v_int)
        self._add_entry(light_frame, "灯光亮度设置:", "100", 3, key="light_brightness", vcmd=self.v_int)
        
        # --- Bottom Buttons ---
        btn_container = ttk.Frame(self.root, padding="10")
        btn_container.pack(fill=tk.X)
        
        ttk.Button(btn_container, text="确定", command=self.save_config).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_container, text="取消", command=self.root.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Load initial data
        self.load_ui_data()

    def _add_entry(self, parent, label_text, default_val, row, unit="", key=None, vcmd=None):
        """Helper to add label + entry + unit to a grid"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        entry_kwargs = {"width": 25}
        if vcmd:
            entry_kwargs["validate"] = "key"
            entry_kwargs["validatecommand"] = vcmd
            
        entry = ttk.Entry(parent, **entry_kwargs)
        entry.insert(0, default_val)
        entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        
        if key:
            self.entries[key] = entry
            
        if unit:
            ttk.Label(parent, text=unit).grid(row=row, column=2, sticky=tk.W)

    def _validate_int(self, P):
        """Validate integer input (allow empty or digits)"""
        if P == "" or P.isdigit():
            return True
        return False

    def _validate_float(self, P):
        """Validate float input (allow empty, digits, or single dot)"""
        if P == "":
            return True
        try:
            if P.count('.') <= 1 and all(c.isdigit() or c == '.' for c in P):
                if P == ".": return True # allow leading dot
                float(P)
                return True
        except ValueError:
            pass
        return False

    def _add_browse_entry(self, parent, label_text, row, is_file=False, default_val="", show_status=True, key=None, filetypes=None):
        """Helper to add label + entry + browse button"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        entry = ttk.Entry(parent, width=25)
        entry.insert(0, default_val)
        entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        
        if key:
            self.entries[key] = entry

        def browse():
            if is_file:
                path = filedialog.askopenfilename(filetypes=filetypes if filetypes else [("All files", "*.*")])
            else:
                path = filedialog.askdirectory()
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        ttk.Button(parent, text="浏览", width=5, command=browse).grid(row=row, column=2, sticky=tk.W)
        
        if show_status:
            status_label = ttk.Label(parent, text="未选择", font=("Microsoft YaHei", 7), foreground="gray")
            status_label.grid(row=row+1, column=1, columnspan=2, sticky=tk.W, padx=3)

    def save_config(self):
        """Collect UI data and save to configuration file

        :param: None
        :return: None
        :raises: None
        :note:: Triggers global event notification after successful save
        """
        config_data = {}
        for key, entry in self.entries.items():
            config_data[key] = entry.get()
            
        if config_context.save(config_data):
            config_context.notify_all()
            messagebox.showinfo("提示", "保存成功")
            self.root.destroy()
        else:
            messagebox.showerror("错误", "保存失败")

    def load_ui_data(self):
        """Populate UI entries from global configuration context

        :param: None
        :return: None
        :raises: None
        :note:: Called only during window initialization
        """
        for key, value in config_context.config.items():
            if key in self.entries:
                self.entries[key].delete(0, tk.END)
                self.entries[key].insert(0, value)

    def show(self):
        """Display configuration window

        :param: None
        :return: None
        :raises: None
        :note:: Starts mainloop if root is a main window
        """
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()
