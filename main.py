# -*- coding: utf-8 -*- 

"""
    File        : main.py
    Brief       : Main entry for Vision Driver Box
    Author      : Jim
    Date        : 2026/5/15
    Copyright(c):
    Note        :
"""
import os, sys
import time
import threading
import pystray
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
from ui.config.config import ConfigUI
from ui.config.cfgcxt import config_context
from drivers.camera.Camera import Camera
from drivers.Printer import Printer
from utils.utils import logger, get_resource_path
from utils.gantt import generate_gantt_from_log

# Global states
is_started = False
is_running_process = False
is_cap_mode = False
icon_instance = None
camera_instance = None
printer_instance = None
mutex_handle = None  # Keep a reference to prevent garbage collection
runtime_error_msg = None
error_lock = threading.Lock()

# Activity tracking for animation (A-B-C icons)
active_sources = {
    'camera': False,
    'tool': False
}
activity_lock = threading.Lock()

# Icon resources
ICON_DIR = os.path.join('src', 'icon')
ICONS = {}

def load_icons():
    global ICONS
    try:
        # Use get_resource_path to ensure icons are found when bundled
        icon_dir = get_resource_path(os.path.join('src', 'icon'))
        # Use .ico files for better compatibility with Windows tray and notifications
        ICONS = {
            'standby': Image.open(os.path.join(icon_dir, 'State_Standby.ico')),
            'offline': Image.open(os.path.join(icon_dir, 'State_Offline.ico')),
            'capMode': Image.open(os.path.join(icon_dir, 'State_CapMode.ico')),
            'A': Image.open(os.path.join(icon_dir, 'State_RunningA.ico')),
            'B': Image.open(os.path.join(icon_dir, 'State_RunningB.ico')),
            'C': Image.open(os.path.join(icon_dir, 'State_RunningC.ico')),
        }
    except Exception as e:
        logger.error(f"Failed to load icons: {e}")
        # Fallback to a simple image if icons are missing
        fallback = Image.new('RGB', (64, 64), color=(73, 109, 137))
        ICONS = {k: fallback for k in ['standby', 'offline', 'capMode', 'A', 'B', 'C']}

def update_activity_status(source, is_active):
    """Updates the global is_running_process based on multiple activity sources."""
    global is_running_process
    with activity_lock:
        if source in active_sources:
            active_sources[source] = is_active
        
        # System is considered "running" if ANY source is active
        is_running_process = any(active_sources.values())

def on_camera_status_change(is_active):
    """Callback for camera activity changes."""
    update_activity_status('camera', is_active)

def on_fatal_error(msg):
    """Callback triggered by drivers when a fatal error occurs."""
    global runtime_error_msg
    with error_lock:
        if runtime_error_msg is None:
            runtime_error_msg = msg

def handle_runtime_error():
    """Processes the runtime error, stops the system and updates UI."""
    global runtime_error_msg, icon_instance
    msg = None
    with error_lock:
        msg = runtime_error_msg
        runtime_error_msg = None
    
    if msg and icon_instance:
        logger.error(f"Runtime error detected: {msg}")
        stop_system()
        icon_instance.icon = ICONS['offline']
        icon_instance.notify(f"运行异常中断: {msg}", title="系统错误")
        icon_instance.update_menu()

def icon_animation_thread():
    """Cycles through A, B, C icons when is_running_process is True."""
    global is_running_process, icon_instance, runtime_error_msg
    frames = ['A', 'B', 'C']
    idx = 0
    was_running = False
    while True:
        # 1. Check for runtime errors from background threads
        if runtime_error_msg is not None:
            handle_runtime_error()

        # 2. Handle normal animation
        if is_running_process and icon_instance:
            icon_instance.icon = ICONS[frames[idx]]
            idx = (idx + 1) % len(frames)
            was_running = True
            time.sleep(0.5)
        else:
            if was_running and icon_instance:
                # Revert to appropriate icon when process stops
                if is_started:
                    icon_instance.icon = ICONS['standby']
                elif is_cap_mode:
                    icon_instance.icon = ICONS['capMode']
                else:
                    icon_instance.icon = ICONS['offline']
                was_running = False
            time.sleep(0.2)

def create_camera_instance(fatal_error_cb=None, status_cb=None):
    """Helper to create a Camera instance with current config."""
    config = config_context.config
    return Camera(
        cam_buffer_count=config.get('cam_buffer_count', 10),
        data_recv_addr=config.get('data_recv_addr', "127.0.0.1"),
        data_recv_port=config.get('data_recv_port', 9120),
        capture_img_len=config.get('capture_img_len', 100.0),
        capture_save_dir=config.get('capture_save_dir', r"D:\vsDriverbox\cap"),
        rip_send_dir=config.get('rip_send_dir', r"D:\vsDriverbox\rip"),
        dpi=config.get('dpi', 300),
        stitch_left_ref=config.get('stitch_left_ref', 2461790),
        stitch_right_ref=config.get('stitch_right_ref', 29057700),
        img_stitch_offset=config.get('img_stitch_offset', 629),
        canvas_start_pos=config.get('canvas_start_pos', 7906),
        canvas_end_pos=config.get('canvas_end_pos', 21259),
        overlap_offset_pix=config.get('overlap_offset_pix', 500),
        calib_file=config.get('calib_file', r"D:\vsDriverbox\calib.yaml"),
        board_comm_addr=config.get('board_comm_addr', "192.168.1.99"),
        board_comm_port=config.get('board_comm_port', 502),
        board_comm_timeout=config.get('board_comm_timeout', 3000),
        board_comm_retry=config.get('board_comm_retry', 3),
        light_serial_port=config.get('light_serial_port', 'COM3'),
        light_baudrate=config.get('light_baudrate', 19200),
        light_comm_timeout=config.get('light_comm_timeout', 1000),
        log_cb=logger.info,
        fatal_error_cb=fatal_error_cb,
        status_cb=status_cb
    )

def start_system(is_capture=False):
    """Common logic to start camera and printer drivers."""
    global camera_instance, printer_instance
    try:
        config = config_context.config
        logger.info(f"Starting system (Capture Mode: {is_capture}) with current configuration...")

        # 1. Instantiate Camera
        try:
            camera_instance = create_camera_instance(
                fatal_error_cb=on_fatal_error,
                status_cb=on_camera_status_change
            )
        except Exception as e:
            logger.error(f"Failed to create camera instance: {e}")
            return False, f"相机驱动初始化失败: {str(e)}"

        # 2. Instantiate Printer
        printer_instance = Printer(
            listen_ip=config.get('data_listen_addr', "127.0.0.1"),
            listen_port=config.get('data_listen_port', 9111),
            target_ip=config.get('forward_target_addr', "127.0.0.1"),
            target_port=config.get('forward_target_port', 9100),
            print_length=config.get('print_length', 100000),
            buffer_size=config.get('buffer_size', 10240),
            log_cb=logger.info,
            fatal_error_cb=on_fatal_error
        )

        # 3. Set capture mode if requested
        if is_capture:
            camera_instance.set_capMode(True)

        # 4. Start drivers
        success, err = camera_instance.start()
        if not success:
            raise Exception(err)
        
        success, err = printer_instance.start()
        if not success:
            raise Exception(err)

        return True, None
    except Exception as e:
        # Cleanup on failure
        if camera_instance:
            try: camera_instance.stop()
            except: pass
        if printer_instance:
            try: printer_instance.stop()
            except: pass
        camera_instance = None
        printer_instance = None
        return False, str(e)

def stop_system():
    """Common logic to stop camera and printer drivers."""
    global camera_instance, printer_instance, is_started, is_running_process, is_cap_mode
    try:
        logger.info("Stopping system...")
        if camera_instance:
            camera_instance.stop()
        if printer_instance:
            printer_instance.stop()
    except Exception as e:
        logger.error(f"Error during system stop: {e}")
    finally:
        camera_instance = None
        printer_instance = None
        is_started = False
        is_running_process = False
        is_cap_mode = False

def on_toggle_start_stop(icon, item):
    global is_started, is_running_process, is_cap_mode
    
    if not is_started:
        success, error_msg = start_system(is_capture=False)
        if success:
            is_started = True
            is_cap_mode = False
            is_running_process = False
            icon.icon = ICONS['standby']
            logger.info("System started successfully")
            icon.notify("系统已成功启动", title="Vision Driver Box")
        else:
            logger.error(f"Startup failed: {error_msg}")
            icon.notify(f"启动失败: {error_msg}", title="错误")
            icon.icon = ICONS['offline']
    else:
        stop_system()
        icon.icon = ICONS['offline']
        logger.info("System stopped and resources released")
        icon.notify("系统已停止并释放资源", title="Vision Driver Box")
    
    icon.update_menu()

def on_capture_image(icon, item):
    global is_cap_mode, is_running_process, is_started
    
    if not is_cap_mode:
        # Start capture mode
        success, error_msg = start_system(is_capture=True)
        if success:
            is_cap_mode = True
            is_started = False # Mutual exclusion: not "started" in the normal sense
            is_running_process = False
            icon.icon = ICONS['capMode']
            logger.info("Capture image mode entered successfully")
            icon.notify("采集图像模式已启动", title="Vision Driver Box")
        else:
            logger.error(f"Capture startup failed: {error_msg}")
            icon.notify(f"采集启动失败: {error_msg}", title="错误")
            icon.icon = ICONS['offline']
    else:
        # Stop capture mode (same as stop_system)
        stop_system()
        icon.icon = ICONS['offline']
        logger.info("Capture mode stopped and resources released")
        icon.notify("采集已停止并释放资源", title="Vision Driver Box")
    
    icon.update_menu()

def on_image_stitch(icon, item):
    """Handles offline image stitching from a directory of JSON and images."""
    global camera_instance
    
    # 1. Ask for directory
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askdirectory(parent=root, title="选择拼接目录")
    
    if not path:
        root.destroy()
        return

    # 2. Check for JSON file
    json_files = [f for f in os.listdir(path) if f.endswith('.json')]
    if not json_files:
        messagebox.showwarning("路径选择错误", "所选目录中没有找到JSON配置文件", parent=root)
        root.destroy()
        return

    # 3. Call stitch_from_json
    try:
        update_activity_status('tool', True)
        temp_instance = False
        cam = camera_instance
        if cam is None:
            cam = create_camera_instance(
                fatal_error_cb=on_fatal_error,
                status_cb=on_camera_status_change
            )
            temp_instance = True
        
        # Determine target JSON
        target_json = "LocalImageInfos.json"
        if target_json not in json_files:
            target_json = json_files[0]
            
        logger.info(f"Starting image stitching from {path} using {target_json}")
        stitched_img_np = cam.stitch_from_json(path, target_json)
        
        if stitched_img_np is not None:
            # Save the result
            save_path = os.path.join(path, "stitched_result.tif")
            Image.fromarray(stitched_img_np).save(save_path)
            messagebox.showinfo("拼接成功", f"图像拼接完成，已保存至：\n{save_path}", parent=root)
            logger.info(f"Image stitching completed and saved to {save_path}")
        else:
            messagebox.showwarning("拼接失败", "拼接返回结果为空，请检查数据完整性", parent=root)
            
    except Exception as e:
        logger.error(f"Image stitching failed: {e}")
        messagebox.showerror("拼接失败", f"执行拼接时发生错误：\n{str(e)}", parent=root)
    finally:
        update_activity_status('tool', False)
        root.destroy()

def on_config(icon, item):
    """Opens the configuration UI in a separate thread."""
    def run_config():
        try:
            # ConfigUI creates its own tk.Tk() if root is None
            ui = ConfigUI()
            ui.show()
        except Exception as e:
            logger.error(f"Failed to open config UI: {e}")

    threading.Thread(target=run_config, daemon=True).start()

def on_generate_gantt(icon, item):
    """Opens a file dialog to select a log file and generates a Gantt chart in a separate thread."""
    def run_gantt():
        try:
            update_activity_status('tool', True)
            # 1. Ask for log file
            root = tk.Tk()
            root.withdraw()
            
            default_dir = config_context.config.get('log_dir', r"D:\vsDriverbox\log")
            if not os.path.exists(default_dir):
                default_dir = os.path.expanduser("~")
            
            file_path = filedialog.askopenfilename(
                parent=root,
                title="选择日志文件生成甘特图",
                initialdir=default_dir,
                filetypes=[("Log files", "*.log"), ("All files", "*.*")]
            )
            
            if not file_path:
                root.destroy()
                return

            # 3. Call generation utility
            logger.info(f"Generating Gantt PDF from: {file_path}")
            pdf_output = generate_gantt_from_log(file_path)
            
            # 4. Notify user of success
            if pdf_output:
                logger.info(f"Gantt PDF saved successfully: {pdf_output}")
                # Open the directory to show the file
                os.startfile(os.path.dirname(pdf_output))
                messagebox.showinfo("生成成功", f"甘特图已保存为 PDF：\n{pdf_output}\n\n已自动为你打开目录。", parent=root)
            
            root.destroy()
            
        except Exception as e:
            logger.error(f"Failed to generate Gantt chart: {e}")
            # Use a temporary root for error message if needed
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror("错误", f"无法生成甘特图：\n{str(e)}", parent=err_root)
            err_root.destroy()
        finally:
            update_activity_status('tool', False)

    threading.Thread(target=run_gantt, daemon=True).start()

def on_exit(icon, item):
    global is_running_process
    is_running_process = False
    icon.stop()

def get_start_stop_text(item):
    return "一键停止" if is_started else "一键启动"

def get_capture_text(item):
    return "采集停止" if is_cap_mode else "采集图像"

def is_capture_enabled(item):
    # Disabled if normal start is active
    return not is_started

def is_start_stop_enabled(item):
    # Disabled if capture mode is active
    return not is_cap_mode

def is_tools_enabled(item):
    # Disabled if system is started
    return not is_started

def setup_tray():
    global icon_instance
    load_icons()
    
    menu = pystray.Menu(
        pystray.MenuItem(get_start_stop_text, on_toggle_start_stop, enabled=is_start_stop_enabled),
        pystray.MenuItem(get_capture_text, on_capture_image, enabled=is_capture_enabled),
        pystray.MenuItem("图像拼接", on_image_stitch),
        pystray.MenuItem("参数设置", on_config),
        pystray.MenuItem("应用工具", pystray.Menu(
            pystray.MenuItem("生成甘特", on_generate_gantt)
        ), enabled=is_tools_enabled),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit)
    )
    
    icon_instance = pystray.Icon(
        'vsDriverbox',
        icon=ICONS['offline'], # 恢复为 offline 启动，符合原逻辑
        title='Vision Driver Box',
        menu=menu
    )

    # Start animation thread
    threading.Thread(target=icon_animation_thread, daemon=True).start()
    
    # 软件启动气泡提示
    def notify_startup():
        time.sleep(2.0) 
        
        # 即使设置了 AppUserModelID，在脚本运行环境下，系统有时仍无法自动关联图标
        # 我们在这里确保发送通知时，托盘图标处于 standby 状态
        if not is_started:
            old_icon = icon_instance.icon
            icon_instance.icon = ICONS['standby'] # 强制切换到 standby
            time.sleep(0.5) # 给 Windows 足够的系统时间来缓存这个新图标
            icon_instance.notify("软件已成功启动并运行在后台", title="Vision Driver Box")
            time.sleep(2.0) # 保持时间加长，确保气泡弹出期间图标资源有效
            if not is_started:
                icon_instance.icon = old_icon
    
    threading.Thread(target=notify_startup, daemon=True).start()
    
    icon_instance.run()

if __name__ == '__main__':
    # 0. Single instance check using Windows Mutex
    try:
        mutex_name = u"Global\\vsDriverBox_SingleInstance_Mutex"
        mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()
        
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            # Create a hidden root for the messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("程序已运行", "Vision Driver Box 已经在运行中。\n请在系统托盘查找图标。")
            root.destroy()
            os._exit(0)
    except Exception as e:
        # If mutex fails for some reason, we log it but might still try to run
        print(f"Mutex check failed: {e}")

    # 0. Set AppUserModelID to ensure notification shows correct icon and name
    # We set this in all environments to help Windows associate notifications with the app
    try:
        myappid = u'vsDriverBox.v1' # Consistent with AppUserModelID in Inno Setup
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception as e:
        logger.error(f"Failed to set AppUserModelID: {e}")

    # 1. Load configuration at startup
    config_context.load()

    # 2. Sync global logger with loaded config
    logger.sync_config(config_context.config)

    # 3. Setup system tray icon
    setup_tray()
