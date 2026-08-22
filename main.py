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
import multiprocessing
import pystray
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import numpy as np
from ui.config.config import ConfigUI
from ui.config.cfgcxt import config_context
from drivers.camera.Camera import Camera
from drivers.Printer import Printer
from utils.utils import logger, get_resource_path
from utils.mp_helper import ProcessProxy
from utils.gantt import generate_gantt_from_log
from utils.i18n import translator
from ui.realtime_display.RealtimeDisplayQt import run_viewer as run_qt_viewer # New import

# Global multiprocessing objects for the Qt viewer
qt_viewer_process = None
image_queue = None
manager = None

def start_qt_viewer_process():
    global qt_viewer_process, image_queue, manager
    if qt_viewer_process is None or not qt_viewer_process.is_alive():
        logger.info("Starting Real-time Qt Viewer process...")
        # Use a multiprocessing.Manager to create a Queue proxy that is safe to share
        if manager is None:
            manager = multiprocessing.Manager()
            logger.info(f"Realtime multiprocessing.Manager created: {manager}")

        image_queue = manager.Queue()
        logger.info(f"Realtime display queue created: {image_queue}")

        qt_viewer_process = multiprocessing.Process(target=run_qt_viewer, args=(image_queue,))
        qt_viewer_process.start()
        logger.info(f"Real-time Qt Viewer process started with PID: {qt_viewer_process.pid}")
    else:
        logger.warning("Real-time Qt Viewer process is already running.")

def stop_qt_viewer_process():
    global qt_viewer_process, image_queue, manager
    if qt_viewer_process and qt_viewer_process.is_alive():
        logger.info("Stopping Real-time Qt Viewer process...")
        if image_queue is not None:
            try:
                image_queue.put(None) # Send sentinel to gracefully shut down the receiver thread
            except Exception:
                logger.warning("Failed to put sentinel into image_queue")

        qt_viewer_process.join(timeout=5) # Give it some time to shut down
        if qt_viewer_process.is_alive():
            logger.warning("Real-time Qt Viewer process did not terminate gracefully, forcing termination.")
            qt_viewer_process.terminate()
        qt_viewer_process = None

        # Shutdown the manager and clear the proxy queue
        if manager is not None:
            try:
                manager.shutdown()
                logger.info("Realtime multiprocessing.Manager shutdown")
            except Exception:
                logger.warning("Failed to shutdown multiprocessing.Manager")
            manager = None

        image_queue = None
        logger.info("Real-time Qt Viewer process stopped.")
    else:
        logger.info("Real-time Qt Viewer process is not running.")

# Global constants
APP_VERSION = "1.1.1_Beta_07"

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
        new_status = any(active_sources.values())
        if new_status != is_running_process:
            is_running_process = new_status
            logger.info(f"Activity status changed: is_running_process={is_running_process} (source: {source}={is_active})")

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
        icon_instance.notify(f"{translator.t('notifications.error_title')}: {msg}", title=translator.t('notifications.error_title'))
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
    """Helper to create a Camera instance wrapped in a ProcessProxy."""
    config = config_context.config
    logger.info(f"Passing image_queue to Camera: {image_queue}")
    return ProcessProxy(
        Camera,
        cam_buffer_count=config.get('cam_buffer_count', 10),
        data_recv_addr=config.get('data_recv_addr', "127.0.0.1"),
        data_recv_port=config.get('data_recv_port', 9120),
        capture_img_len=config.get('capture_img_len', 100.0),
        capture_img_height=config.get('capture_img_height', 2048),
        capture_save_dir=config.get('capture_save_dir', r"D:\vsDriverbox\cap"),
        rip_send_dir=config.get('rip_send_dir', r"D:\vsDriverbox\rip"),
        cap_line_timeout=config.get('cap_line_timeout', 5000),
        cap_frame_timeout=config.get('cap_frame_timeout', 0),
        dpi=config.get('dpi', 300),
        stitch_left_ref=config.get('stitch_left_ref', 2461790),
        stitch_right_ref=config.get('stitch_right_ref', 29057700),
        img_stitch_offset=config.get('img_stitch_offset', 629),
        canvas_start_pos=config.get('canvas_start_pos', 7906),
        canvas_end_pos=config.get('canvas_end_pos', 21259),
        overlap_offset_pix=config.get('overlap_offset_pix', 500),
        stitch_timeout=config.get('stitch_timeout', 60),
        calib_file=config.get('calib_file', r"D:\vsDriverbox\calib.yaml"),
        cal_sel=config.get('cal_sel', '旧版'),
        board_comm_addr=config.get('board_comm_addr', "192.168.1.99"),
        board_comm_port=config.get('board_comm_port', 502),
        board_comm_timeout=config.get('board_comm_timeout', 3000),
        board_comm_retry=config.get('board_comm_retry', 3),
        light_serial_port=config.get('light_serial_port', 'COM3'),
        light_baudrate=config.get('light_baudrate', 19200),
        light_comm_timeout=config.get('light_comm_timeout', 1000),
        light_brightness=config.get('light_brightness', 100),
        light_use_enabled=config.get('light_use_enabled', True),
        log_img_mode=config.get('log_img_mode', False),
        log_img_dir=config.get('log_img_dir', r"D:\vsDriverbox\log\img"),
        realtime_display_enabled=config.get('realtime_display_enabled', False),
        log_cb=logger.info,
        fatal_error_cb=fatal_error_cb,
        status_cb=status_cb,
        image_queue = image_queue 
    )

def start_system(is_capture=False):
    """Common logic to start camera and printer drivers."""
    global camera_instance, printer_instance
    try:
        config = config_context.config
        
        # Ensure a new log file is created for each system start
        logger.sync_config(config, force=True)
        
        logger.info(f"Starting system (Capture Mode: {is_capture}) with current configuration...")

        # 1. Start Real-time Qt Viewer if enabled before camera creation
        if config.get('realtime_display_enabled', False):
            start_qt_viewer_process()

        # 2. Instantiate Camera
        try:
            camera_instance = create_camera_instance(
                fatal_error_cb=on_fatal_error,
                status_cb=on_camera_status_change
            )
        except Exception as e:
            logger.error(f"Failed to create camera instance: {e}")
            if config.get('realtime_display_enabled', False):
                stop_qt_viewer_process()
            return False, f"相机驱动初始化失败: {str(e)}"

        # 3. Instantiate Printer
        printer_instance = ProcessProxy(
            Printer,
            listen_mode=config.get('listen_mode', "TCP/IP"),
            listen_ip=config.get('data_listen_addr', "127.0.0.1"),
            listen_port=config.get('data_listen_port', 9111),
            listen_dir=config.get('data_listen_dir', ""),
            poll_interval=config.get('hot_poll_interval', 100),
            forward_mode=config.get('forward_mode', "TCP/IP"),
            target_ip=config.get('forward_target_addr', "127.0.0.1"),
            target_port=config.get('forward_target_port', 9100),
            print_length=config.get('print_length', 100000),
            buffer_size=config.get('buffer_size', 10240), 
            target_delay=config.get('forward_target_delay', 500),
            target_timeout=config.get('forward_target_timeout', 5),
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
        stop_qt_viewer_process() # Ensure Qt viewer process is stopped
        camera_instance = None
        printer_instance = None
        is_started = False
        is_cap_mode = False
        # Reset all activity sources when system stops
        with activity_lock:
            for source in active_sources:
                active_sources[source] = False
            global is_running_process
            is_running_process = False

def on_toggle_start_stop(icon, item):
    global is_started, is_running_process, is_cap_mode
    
    if not is_started:
        success, error_msg = start_system(is_capture=False)
        if success:
            is_started = True
            is_cap_mode = False
            icon.icon = ICONS['standby']
            logger.info("System started successfully")
            icon.notify(translator.t('notifications.system_started'), title=translator.t('notifications.app_title'))
        else:
            logger.error(f"Startup failed: {error_msg}")
            icon.notify(f"{translator.t('notifications.startup_failed')}: {error_msg}", title=translator.t('notifications.error_title'))
            icon.icon = ICONS['offline']
    else:
        stop_system()
        icon.icon = ICONS['offline']
        logger.info("System stopped and resources released")
        icon.notify(translator.t('notifications.system_stopped'), title=translator.t('notifications.app_title'))
    
    icon.update_menu()

def on_capture_image(icon, item):
    global is_cap_mode, is_running_process, is_started
    
    if not is_cap_mode:
        # Start capture mode
        success, error_msg = start_system(is_capture=True)
        if success:
            is_cap_mode = True
            is_started = False # Mutual exclusion: not "started" in the normal sense
            icon.icon = ICONS['capMode']
            logger.info("Capture image mode entered successfully")
            icon.notify(translator.t('notifications.capture_started'), title=translator.t('notifications.app_title'))
        else:
            logger.error(f"Capture startup failed: {error_msg}")
            icon.notify(f"{translator.t('notifications.capture_failed')}: {error_msg}", title=translator.t('notifications.error_title'))
            icon.icon = ICONS['offline']
    else:
        # Stop capture mode (same as stop_system)
        stop_system()
        icon.icon = ICONS['offline']
        logger.info("Capture mode stopped and resources released")
        icon.notify(translator.t('notifications.capture_stopped'), title=translator.t('notifications.app_title'))
    
    icon.update_menu()

def create_tray_menu():
    """Create tray menu with current language"""
    # Create language submenu
    language_menu_items = []
    for lang_code, lang_name in translator.LANGUAGES.items():
        language_menu_items.append(
            pystray.MenuItem(
                lang_name,
                create_language_handler(lang_code),
                checked=is_language_checked(lang_code)
            )
        )
    
    return pystray.Menu(
        pystray.MenuItem(get_start_stop_text, on_toggle_start_stop, enabled=is_start_stop_enabled),
        pystray.MenuItem(get_capture_text, on_capture_image, enabled=is_capture_enabled),
        pystray.MenuItem(translator.t('tray_menu.image_stitch'), on_image_stitch),
        pystray.MenuItem(translator.t('tray_menu.settings'), on_config),
        pystray.MenuItem(translator.t('tray_menu.tools'), pystray.Menu(
            pystray.MenuItem(translator.t('tray_menu.generate_gantt'), on_generate_gantt)
        ), enabled=is_tools_enabled),
        pystray.MenuItem(translator.t('tray_menu.language'), pystray.Menu(*language_menu_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(translator.t('tray_menu.exit'), on_exit)
    )

def on_change_language(lang_code):
    """Handle language change"""
    translator.set_language(lang_code)
    config_context.config["language"] = lang_code
    config_context.save(config_context.config)
    global icon_instance
    if icon_instance:
        # Recreate the menu with new language
        icon_instance.menu = create_tray_menu()
        icon_instance.update_menu()

def on_image_stitch(icon, item):
    """Handles offline image stitching from a directory of JSON and images in a separate thread."""
    def run_stitch():
        global camera_instance
        try:
            # 1. Ask for directory (Must be in main thread or handle carefully with tk)
            # Actually, pystray callbacks are often already in a separate thread.
            # But let's use a temporary root.
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askdirectory(parent=root, title=translator.t('config_ui.stitch_select_dir'))
            
            if not path:
                root.destroy()
                return

            # 2. Check for JSON file
            json_files = [f for f in os.listdir(path) if f.endswith('.json')]
            if not json_files:
                messagebox.showwarning(translator.t('config_ui.warning'), translator.t('config_ui.stitch_path_error'), parent=root)
                root.destroy()
                return

            # 3. Call stitch_from_json
            update_activity_status('tool', True)
            try:
                temp_instance = False
                cam = camera_instance
                if cam is None:
                    cam = create_camera_instance(
                        fatal_error_cb=on_fatal_error,
                        status_cb=on_camera_status_change
                    )
                    temp_instance = True
                
                # Ensure config/yaml is loaded even if system is not "started"
                # This fixes stitching failure due to missing calibration parameters
                cam.load_config()
                
                # Determine target JSON
                target_json = "LocalImageInfos.json"
                if target_json not in json_files:
                    target_json = json_files[0]
                
                # Use configured stitch timeout
                stitch_timeout = float(config_context.config.get('stitch_timeout', 60.0))
                
                logger.info(f"Starting image stitching from {path} using {target_json} with timeout {stitch_timeout}s")
                stitched_img_np = cam.stitch_from_json(path, target_json, timeout=stitch_timeout)
                
                if isinstance(stitched_img_np, np.ndarray):
                    # Save the result with correct DPI
                    save_path = os.path.join(path, "stitched_result.tif")
                    dpi_val = cam.get_dpi()
                    Image.fromarray(stitched_img_np).save(save_path, dpi=(dpi_val, dpi_val))
                    messagebox.showinfo(translator.t('config_ui.stitch_success'), f"{translator.t('config_ui.stitch_success')}：\n{save_path}", parent=root)
                    logger.info(f"Image stitching completed and saved to {save_path}")
                elif isinstance(stitched_img_np, tuple) and not stitched_img_np[0]:
                    # ProcessProxy error return
                    error_detail = stitched_img_np[1]
                    logger.error(f"Image stitching process error: {error_detail}")
                    messagebox.showerror(translator.t('config_ui.stitch_failed'), f"{translator.t('config_ui.stitch_process_error')}：\n{error_detail}", parent=root)
                else:
                    messagebox.showwarning(translator.t('config_ui.stitch_failed'), translator.t('config_ui.stitch_result_empty'), parent=root)
            finally:
                update_activity_status('tool', False)
                root.destroy()
                
        except Exception as e:
            logger.error(f"Image stitching failed: {e}")
            # Use a new root for the error box if the previous one is gone
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror(translator.t('config_ui.stitch_failed'), f"{translator.t('config_ui.stitch_failed')}：\n{str(e)}", parent=err_root)
            err_root.destroy()

    threading.Thread(target=run_stitch, daemon=True).start()

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
                title=translator.t('config_ui.gantt_select_file'),
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
                messagebox.showinfo(translator.t('config_ui.gantt_success'), f"{translator.t('config_ui.gantt_success')}：\n{pdf_output}\n\n{translator.t('config_ui.gantt_dir_open')}", parent=root)
            
            root.destroy()
            
        except Exception as e:
            logger.error(f"Failed to generate Gantt chart: {e}")
            # Use a temporary root for error message if needed
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror(translator.t('config_ui.gantt_failed'), f"{translator.t('config_ui.gantt_failed')}：\n{str(e)}", parent=err_root)
            err_root.destroy()
        finally:
            update_activity_status('tool', False)

    threading.Thread(target=run_gantt, daemon=True).start()

def on_exit(icon, item):
    global is_running_process
    is_running_process = False
    icon.stop()

def get_start_stop_text(item):
    return translator.t('tray_menu.stop') if is_started else translator.t('tray_menu.start_stop')

def get_capture_text(item):
    return translator.t('tray_menu.capture_stop') if is_cap_mode else translator.t('tray_menu.capture')

def is_capture_enabled(item):
    # Disabled if normal start is active
    return not is_started

def is_start_stop_enabled(item):
    # Disabled if capture mode is active
    return not is_cap_mode

def is_tools_enabled(item):
    # Disabled if system is started
    return not is_started

def is_language_checked(lang_code):
    def checked(item):
        return translator.get_language() == lang_code
    return checked

def create_language_handler(lang_code):
    def handler(icon, item):
        on_change_language(lang_code)
    return handler

def setup_tray():
    global icon_instance
    load_icons()
    
    # Create initial tray menu with current language
    menu = create_tray_menu()
    
    icon_instance = pystray.Icon(
        'vsDriverbox',
        icon=ICONS['offline'], # 恢复为 offline 启动，符合原逻辑
        title=f'Vision Driver Box v{APP_VERSION}',
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
            icon_instance.notify(translator.t('notifications.app_started'), title=translator.t('notifications.app_title'))
            time.sleep(2.0) # 保持时间加长，确保气泡弹出期间图标资源有效
            if not is_started:
                icon_instance.icon = old_icon
    
    threading.Thread(target=notify_startup, daemon=True).start()
    
    icon_instance.run()

if __name__ == '__main__':
    # Support for PyInstaller bundled executables
    multiprocessing.freeze_support()
    
    # 0. Single instance check using Windows Mutex
    try:
        mutex_name = u"Global\\vsDriverBox_SingleInstance_Mutex"
        mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()
        
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            # Create a hidden root for the messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(translator.t('config_ui.warning'), f"{translator.t('config_ui.app_running')}\n{translator.t('config_ui.app_running_hint')}")
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
    
    # Load language setting
    if "language" in config_context.config:
        translator.set_language(config_context.config["language"])

    # 3. Setup system tray icon
    setup_tray()


# if __name__ == "__main__":

#     start_qt_viewer_process()

#     #Generate a simple green square image after a delay
#     import threading
#     def push_another_image():
#         cnt = 0
#         while(True):
#             time.sleep(2)
#             print("push working")
#             dummy_image_2 = np.full((300, 300), 200, dtype=np.uint8) # Light gray
#             image_queue.put(dummy_image_2)  # Use the global image_queue for the Qt viewer
#             cnt = cnt + 1
#             if cnt > 10:
#                 break
#     threading.Thread(target=push_another_image).start()

#     while(True):
#         time.sleep(1)
