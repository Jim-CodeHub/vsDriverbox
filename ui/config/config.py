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
import json
from .cfgcxt import config_context

class ConfigUI(object):
    # Magic header for config file validation
    CFG_MAGIC = "VDB_CFG_V1"
    def __init__(self, root=None):
        if root is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(root)
            
        self.root.title("参数设置")
        self.root.geometry("1100x850")
        self.root.resizable(True, True)
        
        self.entries = {}
        self.buttons = {}
        
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
        # Use pack for the bottom buttons and a canvas with scrollbar for the middle content
        # or just pack the buttons at the bottom first to ensure visibility.
        
        # 1. Bottom Buttons Container (Pack first at bottom)
        btn_container = ttk.Frame(self.root, padding="10")
        btn_container.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Action Buttons (Right-aligned)
        ttk.Button(btn_container, text="取消", command=self.root.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_container, text="确定", command=self.save_config).pack(side=tk.RIGHT, padx=5)
        
        ttk.Frame(btn_container, width=60).pack(side=tk.RIGHT)
        
        ttk.Button(btn_container, text="加载配置", command=self.import_config).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_container, text="存储配置", command=self.export_config).pack(side=tk.RIGHT, padx=5)

        # 2. Main content container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
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
        
        self._add_dropdown(print_frame, "数据监听方式:", ["TCP/IP", "热文件夹"], 0, key="listen_mode", callback=self._on_listen_mode_change)
        self._add_entry(print_frame, "数据监听地址:", "127.0.0.1", 1, key="data_listen_addr")
        self._add_entry(print_frame, "数据监听端口:", "9111", 2, key="data_listen_port", vcmd=self.v_int)
        self._add_browse_entry(print_frame, "数据监听目录:", 3, show_status=False, key="data_listen_dir")
        self._add_entry(print_frame, "数据轮询时间:", "100", 4, unit="ms", key="hot_poll_interval", vcmd=self.v_int)

        self._add_dropdown(print_frame, "转发目标方式:", ["TCP/IP", "HS DLL"], 5, key="forward_mode", callback=self._on_forward_mode_change)
        
        self._add_entry(print_frame, "转发目标地址:", "127.0.0.1", 6, key="forward_target_addr")
        self._add_entry(print_frame, "转发目标端口:", "9100", 7, key="forward_target_port", vcmd=self.v_int)
        self._add_entry(print_frame, "转发目标延迟:", "500", 8, unit="ms", key="forward_target_delay", vcmd=self.v_int)
        self._add_entry(print_frame, "转发目标超时:", "5", 9, unit="s", key="forward_target_timeout", vcmd=self.v_int)
        self._add_entry(print_frame, "打印长度设置:", "100000", 10, unit="mm", key="print_length", vcmd=self.v_int)
        self._add_entry(print_frame, "打印宽度设置:", "1800", 11, unit="mm", key="print_width", vcmd=self.v_int)
        self._add_entry(print_frame, "缓冲字节设置:", "10240", 12, unit="KB", key="buffer_size", vcmd=self.v_int)
        
        # 2. Log Configuration
        log_frame = ttk.LabelFrame(col0, text="日志配置", padding="5")
        log_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_browse_entry(log_frame, "日志存储目录:", 0, default_val=r"D:\vsDriverbox\log", key="log_dir")
        self._add_entry(log_frame, "日志存储上限:", "10240", 1, unit="MB", key="log_limit", vcmd=self.v_int)
        self._add_checkbox(log_frame, "日志存图模式:", 2, key="log_img_mode", callback=self._on_log_img_mode_change)
        self._add_browse_entry(log_frame, "日志存图目录:", 3, default_val=r"D:\vsDriverbox\log\img", key="log_img_dir")
        
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
        self._add_entry(cam_settings_frame, "采集图像高度:", "2048", 4, unit="pix", key="capture_img_height", vcmd=self.v_int)
        self._add_browse_entry(cam_settings_frame, "标定文件选择:", 5, is_file=True, default_val=r"D:\vsDriverbox\calib.yaml", key="calib_file", filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        self._add_browse_entry(cam_settings_frame, "采集存储目录:", 6, default_val=r"D:\vsDriverbox\cap", key="capture_save_dir")
        self._add_browse_entry(cam_settings_frame, "白图发送目录:", 7, default_val=r"D:\vsDriverbox\rip", show_status=False, key="rip_send_dir")
        self._add_entry(cam_settings_frame, "采集行间超时:", "5000", 8, unit="ms", key="cap_line_timeout", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, "采集帧间超时:", "0", 9, unit="ms", key="cap_frame_timeout", vcmd=self.v_int)
        
        # 3.2 Stitching Settings
        stitch_frame = ttk.LabelFrame(col1, text="拼接设置", padding="5")
        stitch_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(stitch_frame, "拼接左侧基准:", "2461790", 0, key="stitch_left_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, "拼接右侧基准:", "29057700", 1, key="stitch_right_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, "图像拼接偏移:", "629", 2, unit="pix", key="img_stitch_offset", vcmd=self.v_int)
        self._add_entry(stitch_frame, "画布开始位置:", "7906", 3, key="canvas_start_pos", vcmd=self.v_int)
        self._add_entry(stitch_frame, "画布结束位置:", "21259", 4, key="canvas_end_pos", vcmd=self.v_int)
        self.entries["canvas_end_pos"].config(state="readonly")
        
        self._add_entry(stitch_frame, "重叠偏移像素:", "500", 5, key="overlap_offset_pix", vcmd=self.v_int)
        self._add_entry(stitch_frame, "DPI:", "300", 6, key="dpi", vcmd=self.v_int)
        self._add_dropdown(stitch_frame, "校准程序选择:", ["旧版", "新版"], 7, key="cal_sel", callback=self._on_cal_sel_change)
        self._add_entry(stitch_frame, "图像拼接超时:", "60", 8, unit="s", key="stitch_timeout", vcmd=self.v_int)
        
        # Add trace-like behavior for real-time update
        self.entries["print_width"].bind("<KeyRelease>", lambda e: self._update_canvas_end_pos())
        self.entries["dpi"].bind("<KeyRelease>", lambda e: self._update_canvas_end_pos())
        
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
        
        # Load initial data
        self.load_ui_data()

    def _add_checkbox(self, parent, label_text, row, key=None, callback=None):
        """Helper to add checkbox to a grid"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        var = tk.BooleanVar()
        check = ttk.Checkbutton(parent, variable=var, command=callback if callback else None)
        check.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        
        if key:
            self.entries[key] = var # Store the variable instead of widget for easy get/set
            
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

    def _add_dropdown(self, parent, label_text, options, row, key=None, callback=None):
        """Helper to add label + combobox to a grid"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        combo = ttk.Combobox(parent, values=options, width=23, state="readonly")
        combo.current(0)
        combo.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        
        if key:
            self.entries[key] = combo
            
        if callback:
            combo.bind("<<ComboboxSelected>>", callback)

    def _on_forward_mode_change(self, event):
        """Handle forward mode change to enable/disable address/port entries"""
        mode = self.entries["forward_mode"].get()
        if mode == "HS DLL":
            self.entries["forward_target_addr"].config(state="disabled")
            self.entries["forward_target_port"].config(state="disabled")
        else:
            self.entries["forward_target_addr"].config(state="normal")
            self.entries["forward_target_port"].config(state="normal")

    def _on_listen_mode_change(self, event):
        """Handle listen mode change to enable/disable address/port or directory entries"""
        mode = self.entries["listen_mode"].get()
        if mode == "热文件夹":
            self.entries["data_listen_addr"].config(state="disabled")
            self.entries["data_listen_port"].config(state="disabled")
            self.entries["data_listen_dir"].config(state="normal")
            self.entries["hot_poll_interval"].config(state="normal")
        else:
            self.entries["data_listen_addr"].config(state="normal")
            self.entries["data_listen_port"].config(state="normal")
            self.entries["data_listen_dir"].config(state="disabled")
            self.entries["hot_poll_interval"].config(state="disabled")

    def _on_cal_sel_change(self, event):
        """Handle calibration selection change to warn user"""
        messagebox.showwarning("注意", "校准程序已切换，需同步变更标定文件！")

    def _on_log_img_mode_change(self):
        """Handle log image mode change to enable/disable directory entry"""
        enabled = self.entries["log_img_mode"].get()
        state = "normal" if enabled else "disabled"
        self.entries["log_img_dir"].config(state=state)
        if "log_img_dir" in self.buttons:
            self.buttons["log_img_dir"].config(state=state)

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

        btn = ttk.Button(parent, text="浏览", width=5, command=browse)
        btn.grid(row=row, column=2, sticky=tk.W)
        
        if key:
            self.buttons[key] = btn
        
        if show_status:
            status_label = ttk.Label(parent, text="未选择", font=("Microsoft YaHei", 7), foreground="gray")
            status_label.grid(row=row+1, column=1, columnspan=2, sticky=tk.W, padx=3)

    def _update_canvas_end_pos(self):
        """Update canvas_end_pos based on print_width and dpi: width * dpi / 25.4"""
        try:
            width_str = self.entries["print_width"].get()
            dpi_str = self.entries["dpi"].get()
            
            if not width_str or not dpi_str:
                return
                
            width = float(width_str)
            dpi = float(dpi_str)
            
            # Formula: print_width / 25.4 * dpi (rounded to integer)
            # User mentioned "打印宽度x25.4/300", which matches pixel calculation if 300 is DPI
            # and they meant "divide by (25.4/DPI)" or "multiply by (DPI/25.4)"
            end_pos = int(width * dpi / 25.4)
            
            # Update the readonly entry
            self.entries["canvas_end_pos"].config(state="normal")
            self.entries["canvas_end_pos"].delete(0, tk.END)
            self.entries["canvas_end_pos"].insert(0, str(end_pos))
            self.entries["canvas_end_pos"].config(state="readonly")
        except (ValueError, ZeroDivisionError):
            pass

    def save_config(self):
        """Collect UI data and save to configuration file

        :param: None
        :return: None
        :raises: None
        :note:: Triggers global event notification after successful save
        """
        config_data = {}
        for key, entry in self.entries.items():
            if isinstance(entry, tk.BooleanVar):
                config_data[key] = entry.get()
            else:
                config_data[key] = entry.get()
            
        if config_context.save(config_data):
            config_context.notify_all()
            messagebox.showinfo("提示", "保存成功")
            self.root.destroy()
        else:
            messagebox.showerror("错误", "保存失败")

    def export_config(self):
        """Export current UI configuration to a .cfg file with magic header"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".cfg",
            filetypes=[("Config files", "*.cfg"), ("All files", "*.*")],
            title="存储配置"
        )
        if not file_path:
            return

        try:
            config_data = {key: entry.get() for key, entry in self.entries.items()}
            export_obj = {
                "header": self.CFG_MAGIC,
                "data": config_data
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_obj, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("成功", f"配置已成功存储至：\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"存储配置失败：\n{str(e)}")

    def import_config(self):
        """Import configuration from a .cfg file and validate magic header"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Config files", "*.cfg"), ("All files", "*.*")],
            title="加载配置"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_obj = json.load(f)

            # Validate header
            if not isinstance(import_obj, dict) or import_obj.get("header") != self.CFG_MAGIC:
                messagebox.showerror("错误", "无效的配置文件：特征头不匹配或格式错误。")
                return

            config_data = import_obj.get("data", {})
            for key, value in config_data.items():
                if key in self.entries:
                    self.entries[key].delete(0, tk.END)
                    self.entries[key].insert(0, str(value))
            
            messagebox.showinfo("成功", "配置加载成功，请点击“确定”以应用更改。")
            self._update_canvas_end_pos()
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败：\n{str(e)}")

    def load_ui_data(self):
        """Populate UI entries from global configuration context

        :param: None
        :return: None
        :raises: None
        :note:: Called only during window initialization
        """
        for key, value in config_context.config.items():
            if key in self.entries:
                if isinstance(self.entries[key], ttk.Combobox):
                    self.entries[key].set(value)
                    # Trigger callback manually for dropdowns to update state
                    if key == "forward_mode":
                        self._on_forward_mode_change(None)
                    elif key == "listen_mode":
                        self._on_listen_mode_change(None)
                elif isinstance(self.entries[key], tk.BooleanVar):
                    self.entries[key].set(value)
                    if key == "log_img_mode":
                        self._on_log_img_mode_change()
                else:
                    self.entries[key].delete(0, tk.END)
                    self.entries[key].insert(0, value)
        
        self._update_canvas_end_pos()

    def show(self):
        """Display configuration window

        :param: None
        :return: None
        :raises: None
        :note:: Starts mainloop if root is a main window
        """
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()
