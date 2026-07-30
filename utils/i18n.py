# -*- coding: utf-8 -*-

"""
    File        : i18n.py
    Brief       : Internationalization (i18n) module for Vision Driver Box
    Author      : Jim
    Date        : 2026/7/8
    Copyright(c):
    Note        : Supports Chinese (zh_CN, English (en_US), Vietnamese (vi_VN)
"""

import os
import sys
import yaml
from typing import Dict, Any
from .utils import get_resource_path


class Translator(object):
    """Singleton translator class for managing multi-language support"""
    
    _instance = None
    
    # Supported languages
    LANGUAGES = {
        "zh_CN": "简体中文",
        "en_US": "English",
        "vi_VN": "Tiếng Việt"
    }
    
    # Default translations (fallback if YAML file not found)
    DEFAULT_TRANSLATIONS = {
        "zh_CN": {
            "tray_menu": {
                "start_stop": "一键启动",
                "stop": "一键停止",
                "capture": "采集图像",
                "capture_stop": "采集停止",
                "image_stitch": "图像拼接",
                "settings": "参数设置",
                "tools": "应用工具",
                "generate_gantt": "生成甘特",
                "language": "语言选择",
                "exit": "退出"
            },
            "notifications": {
                "system_started": "系统已成功启动",
                "system_stopped": "系统已停止并释放资源",
                "capture_started": "采集图像模式已启动",
                "capture_stopped": "采集已停止并释放资源",
                "app_started": "软件已成功启动并运行在后台",
                "app_title": "Vision Driver Box",
                "error_title": "错误",
                "startup_failed": "启动失败",
                "capture_failed": "采集启动失败"
            },
            "config_ui": {
                "title": "参数设置",
                "ok": "确定",
                "cancel": "取消",
                "load_config": "加载配置",
                "save_config": "存储配置",
                "print_settings": "打印设置",
                "log_config": "日志配置",
                "camera_settings": "相机设置",
                "stitch_settings": "拼接设置",
                "board_settings": "板卡设置",
                "light_settings": "灯光设置",
                "listen_mode": "数据监听方式",
                "hot_folder": "热文件夹",
                "listen_addr": "数据监听地址",
                "listen_port": "数据监听端口",
                "listen_dir": "数据监听目录",
                "poll_interval": "数据轮询时间",
                "forward_mode": "转发目标方式",
                "forward_addr": "转发目标地址",
                "forward_port": "转发目标端口",
                "forward_delay": "转发目标延迟",
                "forward_timeout": "转发目标超时",
                "print_length": "打印长度设置",
                "print_width": "打印宽度设置",
                "buffer_size": "缓冲字节设置",
                "log_dir": "日志存储目录",
                "log_limit": "日志存储上限",
                "log_img_mode": "日志存图模式",
                "log_img_dir": "日志存图目录",
                "cam_buffer_count": "相机缓冲区数",
                "data_recv_addr": "数据接收地址",
                "data_recv_port": "数据接收端口",
                "capture_img_len": "采集图像长度",
                "capture_img_height": "采集图像高度",
                "calib_file": "标定文件选择",
                "capture_save_dir": "采集存储目录",
                "rip_send_dir": "白图发送目录",
                "cap_line_timeout": "采集行间超时",
                "cap_frame_timeout": "采集帧间超时",
                "stitch_left_ref": "拼接左侧基准",
                "stitch_right_ref": "拼接右侧基准",
                "img_stitch_offset": "图像拼接偏移",
                "canvas_start_pos": "画布开始位置",
                "canvas_end_pos": "画布结束位置",
                "overlap_offset_pix": "重叠偏移像素",
                "dpi": "DPI",
                "cal_sel": "校准程序选择",
                "stitch_timeout": "图像拼接超时",
                "export_calib_img": "导出校准图像",
                "realtime_display": "采集实时显示",
                "board_comm_addr": "通讯地址设置",
                "board_comm_port": "通讯端口设置",
                "board_comm_timeout": "通讯超时设置",
                "board_comm_retry": "通讯重试次数",
                "light_use_enabled": "使用灯光设置",
                "light_serial_port": "串口端口设置",
                "light_baudrate": "波特率设置",
                "light_comm_timeout": "通讯超时设置",
                "light_brightness": "灯光亮度设置",
                "test": "测试",
                "refresh": "刷新",
                "browse": "浏览",
                "save_success": "保存成功",
                "save_failed": "保存失败",
                "export_success": "配置已成功存储至",
                "export_failed": "存储配置失败",
                "import_success": "配置加载成功，请点击“确定”以应用更改。",
                "import_failed": "加载配置失败",
                "invalid_config": "无效的配置文件：特征头不匹配或格式错误。",
                "warning": "注意",
                "cal_switch_warning": "校准程序已切换，需同步变更标定文件！",
                "light_control_error": "灯光控制失败",
                "light_brightness_error": "灯光亮度设置失败",
                "light_switch_error": "灯光开关设置失败",
                "param_error": "参数格式错误",
                "stitch_select_dir": "选择拼接目录",
                "stitch_path_error": "所选目录中没有找到JSON配置文件",
                "stitch_success": "拼接成功",
                "stitch_process_error": "拼接过程中发生进程错误",
                "stitch_failed": "拼接失败",
                "stitch_result_empty": "拼接返回结果为空，请检查数据完整性",
                "gantt_select_file": "选择日志文件生成甘特图",
                "gantt_success": "甘特图已保存为 PDF",
                "gantt_dir_open": "已自动为你打开目录。",
                "gantt_failed": "无法生成甘特图",
                "app_running": "Vision Driver Box 已经在运行中。",
                "app_running_hint": "请在系统托盘查找图标。",
                "unit": {
                    "ms": "ms",
                    "s": "s",
                    "mm": "mm",
                    "KB": "KB",
                    "MB": "MB",
                    "cm": "cm",
                    "pix": "pix",
                    "次": "次"
                }
            },
            "options": {
                "old_version": "旧版",
                "new_version": "新版",
                "tcp_ip": "TCP/IP",
                "hs_dll": "HS DLL"
            }
        },
        "en_US": {
            "tray_menu": {
                "start_stop": "One Click Start",
                "stop": "One Click Stop",
                "capture": "Capture Image",
                "capture_stop": "Stop Capture",
                "image_stitch": "Image Stitch",
                "settings": "Settings",
                "tools": "Tools",
                "generate_gantt": "Generate Gantt",
                "language": "Language",
                "exit": "Exit"
            },
            "notifications": {
                "system_started": "System started successfully",
                "system_stopped": "System stopped and resources released",
                "capture_started": "Capture image mode started",
                "capture_stopped": "Capture stopped and resources released",
                "app_started": "Application started successfully and running in background",
                "app_title": "Vision Driver Box",
                "error_title": "Error",
                "startup_failed": "Startup failed",
                "capture_failed": "Capture startup failed"
            },
            "config_ui": {
                "title": "Settings",
                "ok": "OK",
                "cancel": "Cancel",
                "load_config": "Load Config",
                "save_config": "Save Config",
                "print_settings": "Print Settings",
                "log_config": "Log Configuration",
                "camera_settings": "Camera Settings",
                "stitch_settings": "Stitch Settings",
                "board_settings": "Board Settings",
                "light_settings": "Light Settings",
                "listen_mode": "Listen Mode",
                "hot_folder": "Hot Folder",
                "listen_addr": "Listen Address",
                "listen_port": "Listen Port",
                "listen_dir": "Listen Directory",
                "poll_interval": "Poll Interval",
                "forward_mode": "Forward Mode",
                "forward_addr": "Forward Address",
                "forward_port": "Forward Port",
                "forward_delay": "Forward Delay",
                "forward_timeout": "Forward Timeout",
                "print_length": "Print Length",
                "print_width": "Print Width",
                "buffer_size": "Buffer Size",
                "log_dir": "Log Directory",
                "log_limit": "Log Limit",
                "log_img_mode": "Log Image Mode",
                "log_img_dir": "Log Image Directory",
                "cam_buffer_count": "Camera Buffer Count",
                "data_recv_addr": "Data Receive Address",
                "data_recv_port": "Data Receive Port",
                "capture_img_len": "Capture Image Length",
                "capture_img_height": "Capture Image Height",
                "calib_file": "Calibration File",
                "capture_save_dir": "Capture Save Directory",
                "rip_send_dir": "RIP Send Directory",
                "cap_line_timeout": "Capture Line Timeout",
                "cap_frame_timeout": "Capture Frame Timeout",
                "stitch_left_ref": "Stitch Left Reference",
                "stitch_right_ref": "Stitch Right Reference",
                "img_stitch_offset": "Image Stitch Offset",
                "canvas_start_pos": "Canvas Start Position",
                "canvas_end_pos": "Canvas End Position",
                "overlap_offset_pix": "Overlap Offset Pixel",
                "dpi": "DPI",
                "cal_sel": "Calibration Selection",
                "stitch_timeout": "Stitch Timeout",
                "export_calib_img": "Export Calibrated Image",
                "realtime_display": "Capture Real-time Display",
                "board_comm_addr": "Board Communication Address",
                "board_comm_port": "Board Communication Port",
                "board_comm_timeout": "Board Communication Timeout",
                "board_comm_retry": "Board Communication Retry",
                "light_use_enabled": "Enable Light Control",
                "light_serial_port": "Serial Port",
                "light_baudrate": "Baud Rate",
                "light_comm_timeout": "Communication Timeout",
                "light_brightness": "Light Brightness",
                "test": "Test",
                "refresh": "Refresh",
                "browse": "Browse",
                "save_success": "Saved successfully",
                "save_failed": "Save failed",
                "export_success": "Configuration exported successfully to",
                "export_failed": "Export configuration failed",
                "import_success": "Configuration loaded successfully. Please click OK to apply changes.",
                "import_failed": "Load configuration failed",
                "invalid_config": "Invalid configuration file: header mismatch or format error.",
                "warning": "Warning",
                "cal_switch_warning": "Calibration program switched, please update calibration file accordingly!",
                "light_control_error": "Light control failed",
                "light_brightness_error": "Light brightness setting failed",
                "light_switch_error": "Light switch setting failed",
                "param_error": "Parameter format error",
                "stitch_select_dir": "Select Stitch Directory",
                "stitch_path_error": "No JSON configuration file found in selected directory",
                "stitch_success": "Stitch successful",
                "stitch_process_error": "Process error occurred during stitching",
                "stitch_failed": "Stitch failed",
                "stitch_result_empty": "Stitch returned empty result, please check data integrity",
                "gantt_select_file": "Select Log File to Generate Gantt",
                "gantt_success": "Gantt chart saved as PDF",
                "gantt_dir_open": "Directory opened automatically for you.",
                "gantt_failed": "Failed to generate Gantt chart",
                "app_running": "Vision Driver Box is already running.",
                "app_running_hint": "Please look for the icon in the system tray.",
                "unit": {
                    "ms": "ms",
                    "s": "s",
                    "mm": "mm",
                    "KB": "KB",
                    "MB": "MB",
                    "cm": "cm",
                    "pix": "pix",
                    "次": "times"
                }
            },
            "options": {
                "old_version": "Old Version",
                "new_version": "New Version",
                "tcp_ip": "TCP/IP",
                "hs_dll": "HS DLL"
            }
        },
        "vi_VN": {
            "tray_menu": {
                "start_stop": "Khởi động một lần",
                "stop": "Dừng một lần",
                "capture": "Chụp ảnh",
                "capture_stop": "Dừng chụp",
                "image_stitch": "Ghép ảnh",
                "settings": "Cài đặt",
                "tools": "Công cụ",
                "generate_gantt": "Tạo Gantt",
                "language": "Ngôn ngữ",
                "exit": "Thoát"
            },
            "notifications": {
                "system_started": "Hệ thống khởi động thành công",
                "system_stopped": "Hệ thống đã dừng và giải phóng tài nguyên",
                "capture_started": "Chế độ chụp ảnh đã bắt đầu",
                "capture_stopped": "Đã dừng chụp và giải phóng tài nguyên",
                "app_started": "Ứng dụng khởi động thành công và chạy trong nền",
                "app_title": "Vision Driver Box",
                "error_title": "Lỗi",
                "startup_failed": "Khởi động thất bại",
                "capture_failed": "Khởi động chụp thất bại"
            },
            "config_ui": {
                "title": "Cài đặt",
                "ok": "OK",
                "cancel": "Hủy",
                "load_config": "Tải cấu hình",
                "save_config": "Lưu cấu hình",
                "print_settings": "Cài đặt in",
                "log_config": "Cấu hình log",
                "camera_settings": "Cài đặt camera",
                "stitch_settings": "Cài đặt ghép ảnh",
                "board_settings": "Cài đặt bo mạch",
                "light_settings": "Cài đặt đèn",
                "listen_mode": "Chế độ lắng nghe",
                "hot_folder": "Thư mục nóng",
                "listen_addr": "Địa chỉ lắng nghe",
                "listen_port": "Cổng lắng nghe",
                "listen_dir": "Thư mục lắng nghe",
                "poll_interval": "Khoảng thời gian thăm dò",
                "forward_mode": "Chế độ chuyển tiếp",
                "forward_addr": "Địa chỉ chuyển tiếp",
                "forward_port": "Cổng chuyển tiếp",
                "forward_delay": "Độ trễ chuyển tiếp",
                "forward_timeout": "Thời gian chờ chuyển tiếp",
                "print_length": "Chiều dài in",
                "print_width": "Chiều rộng in",
                "buffer_size": "Kích thước bộ đệm",
                "log_dir": "Thư mục log",
                "log_limit": "Giới hạn log",
                "log_img_mode": "Chế độ lưu ảnh log",
                "log_img_dir": "Thư mục lưu ảnh log",
                "cam_buffer_count": "Số bộ đệm camera",
                "data_recv_addr": "Địa chỉ nhận dữ liệu",
                "data_recv_port": "Cổng nhận dữ liệu",
                "capture_img_len": "Chiều dài ảnh chụp",
                "capture_img_height": "Chiều cao ảnh chụp",
                "calib_file": "Tệp hiệu chỉnh",
                "capture_save_dir": "Thư mục lưu ảnh chụp",
                "rip_send_dir": "Thư mục gửi RIP",
                "cap_line_timeout": "Thời gian chờ giữa các dòng",
                "cap_frame_timeout": "Thời gian chờ giữa các khung",
                "stitch_left_ref": "Tham chiếu trái ghép ảnh",
                "stitch_right_ref": "Tham chiếu phải ghép ảnh",
                "img_stitch_offset": "Độ lệch ghép ảnh",
                "canvas_start_pos": "Vị trí bắt đầu khung vẽ",
                "canvas_end_pos": "Vị trí kết thúc khung vẽ",
                "overlap_offset_pix": "Độ lệch pixel chồng chéo",
                "dpi": "DPI",
                "cal_sel": "Lựa chọn chương trình hiệu chỉnh",
                "stitch_timeout": "Thời gian chờ ghép ảnh",
                "export_calib_img": "Xuất ảnh hiệu chỉnh",
                "realtime_display": "Hiển thị thời gian thực",
                "board_comm_addr": "Địa chỉ giao tiếp bo mạch",
                "board_comm_port": "Cổng giao tiếp bo mạch",
                "board_comm_timeout": "Thời gian chờ giao tiếp bo mạch",
                "board_comm_retry": "Số lần thử lại giao tiếp bo mạch",
                "light_use_enabled": "Bật điều khiển đèn",
                "light_serial_port": "Cổng nối tiếp",
                "light_baudrate": "Tốc độ truyền",
                "light_comm_timeout": "Thời gian chờ giao tiếp",
                "light_brightness": "Độ sáng đèn",
                "test": "Kiểm tra",
                "refresh": "Làm mới",
                "browse": "Duyệt",
                "save_success": "Lưu thành công",
                "save_failed": "Lưu thất bại",
                "export_success": "Đã xuất cấu hình thành công đến",
                "export_failed": "Xuất cấu hình thất bại",
                "import_success": "Đã tải cấu hình thành công. Vui lòng nhấn OK để áp dụng thay đổi.",
                "import_failed": "Tải cấu hình thất bại",
                "invalid_config": "Tệp cấu hình không hợp lệ: không khớp tiêu đề hoặc lỗi định dạng.",
                "warning": "Cảnh báo",
                "cal_switch_warning": "Đã chuyển chương trình hiệu chỉnh, vui lòng cập nhật tệp hiệu chỉnh tương ứng!或者",
                "light_control_error": "Điều khiển đèn thất bại",
                "light_brightness_error": "Đặt độ sáng đèn thất bại",
                "light_switch_error": "Đặt công tắc đèn thất bại",
                "param_error": "Lỗi định dạng tham số",
                "stitch_select_dir": "Chọn thư mục ghép ảnh",
                "stitch_path_error": "Không tìm thấy tệp cấu hình JSON trong thư mục đã chọn",
                "stitch_success": "Ghép ảnh thành công",
                "stitch_process_error": "Lỗi quy trình xảy ra trong quá trình ghép ảnh",
                "stitch_failed": "Ghép ảnh thất bại",
                "stitch_result_empty": "Kết quả ghép ảnh rỗng, vui lòng kiểm tra tính toàn vẹn dữ liệu",
                "gantt_select_file": "Chọn tệp log để tạo Gantt",
                "gantt_success": "Đã lưu biểu đồ Gantt dưới dạng PDF",
                "gantt_dir_open": "Đã tự động mở thư mục cho bạn.",
                "gantt_failed": "Không thể tạo biểu đồ Gantt",
                "app_running": "Vision Driver Box đang chạy.",
                "app_running_hint": "Vui lòng tìm biểu tượng trong khay hệ thống.",
                "unit": {
                    "ms": "ms",
                    "s": "s",
                    "mm": "mm",
                    "KB": "KB",
                    "MB": "MB",
                    "cm": "cm",
                    "pix": "pix",
                    "次": "lần"
                }
            },
            "options": {
                "old_version": "Phiên bản cũ",
                "new_version": "Phiên bản mới",
                "tcp_ip": "TCP/IP",
                "hs_dll": "HS DLL"
            }
        }
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Translator, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_lang = "zh_CN"
        self._translations = self.DEFAULT_TRANSLATIONS.copy()
        self._load_translations()

    def _get_translations_path(self):
        """Get the path to translations.yaml file"""
        try:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(__file__))
            return os.path.join(base_dir, "translations.yaml")
        except Exception:
            return None

    def _load_translations(self):
        """Load translations from YAML file if available"""
        translations_path = self._get_translations_path()
        if translations_path and os.path.exists(translations_path):
            try:
                with open(translations_path, 'r', encoding='utf-8') as f:
                    file_translations = yaml.safe_load(f)
                    if file_translations:
                        # Merge with default translations
                        for lang in self._translations:
                            if lang in file_translations:
                                self._deep_update(self._translations[lang], file_translations[lang])
            except Exception:
                pass

    def _deep_update(self, d: Dict, u: Dict):
        """Deep update dictionary"""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v

    def set_language(self, lang_code: str):
        """Set current language"""
        if lang_code in self.LANGUAGES:
            self._current_lang = lang_code

    def get_language(self) -> str:
        """Get current language code"""
        return self._current_lang

    def get_language_name(self) -> str:
        """Get current language display name"""
        return self.LANGUAGES.get(self._current_lang, self._current_lang)

    def t(self, key: str, **kwargs) -> str:
        """Get translated text by key

        :param key: Translation key (e.g., "tray_menu.start_stop")
        :param kwargs: Format arguments
        :return: Translated text
        """
        keys = key.split('.')
        value = self._translations.get(self._current_lang, {})
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Fallback to default language
                value = self._translations.get("zh_CN", {})
                for k2 in keys:
                    if isinstance(value, dict) and k2 in value:
                        value = value[k2]
                    else:
                        return key
                break

        if isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        return key


# Singleton instance
translator = Translator()
