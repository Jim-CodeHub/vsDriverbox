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
import sys
import serial.tools.list_ports
from .cfgcxt import config_context

# 添加父目录到路径，以便导入灯光类
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from drivers.camera.Camera import Camera
from utils.i18n import translator

class ConfigUI(object):
    # Magic header for config file validation
    CFG_MAGIC = "VDB_CFG_V1"
    def __init__(self, root=None):
        if root is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(root)
        
        self.layout = self._get_layout_config()
        self.root.title(translator.t('config_ui.title'))
        self.root.geometry(f"{self.layout['window_width']}x850")
        self.root.minsize(self.layout["window_min_width"], 850)
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

    def _get_layout_config(self):
        """Return language-aware layout settings for the configuration window."""
        language = translator.get_language()
        layouts = {
            "zh_CN": {
                "window_width": 1100,
                "window_min_width": 1060,
                "group_minsize": 335,
                "label_col_width": 120,
                "field_col_minsize": 165,
                "aux_col_width": 60,
                "entry_width": 25,
                "combo_width": 23,
                "serial_combo_width": 22,
                "small_button_width": 5,
                "action_button_width": 10,
                "button_gap_width": 60,
            },
            "en_US": {
                "window_width": 1420,
                "window_min_width": 1360,
                "group_minsize": 445,
                "label_col_width": 190,
                "field_col_minsize": 185,
                "aux_col_width": 88,
                "entry_width": 30,
                "combo_width": 28,
                "serial_combo_width": 27,
                "small_button_width": 8,
                "action_button_width": 14,
                "button_gap_width": 36,
            },
            "vi_VN": {
                "window_width": 1540,
                "window_min_width": 1480,
                "group_minsize": 485,
                "label_col_width": 220,
                "field_col_minsize": 190,
                "aux_col_width": 100,
                "entry_width": 31,
                "combo_width": 29,
                "serial_combo_width": 28,
                "small_button_width": 10,
                "action_button_width": 16,
                "button_gap_width": 24,
            },
        }
        return layouts.get(language, layouts["zh_CN"])

    def _configure_form_grid(self, parent):
        """Apply shared column sizing so long translated labels still fit."""
        if getattr(parent, "_vdb_form_grid_configured", False):
            return

        parent.columnconfigure(0, minsize=self.layout["label_col_width"])
        parent.columnconfigure(1, weight=1, minsize=self.layout["field_col_minsize"])
        parent.columnconfigure(2, minsize=self.layout["aux_col_width"])
        parent._vdb_form_grid_configured = True
        
    def _create_widgets(self):
        # Main container with three uniform columns
        # Use pack for the bottom buttons and a canvas with scrollbar for the middle content
        # or just pack the buttons at the bottom first to ensure visibility.
        
        # 1. Bottom Buttons Container (Pack first at bottom)
        btn_container = ttk.Frame(self.root, padding="10")
        btn_container.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Action Buttons (Right-aligned)
        ttk.Button(
            btn_container,
            text=translator.t('config_ui.cancel'),
            command=self.root.destroy,
            width=self.layout["action_button_width"]
        ).pack(side=tk.RIGHT, padx=5)
        ttk.Button(
            btn_container,
            text=translator.t('config_ui.ok'),
            command=self.save_config,
            width=self.layout["action_button_width"]
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Frame(btn_container, width=self.layout["button_gap_width"]).pack(side=tk.RIGHT)
        
        ttk.Button(
            btn_container,
            text=translator.t('config_ui.load_config'),
            command=self.import_config,
            width=self.layout["action_button_width"]
        ).pack(side=tk.RIGHT, padx=5)
        ttk.Button(
            btn_container,
            text=translator.t('config_ui.save_config'),
            command=self.export_config,
            width=self.layout["action_button_width"]
        ).pack(side=tk.RIGHT, padx=5)

        # 2. Main content container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Configure uniform columns
        for i in range(3):
            main_container.columnconfigure(
                i,
                weight=1,
                uniform="group1",
                minsize=self.layout["group_minsize"]
            )
        main_container.rowconfigure(0, weight=1)
            
        # --- Column 0: Print & Log ---
        col0 = ttk.Frame(main_container)
        col0.grid(row=0, column=0, sticky=tk.NSEW, padx=5)
        col0.columnconfigure(0, weight=1)
        col0.rowconfigure(0, weight=1, uniform="row_group")
        col0.rowconfigure(1, weight=1, uniform="row_group")
        
        # 1. Print Settings
        print_frame = ttk.LabelFrame(col0, text=translator.t('config_ui.print_settings'), padding="5")
        print_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_dropdown(print_frame, translator.t('config_ui.listen_mode') + ":", [translator.t('options.tcp_ip'), translator.t('config_ui.hot_folder')], 0, key="listen_mode", callback=self._on_listen_mode_change)
        self._add_entry(print_frame, translator.t('config_ui.listen_addr') + ":", "127.0.0.1", 1, key="data_listen_addr")
        self._add_entry(print_frame, translator.t('config_ui.listen_port') + ":", "9111", 2, key="data_listen_port", vcmd=self.v_int)
        self._add_browse_entry(print_frame, translator.t('config_ui.listen_dir') + ":", 3, show_status=False, key="data_listen_dir")
        self._add_entry(print_frame, translator.t('config_ui.poll_interval') + ":", "100", 4, unit=translator.t('config_ui.unit.ms'), key="hot_poll_interval", vcmd=self.v_int)

        self._add_dropdown(print_frame, translator.t('config_ui.forward_mode') + ":", [translator.t('options.tcp_ip'), translator.t('options.hs_dll')], 5, key="forward_mode", callback=self._on_forward_mode_change)
        
        self._add_entry(print_frame, translator.t('config_ui.forward_addr') + ":", "127.0.0.1", 6, key="forward_target_addr")
        self._add_entry(print_frame, translator.t('config_ui.forward_port') + ":", "9100", 7, key="forward_target_port", vcmd=self.v_int)
        self._add_entry(print_frame, translator.t('config_ui.forward_delay') + ":", "500", 8, unit=translator.t('config_ui.unit.ms'), key="forward_target_delay", vcmd=self.v_int)
        self._add_entry(print_frame, translator.t('config_ui.forward_timeout') + ":", "5", 9, unit=translator.t('config_ui.unit.s'), key="forward_target_timeout", vcmd=self.v_int)
        self._add_entry(print_frame, translator.t('config_ui.print_length') + ":", "100000", 10, unit=translator.t('config_ui.unit.mm'), key="print_length", vcmd=self.v_int)
        self._add_entry(print_frame, translator.t('config_ui.print_width') + ":", "1800", 11, unit=translator.t('config_ui.unit.mm'), key="print_width", vcmd=self.v_int)
        self._add_entry(print_frame, translator.t('config_ui.buffer_size') + ":", "10240", 12, unit=translator.t('config_ui.unit.KB'), key="buffer_size", vcmd=self.v_int)
        
        # 2. Log Configuration
        log_frame = ttk.LabelFrame(col0, text=translator.t('config_ui.log_config'), padding="5")
        log_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_browse_entry(log_frame, translator.t('config_ui.log_dir') + ":", 0, default_val=r"D:\vsDriverbox\log", key="log_dir")
        self._add_entry(log_frame, translator.t('config_ui.log_limit') + ":", "10240", 1, unit=translator.t('config_ui.unit.MB'), key="log_limit", vcmd=self.v_int)
        self._add_checkbox(log_frame, translator.t('config_ui.log_img_mode') + ":", 2, key="log_img_mode", callback=self._on_log_img_mode_change)
        self._add_browse_entry(log_frame, translator.t('config_ui.log_img_dir') + ":", 3, default_val=r"D:\vsDriverbox\log\img", key="log_img_dir")
        
        # --- Column 1: Camera & Stitching ---
        col1 = ttk.Frame(main_container)
        col1.grid(row=0, column=1, sticky=tk.NSEW, padx=5)
        col1.columnconfigure(0, weight=1)
        col1.rowconfigure(0, weight=1, uniform="row_group")
        col1.rowconfigure(1, weight=1, uniform="row_group")
        
        # 3.1 Camera Settings
        cam_settings_frame = ttk.LabelFrame(col1, text=translator.t('config_ui.camera_settings'), padding="5")
        cam_settings_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(cam_settings_frame, translator.t('config_ui.cam_buffer_count') + ":", "10", 0, key="cam_buffer_count", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, translator.t('config_ui.data_recv_addr') + ":", "127.0.0.1", 1, key="data_recv_addr")
        self._add_entry(cam_settings_frame, translator.t('config_ui.data_recv_port') + ":", "9120", 2, key="data_recv_port", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, translator.t('config_ui.capture_img_len') + ":", "100", 3, unit=translator.t('config_ui.unit.cm'), key="capture_img_len", vcmd=self.v_float)
        self._add_entry(cam_settings_frame, translator.t('config_ui.capture_img_height') + ":", "2048", 4, unit=translator.t('config_ui.unit.pix'), key="capture_img_height", vcmd=self.v_int)
        self._add_browse_entry(cam_settings_frame, translator.t('config_ui.calib_file') + ":", 5, is_file=True, default_val=r"D:\vsDriverbox\calib.yaml", key="calib_file", filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        self._add_browse_entry(cam_settings_frame, translator.t('config_ui.capture_save_dir') + ":", 6, default_val=r"D:\vsDriverbox\cap", key="capture_save_dir")
        self._add_browse_entry(cam_settings_frame, translator.t('config_ui.rip_send_dir') + ":", 7, default_val=r"D:\vsDriverbox\rip", show_status=False, key="rip_send_dir")
        self._add_entry(cam_settings_frame, translator.t('config_ui.cap_line_timeout') + ":", "5000", 8, unit=translator.t('config_ui.unit.ms'), key="cap_line_timeout", vcmd=self.v_int)
        self._add_entry(cam_settings_frame, translator.t('config_ui.cap_frame_timeout') + ":", "0", 9, unit=translator.t('config_ui.unit.ms'), key="cap_frame_timeout", vcmd=self.v_int)
        
        # 3.2 Stitching Settings
        stitch_frame = ttk.LabelFrame(col1, text=translator.t('config_ui.stitch_settings'), padding="5")
        stitch_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(stitch_frame, translator.t('config_ui.stitch_left_ref') + ":", "2461790", 0, key="stitch_left_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, translator.t('config_ui.stitch_right_ref') + ":", "29057700", 1, key="stitch_right_ref", vcmd=self.v_int)
        self._add_entry(stitch_frame, translator.t('config_ui.img_stitch_offset') + ":", "629", 2, unit=translator.t('config_ui.unit.pix'), key="img_stitch_offset", vcmd=self.v_int)
        self._add_entry(stitch_frame, translator.t('config_ui.canvas_start_pos') + ":", "7906", 3, key="canvas_start_pos", vcmd=self.v_int)
        self._add_entry(stitch_frame, translator.t('config_ui.canvas_end_pos') + ":", "21259", 4, key="canvas_end_pos", vcmd=self.v_int)
        self.entries["canvas_end_pos"].config(state="readonly")
        
        self._add_entry(stitch_frame, translator.t('config_ui.overlap_offset_pix') + ":", "500", 5, key="overlap_offset_pix", vcmd=self.v_int)
        self._add_entry(stitch_frame, translator.t('config_ui.dpi') + ":", "300", 6, key="dpi", vcmd=self.v_int)
        self._add_dropdown(stitch_frame, translator.t('config_ui.cal_sel') + ":", [translator.t('options.old_version'), translator.t('options.new_version')], 7, key="cal_sel", callback=self._on_cal_sel_change)
        self._add_entry(stitch_frame, translator.t('config_ui.stitch_timeout') + ":", "60", 8, unit=translator.t('config_ui.unit.s'), key="stitch_timeout", vcmd=self.v_int)
        self._add_checkbox(stitch_frame, translator.t('config_ui.export_calib_img') + ":", 9, key="export_calib_img")
        
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
        board_frame = ttk.LabelFrame(col2, text=translator.t('config_ui.board_settings'), padding="5")
        board_frame.grid(row=0, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_entry(board_frame, translator.t('config_ui.board_comm_addr') + ":", "192.168.1.99", 0, key="board_comm_addr")
        self._add_entry(board_frame, translator.t('config_ui.board_comm_port') + ":", "502", 1, key="board_comm_port", vcmd=self.v_int)
        self._add_entry(board_frame, translator.t('config_ui.board_comm_timeout') + ":", "3000", 2, unit=translator.t('config_ui.unit.ms'), key="board_comm_timeout", vcmd=self.v_int)
        self._add_entry(board_frame, translator.t('config_ui.board_comm_retry') + ":", "3", 3, unit=translator.t('config_ui.unit.次'), key="board_comm_retry", vcmd=self.v_int)
        
        # 3.4 Light Settings
        light_frame = ttk.LabelFrame(col2, text=translator.t('config_ui.light_settings'), padding="5")
        light_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=2)
        
        self._add_checkbox(light_frame, translator.t('config_ui.light_use_enabled') + ":", 0, key="light_use_enabled", callback=self._on_light_use_enabled_change)
        self._add_serial_port_entry(light_frame, translator.t('config_ui.light_serial_port') + ":", 1, default_val="COM3", key="light_serial_port")
        self._add_entry(light_frame, translator.t('config_ui.light_baudrate') + ":", "19200", 2, key="light_baudrate", vcmd=self.v_int)
        self._add_entry(light_frame, translator.t('config_ui.light_comm_timeout') + ":", "1000", 3, unit=translator.t('config_ui.unit.ms'), key="light_comm_timeout", vcmd=self.v_int)
        
        # 灯光亮度设置 + 测试按钮
        ttk.Label(light_frame, text=translator.t('config_ui.light_brightness') + ":").grid(row=4, column=0, sticky=tk.W, pady=2)
        
        self._configure_form_grid(light_frame)
        brightness_entry = ttk.Entry(
            light_frame,
            width=self.layout["entry_width"],
            validate="key",
            validatecommand=self.v_int
        )
        brightness_entry.insert(0, "100")
        brightness_entry.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)
        self.entries["light_brightness"] = brightness_entry
        
        # 保存控件引用
        if not hasattr(self, 'light_widgets'):
            self.light_widgets = {}
        self.light_widgets["light_brightness"] = brightness_entry
        
        # 测试按钮状态变量
        self.test_button_state = tk.BooleanVar(value=False)
        # 创建测试按钮 - 与刷新按钮样式保持一致
        self.test_button = tk.Button(
            light_frame,
            text=translator.t('config_ui.test'),
            width=self.layout["small_button_width"],
            command=self._toggle_test_button
        )
        self.test_button.grid(row=4, column=2, sticky=tk.W)
        self.light_widgets["test_button"] = self.test_button
        # 设置初始背景色
        self._update_test_button_color()
        
        # Load initial data
        self.load_ui_data()
    
    def _update_ui_texts(self):
        """更新所有UI文本以支持语言切换（用于未来扩展）"""
        pass

    def _add_checkbox(self, parent, label_text, row, key=None, callback=None):
        """Helper to add checkbox to a grid"""
        self._configure_form_grid(parent)
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        var = tk.BooleanVar()
        check = ttk.Checkbutton(parent, variable=var, command=callback if callback else None)
        check.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
        
        if key:
            self.entries[key] = var # Store the variable instead of widget for easy get/set
            
    def _add_entry(self, parent, label_text, default_val, row, unit="", key=None, vcmd=None):
        """Helper to add label + entry + unit to a grid"""
        self._configure_form_grid(parent)
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        entry_kwargs = {"width": self.layout["entry_width"]}
        if vcmd:
            entry_kwargs["validate"] = "key"
            entry_kwargs["validatecommand"] = vcmd
            
        entry = ttk.Entry(parent, **entry_kwargs)
        entry.insert(0, default_val)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
        
        if key:
            self.entries[key] = entry
            # 保存控件引用到专门的灯光控件字典
            if key.startswith("light_"):
                if not hasattr(self, 'light_widgets'):
                    self.light_widgets = {}
                self.light_widgets[key] = entry
            
        if unit:
            ttk.Label(parent, text=unit).grid(row=row, column=2, sticky=tk.W)

    def _add_dropdown(self, parent, label_text, options, row, key=None, callback=None):
        """Helper to add label + combobox to a grid"""
        self._configure_form_grid(parent)
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        combo = ttk.Combobox(parent, values=options, width=self.layout["combo_width"], state="readonly")
        combo.current(0)
        combo.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
        
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
        messagebox.showwarning(translator.t('config_ui.warning'), translator.t('config_ui.cal_switch_warning'))

    def _on_log_img_mode_change(self):
        """Handle log image mode change to enable/disable directory entry"""
        enabled = self.entries["log_img_mode"].get()
        state = "normal" if enabled else "disabled"
        self.entries["log_img_dir"].config(state=state)
        if "log_img_dir" in self.buttons:
            self.buttons["log_img_dir"].config(state=state)
    
    def _on_light_use_enabled_change(self):
        """Handle light use enabled change to enable/disable all light settings"""
        if not hasattr(self, 'entries') or "light_use_enabled" not in self.entries:
            return
        
        enabled = self.entries["light_use_enabled"].get()
        state = "normal" if enabled else "disabled"
        
        # 如果没有保存灯光控件引用，直接返回
        if not hasattr(self, 'light_widgets'):
            return
        
        # 遍历所有灯光控件并设置状态
        for key, widget in self.light_widgets.items():
            try:
                widget.config(state=state)
            except:
                pass

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

    def _add_serial_port_entry(self, parent, label_text, row, default_val="COM3", key=None):
        """Helper to add label + serial port combobox + refresh button"""
        self._configure_form_grid(parent)
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        combo = ttk.Combobox(parent, width=self.layout["serial_combo_width"], state="readonly")
        combo.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
        
        if key:
            self.entries[key] = combo
        
        def refresh_serial_ports():
            """Refresh and populate the serial port dropdown"""
            ports = serial.tools.list_ports.comports()
            port_list = [port.device for port in ports]
            combo['values'] = port_list
            
            current_value = combo.get()
            if current_value in port_list:
                combo.set(current_value)
            elif port_list:
                combo.set(port_list[0])
            else:
                combo.set(default_val)
        
        refresh_serial_ports()
        combo.set(default_val)
        
        btn = ttk.Button(
            parent,
            text=translator.t('config_ui.refresh'),
            width=self.layout["small_button_width"],
            command=refresh_serial_ports
        )
        btn.grid(row=row, column=2, sticky=tk.W)
        
        if key:
            self.buttons[key] = btn
            # 保存控件引用到专门的灯光控件字典
            if key.startswith("light_"):
                if not hasattr(self, 'light_widgets'):
                    self.light_widgets = {}
                self.light_widgets[key] = combo
                self.light_widgets[key + '_btn'] = btn

    def _add_browse_entry(self, parent, label_text, row, is_file=False, default_val="", show_status=True, key=None, filetypes=None):
        """Helper to add label + entry + browse button"""
        self._configure_form_grid(parent)
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        entry = ttk.Entry(parent, width=self.layout["entry_width"])
        entry.insert(0, default_val)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
        
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

        btn = ttk.Button(
            parent,
            text=translator.t('config_ui.browse'),
            width=self.layout["small_button_width"],
            command=browse
        )
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
            messagebox.showinfo(translator.t('config_ui.save_success'), translator.t('config_ui.save_success'))
            self.root.destroy()
        else:
            messagebox.showerror(translator.t('config_ui.save_failed'), translator.t('config_ui.save_failed'))

    def export_config(self):
        """Export current UI configuration to a .cfg file with magic header"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".cfg",
            filetypes=[("Config files", "*.cfg"), ("All files", "*.*")],
            title=translator.t('config_ui.save_config')
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
            messagebox.showinfo(translator.t('config_ui.save_success'), f"{translator.t('config_ui.export_success')}：\n{file_path}")
        except Exception as e:
            messagebox.showerror(translator.t('config_ui.export_failed'), f"{translator.t('config_ui.export_failed')}：\n{str(e)}")

    def import_config(self):
        """Import configuration from a .cfg file and validate magic header"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Config files", "*.cfg"), ("All files", "*.*")],
            title=translator.t('config_ui.load_config')
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_obj = json.load(f)

            # Validate header
            if not isinstance(import_obj, dict) or import_obj.get("header") != self.CFG_MAGIC:
                messagebox.showerror(translator.t('config_ui.import_failed'), translator.t('config_ui.invalid_config'))
                return

            config_data = import_obj.get("data", {})
            for key, value in config_data.items():
                if key in self.entries:
                    if isinstance(self.entries[key], tk.BooleanVar):
                        # Handle boolean values for checkboxes
                        self.entries[key].set(value)
                    else:
                        self.entries[key].delete(0, tk.END)
                        self.entries[key].insert(0, str(value))
            
            messagebox.showinfo(translator.t('config_ui.save_success'), translator.t('config_ui.import_success'))
            self._update_canvas_end_pos()
        except Exception as e:
            messagebox.showerror(translator.t('config_ui.import_failed'), f"{translator.t('config_ui.import_failed')}：\n{str(e)}")

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
        # 初始化灯光设置状态
        self._on_light_use_enabled_change()

    def show(self):
        """Display configuration window

        :param: None
        :return: None
        :raises: None
        :note:: Starts mainloop if root is a main window
        """
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()
    
    def _update_test_button_color(self):
        """更新测试按钮的背景颜色"""
        if self.test_button_state.get():
            # 按下状态（on）- 绿色背景
            self.test_button.config(bg="#4CAF50", fg="white")
        else:
            # 抬起状态（off）- 灰色背景
            self.test_button.config(bg="#f0f0f0", fg="black")
    
    def _toggle_test_button(self):
        """切换测试按钮状态并控制灯光"""
        try:
            # 获取当前配置
            port = self.entries["light_serial_port"].get()
            baud = int(self.entries["light_baudrate"].get())
            tout = int(self.entries["light_comm_timeout"].get()) / 1000.0
            brightness = int(self.entries["light_brightness"].get())
            
            # 创建灯光实例
            light = Camera.Illuminant(port=port, baud=baud, tout=tout)
            
            # 设置参数
            light.set_port(port)
            light.set_baud(baud)
            light.set_tout(tout)
            
            # 设置亮度
            if not light.set_brightness(brightness):
                messagebox.showerror(translator.t('config_ui.light_control_error'), translator.t('config_ui.light_brightness_error'))
                return
            
            # 切换开关状态
            new_state = not self.test_button_state.get()
            if not light.set_switch(new_state):
                messagebox.showerror(translator.t('config_ui.light_control_error'), translator.t('config_ui.light_switch_error'))
                return
            
            # 更新按钮状态
            self.test_button_state.set(new_state)
            self._update_test_button_color()
            
        except ValueError as e:
            messagebox.showerror(translator.t('config_ui.light_control_error'), f"{translator.t('config_ui.param_error')}：{str(e)}")
        except Exception as e:
            messagebox.showerror(translator.t('config_ui.light_control_error'), f"{translator.t('config_ui.light_control_error')}：{str(e)}")
