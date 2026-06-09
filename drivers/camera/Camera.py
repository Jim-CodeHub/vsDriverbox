# -*- coding: utf-8 -*-

"""
    File        : Camera.py
    Brief       : IKap camera driver
    Author      : Jim
    Date        : 2026/5/11
    Copyright(c):
    Note        :
"""

import ctypes, os, json, cv2, threading, socket, struct, sys, queue, time, serial, re, yaml
import serial.tools.list_ports
from datetime import datetime
import numpy as np
import drivers.camera.IKapC as IKapC
import drivers.camera.IKapCDef as IKapCDef
import drivers.camera.Charuco as Charuco
from numpy import ndarray
from dataclasses import dataclass
from PIL import Image
from pymodbus import ModbusException
from pymodbus.client import ModbusTcpClient

class Camera(object):
    r""" IKap camera driver
    """
    def __init__(self, 
                 # Base Camera Settings
                 cam_buffer_count=10,
                 data_recv_addr="127.0.0.1",
                 data_recv_port=9120,
                 capture_img_len=100.0,
                 capture_img_height=2048,
                 capture_save_dir=r"D:\vsDriverbox\cap",
                 rip_send_dir=r"D:\vsDriverbox\rip",
                 cap_line_timeout=5000,
                 cap_frame_timeout=5000,
                 dpi=300,
                 # Stitching Settings
                 stitch_left_ref=2461790,
                 stitch_right_ref=29057700,
                 img_stitch_offset=629,
                 canvas_start_pos=7906,
                 canvas_end_pos=21259,
                 overlap_offset_pix=500,
                 calib_file=r"D:\vsDriverbox\calib.yaml",
                 cal_sel="旧版",
                 # Board Settings
                 board_comm_addr="192.168.1.99",
                 board_comm_port=502,
                 board_comm_timeout=3000,
                 board_comm_retry=3,
                 # Light Settings
                 light_serial_port='COM3',
                 light_baudrate=19200,
                 light_comm_timeout=1000,
                 # Callbacks
                 log_cb=None,
                 fatal_error_cb=None,
                 status_cb=None) -> None:
        """Init IKap camera with configuration parameters

        :param log_cb: Callback for logging
        :param fatal_error_cb: Callback for fatal errors
        :param status_cb: Callback for status changes (active/idle)
        """
        super().__init__()
        
        self.log_cb = log_cb
        self.fatal_error_cb = fatal_error_cb
        self.status_cb = status_cb

        # 1. Base Camera Settings
        self.__bufferCnt = int(cam_buffer_count)
        self.data_ip = data_recv_addr
        self.data_port = int(data_recv_port)
        self.__cap_Leng = float(capture_img_len)
        self.__cap_Height = int(capture_img_height)
        self.__cap_path = capture_save_dir
        self.__cap_white_path = rip_send_dir
        self.__cap_line_timeout = int(cap_line_timeout)
        self.__cap_frame_timeout = int(cap_frame_timeout)
        self.__Image_DPI = int(dpi)
        
        # 2. Stitching Settings
        self.__canvas_width = int(canvas_end_pos)
        
        # Internal state
        self.__m_hDevice = ctypes.c_void_p(None)
        self.__m_hStream = ctypes.c_void_p(None)
        self.ReceiveBuff = ctypes.c_void_p(None)
        self.__isStarted = False
        self.__frameScnt = 0
        self.__frameOcnt = 0
        self.__frameEcnt = 0
        self.__frame_inx = 0;
        self.__JSON_Gen_ = None
        self.__cap_mode = False # Default to False, can be set if needed

        self.data_socket = None
        self.data_connected = False

        # Callback instances must be saved to prevent GC from reclaiming function pointers
        self.cb_ref_on_start_of_stream = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_start_of_stream)
        self.cb_ref_on_end_of_stream = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_end_of_stream)
        self.cb_ref_on_start_of_frame = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_start_of_frame)
        self.cb_ref_on_end_of_frame = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_end_of_frame)
        self.cb_ref_on_time_out = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_time_out)
        self.cb_ref_on_frame_lost = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_frame_lost)
        self.cb_ref_on_image_data_error = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_image_data_error)
        self.cb_ref_on_end_of_line = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_end_of_line)
        self.cb_ref_on_end_of_batch = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self.cb_on_end_of_batch)

        self.__error_check(IKapC.ItkManInitialize())


        self.running = True # AS A THREAD FLAG , SHALL BE IMPLEMENTED BEFORE ANY THREAD!

        self.__DtTQueue = queue.Queue()

        self.__MbTQueue = queue.Queue()
        self.__modbus = Camera.VisionModbus(ip=board_comm_addr, port=int(board_comm_port), timeout=int(int(board_comm_timeout)/1000.0), retries=int(board_comm_retry) )
        threading.Thread(target=self.__Mb_Thread, daemon=True).start()

        self.__StTQ_inf = queue.Queue()
        self.__StTQ_img = queue.Queue()
        self.__stitch = Camera.ImageStitch(x_base_L=int(stitch_left_ref), x_base_R=int(stitch_right_ref), x_invert=int(img_stitch_offset), canvas_start=int(canvas_start_pos), canvas_width=self.__canvas_width, DPI=self.__Image_DPI, hold_pix=int(overlap_offset_pix), YamlPath=calib_file, log_cb=self.log_cb, cal_sel=cal_sel)
        threading.Thread(target=self.__St_Thread, daemon=True).start()
        threading.Thread(target=self.__Dt_Thread, daemon=True).start()

        #self.running = True # Set after thread again

        self.__light = Camera.Illuminant(port=light_serial_port, baud=int(light_baudrate), tout=int(light_comm_timeout)/1000.0)

        self.DATA_HEADER_SIZE = 28

        self._log("Camera driver initialized")

    def _log(self, msg, level="info"):
        if self.log_cb:
            self.log_cb(f"Camera: {msg}")

    def _log_error(self, msg):
        if self.log_cb:
            self.log_cb(f"Camera ERROR: {msg}")

    def update_config(self, config: dict):
        """DEPRECATED: Configuration is now handled in __init__"""
        pass

    def generate_white_images(self):
        """Generate pure white TIFF images based on set length (in capture mode)

        :param: None
        :return: None
        :raises: Exception
        :note:: Generates white images in 50cm or 10cm segments
        """
        # Prefer rip_send_dir, fallback to capture_save_dir if not set
        save_path = self.__cap_white_path if hasattr(self, '_Camera__cap_white_path') and self.__cap_white_path and self.__cap_white_path != 'Directory not selected' else self.__cap_path

        if not save_path or save_path == 'Directory not selected':
            self._log("Error: Please select rip send directory or capture save directory first")
            return
            
        try:
            dpi_value = self.__Image_DPI
            width_px = self.__canvas_width
            
            # Calculate pixels
            _50cm_Ln_px = int(50 * 10 * dpi_value / 25.4) 
            _10cm_Ln_px = int(10 * 10 * dpi_value / 25.4) 
            
            # Get user-set total length (cm)
            try:
                total_len_cm = float(self.__cap_Leng)
            except:
                total_len_cm = 200.0 # Default 200cm
                
            total_px = int(total_len_cm * 10 * dpi_value / 25.4)
            _times, _left = divmod(total_px, _50cm_Ln_px) 
            
            h_Pix_List = [] 
            for i in range(_times): 
                h_Pix_List.append(_50cm_Ln_px) 
            
            if _left > _10cm_Ln_px: 
                h_Pix_List.append(_left) 
            
            if not h_Pix_List:
                self._log("Set length too short, no need to generate")
                return
                
            self._log(f"Starting white image generation: Total length {total_len_cm}cm, divided into {len(h_Pix_List)} segments")
            
            for idx, h in enumerate(h_Pix_List): 
                img = Image.new("RGB", (width_px, h), (255, 255, 255))  # Pure white 
                
                if len(h_Pix_List) > 1:
                    file_name = f"000_{idx+1:03d}.tif"
                else:
                    file_name = "000.tif"
                    
                file_path = os.path.join(save_path, file_name)
                img.save(file_path, dpi=(dpi_value, dpi_value), photometric="rgb")

                self._log(f"Saved: {file_name} (Height: {h}px)")

                # Keep UI responsive
                time.sleep(0.1)

            self._log(f"White image generation task completed, total {len(h_Pix_List)} images generated")
            
        except Exception as e:
            self._log(f"White image generation exception: {str(e)}")

    def get_dpi(self):
        """Get current image DPI setting"""
        return self.__Image_DPI

    def stitch_from_json(self, file_path:str, file_name:str= "LocalImageInfos.json") -> np.ndarray:
        """ Stitching images from JSON file (Wrapper)

        :param file_path: Directory containing JSON and images
        :param file_name: JSON file name
        :return: Stitched canvas as numpy array
        """
        return self.__stitch.stitch_from_json(file_path, file_name)

    def start(self):
        """Start camera: Open device, create stream, connect to data server, and start acquisition.

        :param: None
        :return: (True, None) for success, (False, error_msg) for failure
        :raises: None
        :note:: Automatically calls stop() on any failure
        """
        #try:
        #    if not self.__light.set_switch(True):
        #        return False, "灯光控制器连接失败，请检查串口或电源"
        #except Exception as e:
        #    return False, f"灯光控制器错误: {str(e)}"

        try:
            # 0. load calib yaml file
            if not self.__stitch.load_calib_yaml():
                self.stop("Yaml file is missing")
                return False, "标定文件未选定或路径错误"

            # 1. connect to modbus
            if not self.__modbus.connect():
                self.stop("Failed to connect modbus")
                return False, "PLC连接失败，请检查网线或IP设置"

            # 2. Open device
            if not self.open_device():
                self.stop("Failed to open camera device")
                return False, "相机连接失败，请检查光纤或驱动"
            
            # 3. Create stream
            if not self.create_stream():
                self.stop("Failed to create camera stream")
                return False, "相机流创建失败，请检查资源占用"
            
            # 4. Connect to data server
            if not self.connect():
                self.stop("Failed to connect to data server")
                return False, "数据服务连接失败，请检查端口占用"
            
            # 5. Start acquisition
            self.start_acq()

            # 6. Initialize JSON Generator if in capture mode
            if self.__cap_mode:
                self.Init_JSON_Gen()
                self.generate_white_images()
                self._log("Capture mode JSON generator initialized")

            self._log("Camera driver started successfully")
            return True, None
            
        except Exception as e:
            err_msg = f"相机启动异常: {str(e)}"
            self.stop(err_msg)
            return False, err_msg

    def load_config(self):
        """Load calibration configuration from YAML file.
        
        :return: True if loaded successfully, False otherwise
        """
        return self.__stitch.load_calib_yaml()

    def stop(self, reason=None):
        """Stop camera: Stop acquisition, destroy stream, disconnect, and close device.

        :param reason: Reason for stopping, if provided records error and triggers fatal error handling
        :return: True for success, False for failure
        :raises: None
        :note:: Records error and triggers fatal error handling if reason is provided
        """
        self.running = False
        success = True
        
        # Send poison pills to all queues
        for q in [self.__MbTQueue, self.__StTQ_inf, self.__StTQ_img, self.__DtTQueue]:
            try:
                q.put(None)
            except:
                pass

        if reason:
            self._log_error(f"Camera abnormal stop: {reason}")
            if self.fatal_error_cb:
                self.fatal_error_cb(reason)

        try:
            self.stop_acq()
        except Exception as e:
            self._log_error(f"Failed to stop acquisition: {str(e)}")
            success = False

        try:
            self.destroy_stream()
        except Exception as e:
            self._log_error(f"Failed to destroy stream: {str(e)}")
            success = False

        try:
            self.close_device()
        except Exception as e:
            self._log_error(f"Failed to close device: {str(e)}")
            success = False

        self.__light.set_switch(False)
        self._log("Camera driver service stopped completely")
        return success, None

    def connect(self):
        """Connect to data server

        :param: None
        :return: True for success, False for failure
        :raises: Exception
        :note:: Recommend slight delay after successful connect
        """
        if self.data_connected:
            self._log("Already connected to data server")
            return True

        try:
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024*1024*1024)
            self.data_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.data_socket.connect((self.data_ip, self.data_port))
            self.data_socket.settimeout(10.0)

            time.sleep(0.1) # Since multi-threaded socket process is already running, full-duplex TCP/IP enters recv block at connect success moment, might cause race condition where server accept cannot return

            self.data_connected = True
            self._log(f"Connected to data server {self.data_ip}:{self.data_port}")
            return True
        except Exception as e:
            self._log(f"Failed to connect to data server: {str(e)}")
            self.data_connected = False
            return False

    def disconnect(self):
        """Disconnect from data server

        :param: None
        :return: None
        :raises: None
        :note::
        """
        if self.data_socket:
            try:
                self.data_socket.close()
            except:
                pass
            self.data_socket = None
        self.data_connected = False
        self._log("Disconnected from data server")

    def open_device(self) -> bool:
        """Open (create) device

        Pre-operation of Itk device, 'Initialize', 'get device count' and 'open device'

        :param: None
        :return: True for success, False for failure
        :raises: CameraError(value)
        """

        res, num_cameras = IKapC.ItkManGetDeviceCount()
        self.__error_check(res)

        if num_cameras != 0:
            for nIndex in range(0, num_cameras, 1):
                res, dev_info = IKapC.ItkManGetDeviceInfo(nIndex)
                self.__error_check(res)

                if dev_info.DeviceClass == b'GigEVision' and dev_info.SerialNumber != b'':
                    res, gv_dev_info = IKapC.ItkManGetGigEDeviceInfo(nIndex)
                    self.__error_check(res)

                    res, self.__m_hDevice = IKapC.ItkDevOpen(nIndex, IKapCDef.ITKDEV_VAL_ACCESS_MODE_EXCLUSIVE)
                    self.__error_check(res)

                    break # Only get one instance

        return False if None == self.__m_hDevice.value or 0 == num_cameras else True

    def create_stream(self) -> bool:
        """Open (create) device and create stream

        Pre-operation of Itk device, 'Initialize', 'get device count' and 'open device'

        :param: None
        :return: True for success, False for failure
        :raises: CameraError(value)
        """
        if 0 == IKapC.ItkDevGetStreamCount(self.__m_hDevice):
            return False

        res, self.__m_hStream = IKapC.ItkDevAllocStreamEx(self.__m_hDevice, 0, self.__bufferCnt)
        self.__error_check(res)

        res, hBuffer = IKapC.ItkStreamGetBuffer(self.__m_hStream, 0)
        self.__error_check(res)

        res,bufferInfo = IKapC.ItkBufferGetInfo(hBuffer)
        self.__error_check(res)

        # Apply buffer data
        self.ReceiveBuff = ctypes.create_string_buffer(bufferInfo.ImageSize)
        if self.ReceiveBuff is None:
            return False

        res = IKapC.ItkStreamSetPrm(self.__m_hStream, IKapCDef.ITKSTREAM_PRM_START_MODE, ctypes.c_uint32(
            IKapCDef.ITKSTREAM_VAL_START_MODE_NON_BLOCK))
        self.__error_check(res)

        res = IKapC.ItkStreamSetPrm(self.__m_hStream, IKapCDef.ITKSTREAM_PRM_TRANSFER_MODE, ctypes.c_uint32(
            IKapCDef.ITKSTREAM_VAL_TRANSFER_MODE_SYNCHRONOUS_WITH_PROTECT))
        self.__error_check(res)

        res = IKapC.ItkStreamSetPrm(self.__m_hStream, IKapCDef.ITKSTREAM_PRM_TIME_OUT, ctypes.c_uint32(self.__cap_frame_timeout))
        self.__error_check(res)

        res = IKapC.ItkStreamSetPrm(self.__m_hStream, IKapCDef.ITKSTREAM_PRM_GV_PACKET_INTER_TIMEOUT, ctypes.c_uint32(self.__cap_line_timeout))
        self.__error_check(res)

        # Register stream callback
        # """
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_START_OF_STREAM, self.cb_ref_on_start_of_stream, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_STREAM, self.cb_ref_on_end_of_stream, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_START_OF_FRAME, self.cb_ref_on_start_of_frame, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_FRAME, self.cb_ref_on_end_of_frame, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_TIME_OUT, self.cb_ref_on_time_out, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_FRAME_LOST, self.cb_ref_on_frame_lost, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_IMAGE_DATA_ERROR, self.cb_ref_on_image_data_error, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_LINE, self.cb_ref_on_end_of_line, ctypes.c_void_p(None))
        IKapC.ItkStreamRegisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_BATCH, self.cb_ref_on_end_of_batch, ctypes.c_void_p(None))
        # """

        return True

    def get_features(self) -> list:
        """Get camera features

        :param: None
        :return: feature name list
        :raises: CameraError
        :note::
        """
        res, count = IKapC.ItkDevGetFeatureCount(self.__m_hDevice)
        self.__error_check(res)

        feature_list = []
        for i in range(0, count, 1):
            res, name = IKapC.ItkDevGetFeatureName(self.__m_hDevice, i)
            feature_list.append(name)

        return feature_list

    def set_feature(self):
        """Set camera feature

        :param: None
        :return: None
        :raises: None
        :note:: Placeholder
        """
        pass

    def set_capMode(self, bSwitch:bool):
        self.__cap_mode = bSwitch

    def start_acq(self) -> None:
        """Start IKap camera acquisition (Image acquisition)

        :param: None
        :return: None
        :raises: CameraError
        :note:: The acquisition thread of the camera class cannot be terminated, otherwise images cannot be acquired continuously
        """

        if self.__isStarted: return

        res = IKapC.ItkStreamStart(self.__m_hStream, IKapCDef.ITKSTREAM_CONTINUOUS)
        self.__error_check(res)

        self.__isStarted = True

    def stop_acq(self) -> None:
        """Stop IKap camera acquisition (Image acquisition)

        :param: None
        :return: None
        :raises: CameraError
        :note::
        """

        res = IKapC.ItkStreamStop(self.__m_hStream)
        self.__error_check(res)

        self.__isStarted = False

    def destroy_stream(self) -> None:
        """Destroy Itk camera stream

        :param: None
        :return: None
        :raises: CameraError
        :note::
        """
        self.disconnect()
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_START_OF_STREAM)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_STREAM)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_START_OF_FRAME)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_FRAME)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_TIME_OUT)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_FRAME_LOST)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_IMAGE_DATA_ERROR)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_LINE)
        IKapC.ItkStreamUnregisterCallback(self.__m_hStream, IKapCDef.ITKSTREAM_VAL_EVENT_TYPE_END_OF_BATCH)

        res = IKapC.ItkDevFreeStream(self.__m_hStream)
        self.__error_check(res)

    def close_device(self) -> None:
        """Close (Destroy) device

        :param: None
        :return: None
        :raises: CameraError
        :note::
        """
        if self.__m_hDevice and self.__m_hDevice.value:
            
            IKapC.ItkDevClose(self.__m_hDevice)
 
            self.__m_hDevice = ctypes.c_void_p(None)

    def terminate_manager(self) -> None:
        """Release IKap manager global resources

        :param: None
        :return: None
        :raises: None
        :note::
        """

        # Stop and clean Modbus client
        if hasattr(self, '_Camera__modbus'):
            self.__modbus.close()
        
        IKapC.ItkManTerminate()

    # 这个如何启动的话 如果对象被释放 就会被调用，但如果句柄还在呢？好像冲突了
    # def __del__(self) -> None:
    #     """Destructure
    #
    #     :param:
    #     :return:
    #     :raises:CameraError(value)
    #     """
    #     self.stop_acq()
    #     self.destroy_stream()
    #     self.close_device()
    #
    #     res = IKapC.ItkManTerminate()
    #     self.__error_check(res)

    def reset(self) -> None:
        """Reset camera state, clear all counters and queues

        :param: None
        :return: None
        :raises: None
        """
        self.__frameEcnt = 0
        self.__frameOcnt = 0
        self.__frameScnt = 0
        
        while not self.__MbTQueue.empty():
            try:
                self.__MbTQueue.get(block=False)
            except Exception:
                pass
        
        while not self.__StTQ_inf.empty():
            try:
                self.__StTQ_inf.get(block=False)
            except Exception:
                pass
        
        while not self.__StTQ_img.empty():
            try:
                self.__StTQ_img.get(block=False)
            except Exception:
                pass
        
        if hasattr(self, '_Camera__stitch') and self.__stitch is not None:
            self.__stitch.step_Reset()
        
        self._log("Camera reset completed")

    @staticmethod
    def __get_image_format(str_pixel_format:str) -> int:
        """get Itk camera image format

        :param str_pixel_format: Itk camera string image format
        :return: None or Itk camera image format
        :raises: None
        """
        _FORMAT_MAP = {
            b"Mono8": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO8,
            b"BayerGR8": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GR8,
            b"BayerRG8": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_RG8,
            b"BayerGB8": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GB8,
            b"BayerBG8": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_BG8,
            b"Mono10": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO10,
            b"Mono10Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO10PACKED,
            b"BayerGR10": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GR10,
            b"BayerRG10": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_RG10,
            b"BayerGB10": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GB10,
            b"BayerBG10": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_BG10,
            b"BayerGR10Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GR10PACKED,
            b"BayerRG10Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_RG10PACKED,
            b"BayerGB10Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_GB10PACKED,
            b"BayerBG10Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_BAYER_BG10PACKED,
            b"Mono12": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO12,
            b"Mono12Packed": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO12PACKED,
            b"Mono14": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO14,
            b"Mono16": IKapCDef.ITKBUFFER_VAL_FORMAT_MONO16,
            b"RGB8": IKapCDef.ITKBUFFER_VAL_FORMAT_RGB888,
            b"RGB10": IKapCDef.ITKBUFFER_VAL_FORMAT_RGB101010,
            b"RGB12": IKapCDef.ITKBUFFER_VAL_FORMAT_RGB121212,
            b"RGB14": IKapCDef.ITKBUFFER_VAL_FORMAT_RGB141414,
            b"RGB16": IKapCDef.ITKBUFFER_VAL_FORMAT_RGB161616,
            b"BGR8": IKapCDef.ITKBUFFER_VAL_FORMAT_BGR888,
            b"BGR10": IKapCDef.ITKBUFFER_VAL_FORMAT_BGR101010,
            b"BGR12": IKapCDef.ITKBUFFER_VAL_FORMAT_BGR121212,
            b"BGR14": IKapCDef.ITKBUFFER_VAL_FORMAT_BGR141414,
            b"BGR16": IKapCDef.ITKBUFFER_VAL_FORMAT_BGR161616,
        }
        return _FORMAT_MAP.get(str_pixel_format)

    def __error_check(self, value:int) -> None:
        """Check Itk Camera error

        :param value: Itk Camera error flag
        :return: None
        :raises: Camera.ItkCAMError(value)
        """
        if IKapCDef.ITKSTATUS_OK != value:
            raise Camera.ItkCAMError(value)

    class ItkCAMError(Exception):
        _ERROR_MAP = {
            IKapCDef.ITKSTATUS_INVALID_HANDLE: "ITKSTATUS_INVALID_HANDLE",
            IKapCDef.ITKSTATUS_INSUFFICIENT_RESOURCES: "ITKSTATUS_INSUFFICIENT_RESOURCES",
            IKapCDef.ITKSTATUS_BUFFER_TOO_SMALL: "ITKSTATUS_BUFFER_TOO_SMALL",
            IKapCDef.ITKSTATUS_MISSING_RESOURCE: "ITKSTATUS_MISSING_RESOURCES",
            IKapCDef.ITKSTATUS_UNINITIALIZE: "ITKSTATUS_UNINITIALIZE",
            IKapCDef.ITKSTATUS_DEVICE_ID_OUTOF_RANGE: "ITKSTATUS_DEVICE_ID_OUTOF_RANGE",
            IKapCDef.ITKSTATUS_SERAIL_PORT_NOT_AVAILABLE: "ITKSTATUS_SERAIL_PORT_NOT_AVAILABLE",
            IKapCDef.ITKSTATUS_XML_NOT_FOUND: "ITKSTATUS_XML_NOT_FOUND",
            IKapCDef.ITKSTATUS_DEVICE_NOT_ACCESSABLE: "ITKSTATUS_DEVICE_NOT_ACCESSABLE",
            IKapCDef.ITKSTATUS_DEVICE_PERMISSION_DENY: "ITKSTATUS_DEVICE_PERMISSION_DENY",
            IKapCDef.ITKSTATUS_REGISTRY_NOT_FOUND: "ITKSTATUS_REGISTRY_NOT_FOUND",
            IKapCDef.ITKSTATUS_XML_PARSE_ERROR: "ITKSTATUS_XML_PARSE_ERROR",
            IKapCDef.ITKSTATUS_INVALID_ARG: "ITKSTATUS_INVALID_ARG",
            IKapCDef.ITKSTATUS_INVALID_NAME: "ITKSTATUS_INVALID_NAME",
            IKapCDef.ITKSTATUS_INCOMPATIBLE_FEATURE_TYPE: "ITKSTATUS_INCOMPATIBLE_FEATURE_TYPE",
            IKapCDef.ITKSTATUS_TIME_OUT: "ITKSTATUS_TIME_OUT",
            IKapCDef.ITKSTATUS_COMMAND_CRASH: "ITKSTATUS_COMMAND_CRASH",
            IKapCDef.ITKSTATUS_COMMAND_PARAM_OUT_OF_RANGE: "ITKSTATUS_COMMAND_PARAM_OUT_OF_RANGE",
            IKapCDef.ITKSTATUS_COMMAND_NOT_ALLOW: "ITKSTATUS_COMMAND_NOT_ALLOW",
            IKapCDef.ITKSTATUS_COMMAND_NOT_PRASE: "ITKSTATUS_COMMAND_NOT_PRASE",
            IKapCDef.ITKSTATUS_COMMAND_PENDING: "ITKSTATUS_COMMAND_PENDING",
            IKapCDef.ITKSTATUS_ARG_OUT_OF_RANGE: "ITKSTATUS_ARG_OUT_OF_RANGE",
            IKapCDef.ITKSTATUS_NOT_IMPLEMENT: "ITKSTATUS_NOT_IMPLEMENT",
            IKapCDef.ITKSTATUS_NO_MEMORY: "ITKSTATUS_NO_MEMORY",
            IKapCDef.ITKSTATUS_INCOMPATIBLE_ARG_TYPE: "ITKSTATUS_INCOMPATIBLE_ARG_TYPE",
            IKapCDef.ITKSTATUS_STREAM_IN_PROCESS: "ITKSTATUS_STREAM_IN_PROCESS",
            IKapCDef.ITKSTATUS_PRM_READ_ONLY: "ITKSTATUS_PRM_READ_ONLY",
            IKapCDef.ITKSTATUS_STREAM_IS_OPENED: "ITKSTATUS_STREAM_IS_OPENED",
            IKapCDef.ITKSTATUS_SYSTEM_ERROR: "ITKSTATUS_SYSTEM_ERROR",
            IKapCDef.ITKSTATUS_INVALID_ADDRESS: "ITKSTATUS_INVALID_ADDRESS",
            IKapCDef.ITKSTATUS_BAD_ALIGNMENT: "ITKSTATUS_BAD_ALIGNMENT",
            IKapCDef.ITKSTATUS_DEVICE_BUSY: "ITKSTATUS_DEVICE_BUSY",
            IKapCDef.ITKSTATUS_DEVICE_IS_REMOVED: "ITKSTATUS_DEVICE_IS_REMOVED",
            IKapCDef.ITKSTATUS_DEVICE_NOT_FOUND: "ITKSTATUS_DEVICE_NOT_FOUND",
            IKapCDef.ITKSTATUS_BOARD_IS_OPENED: "ITKSTATUS_BOARD_IS_OPENED",
            IKapCDef.ITKSTATUS_BOARD_NO_OPENED: "ITKSTATUS_BOARD_NO_OPENED",
            IKapCDef.ITKSTATUS_PRM_WRITE_ONLY: "ITKSTATUS_PRM_WRITE_ONLY",
            IKapCDef.ITKSTATUS_BOARD_CONNECTION_FAIL: "ITKSTATUS_BOARD_CONNECTION_FAIL",
            IKapCDef.ITKSTATUS_RUNTIME_ERROR: "ITKSTATUS_RUNTIME_ERROR",
            IKapCDef.ITKSTATUS_IO_ERROR: "ITKSTATUS_IO_ERROR",
            IKapCDef.ITKSTATUS_BUFFER_OVERFLOW: "ITKSTATUS_BUFFER_OVERFLOW",
            IKapCDef.ITKSTATUS_COMMUNICATION_ERROR: "ITKSTATUS_COMMUNICATION_ERROR",
            IKapCDef.ITKSTATUS_CXP_CONTROL_CRC_ERROR: "ITKSTATUS_CXP_CONTROL_CRC_ERROR",
            IKapCDef.ITKSTATUS_ACK_ID_NOT_COMPATIABLE: "ITKSTATUS_ACK_ID_NOT_COMPATIABLE",
            IKapCDef.ITKSTATUS_DEV_INVALID_HEADER: "ITKSTATUS_DEV_INVALID_HEADER",
            IKapCDef.ITKSTATUS_DEV_DSI_ENDPOINT_HALTED: "ITKSTATUS_DEV_DSI_ENDPOINT_HALTED",
            IKapCDef.ITKSTATUS_DEV_DEI_ENDPOINT_HALTED: "ITKSTATUS_DEV_DEI_ENDPOINT_HALTED",
            IKapCDef.ITKSTATUS_DEV_DATA_DISCARDED: "ITKSTATUS_DEV_DATA_DISCARDED",
            IKapCDef.ITKSTATUS_DEV_DATA_OVERRUN: "ITKSTATUS_DEV_DATA_OVERRUN",
            IKapCDef.ITKSTATUS_STREAM_ABORTED: "ITKSTATUS_STREAM_ABORTED",
            IKapCDef.ITKSTATUS_DRIVER_NOT_MATCH: "ITKSTATUS_DRIVER_NOT_MATCH",
            IKapCDef.ITKSTATUS_DEVICE_WRONG_USB_PORT: "ITKSTATUS_DEVICE_WRONG_USB_PORT",
            IKapCDef.ITKSTATUS_DEVICE_IS_FAULTY: "ITKSTATUS_DEVICE_IS_FAULTY",
        }

        def __init__(self, value):
            self.string = self._ERROR_MAP.get(value, "Other errors")
            super().__init__(self.string)

    def cb_on_start_of_stream(self, p_param):
        self._log("Camera stream started")
        if self.status_cb:
            self.status_cb(True)

    def cb_on_end_of_stream(self, p_param):
        self._log("Camera stream ended")
        if self.status_cb:
            self.status_cb(False)
    def cb_on_start_of_frame(self, p_param):
        self._log(f"Camera frame started [{self.__frameScnt}]")
        self.__frameScnt+=1
        self.__MbTQueue.put(True)

    def cb_on_end_of_frame(self, p_param):
        try:
            res, hBuffer = IKapC.ItkStreamGetCurrentBuffer(self.__m_hStream)
            self.__error_check(res)

            res, bufferInfo = IKapC.ItkBufferGetInfo(hBuffer)
            self.__error_check(res)
            bufferStatus = bufferInfo.State

            if bufferStatus == IKapCDef.ITKBUFFER_VAL_STATE_FULL:
                bufferSize = bufferInfo.ImageSize
                res = IKapC.ItkBufferRead(hBuffer, 0, self.ReceiveBuff, bufferSize)
                self.__error_check(res)

                image = np.frombuffer(ctypes.string_at(self.ReceiveBuff, bufferSize), dtype=np.uint8).reshape((bufferInfo.ImageHeight, bufferInfo.ImageWidth)).copy()

                self._log(f"Camera frame ended [{self.__frameOcnt}]")
                self.__frameOcnt += 1

                self.__StTQ_img.put(image)
            else:
                self.stop(f"Camera buffer status error: {str(bufferStatus)}")

        except Exception as e:
            self._log_error(f"Frame callback error: {str(e)}")

    def cb_on_time_out(self, p_param): self.stop("Camera timeout")
    def cb_on_frame_lost(self, p_param): self.stop("Camera frame lost")
    def cb_on_image_data_error(self, p_param): self.stop("Camera image data error")
    def cb_on_end_of_line(self, p_param): self._log("Camera end of line")
    def cb_on_end_of_batch(self, p_param): self._log("Camera end of batch")

    def __St_Thread(self):
        infoList = []
        while self.running:
            try:
                _Info2 = self.__StTQ_inf.get(block=False)
                if _Info2 is None: break
                infoList.append(_Info2)
            except queue.Empty:
                pass # shall be pass here
            except Exception as e:
                if self.running:
                    self.stop(f"Stitch thread exception3: {str(e)}")
                break

            try:
                image = self.__StTQ_img.get(block=True, timeout=1.0)
                if image is None: break

                if not infoList:
                    if self.running:
                        self.stop(f"Stitch thread exception4: infoList is empty")
                    break

                _Info = infoList.pop(0)
                if self.__cap_mode:
                    img_path = self.__JSON_Gen_.generate_json(y_steps=_Info["Step"], direction=_Info["Direction"], x_pos=_Info["MotionStartPoint"])
                    Image.fromarray(image).save(img_path, dpi=(self.__Image_DPI, self.__Image_DPI))

                    self._log(f"Cap mode Image saved[{self.__frameEcnt}], path={img_path}")
                    self.__frameEcnt += 1
                else:
                    self._log(f"Stitching...image={image.shape}, Step={_Info['Step']}, Direction={_Info['Direction']}, MotionStartPoint={_Info['MotionStartPoint']} ")

                    fresh, y_step = self.__stitch.stitch_from_ram(_image=image, Step=_Info["Step"], Direction=_Info["Direction"], MotionStartPoint=_Info["MotionStartPoint"])

                    # if 0 == self.__frame_inx:
                    #     self.__DtTQueue.put((self.__stitch.get_addons(), 834))
                    #
                    # self.__frame_inx += 1

                    self.__DtTQueue.put((fresh.copy(), y_step))
                self.__StTQ_inf.task_done()
                self.__StTQ_img.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    self.stop(f"Stitch thread exception: {str(e)}")
                break

    def __Mb_Thread(self):
        while self.running:
            try:
                _Sig_ = self.__MbTQueue.get(block=True, timeout=1.0)
                if _Sig_ is None: break

                time.sleep(0.1) # DO SOME DELAY HERE FOR PLC DATA UPDATE

                self.__modbus.get_info()

                self.__StTQ_inf.put({"Step":self.__modbus.y_axis_pos(), "Direction":self.__modbus.is_right_to_left(), "MotionStartPoint":self.__modbus.x_axis_pos()})
                self.__MbTQueue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    self.stop(f"Modbus thread exception: {str(e)}")
                break

    def __Dt_Thread(self):
        while self.running:
            try:
                _Data_ = self.__DtTQueue.get(block=True, timeout=1.0)
                if _Data_ is None: break
                _Img_, y_step = _Data_

                if self.data_connected and self.data_socket:
                    try:
                        height, width = _Img_.shape[:2]
                        img_data = _Img_.tobytes()
                        img_leng = len(img_data)
                        
                        # Pack Header: Magic(I), TotalSize(I), Width(I), Height(I), DataSize(I), YStep(d)
                        header = struct.pack('<IIIIId', 
                                           0x4D414749, 
                                           self.DATA_HEADER_SIZE + img_leng, 
                                           width, 
                                           height, 
                                           img_leng, 
                                           y_step)
                        
                        self.data_socket.sendall(header + img_data)

                        self._log(f"Camera send ended [{self.__frameEcnt}] (Size: {width}x{height}), ({y_step} steps)")
                        self.__frameEcnt += 1
                    except Exception as e:
                        if self.running:
                            self.stop(f"Failed to send image data: {str(e)}")

                self.__DtTQueue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    self.stop(f"Data thread exception: {str(e)}")
                break

    def __Cm_Thread(self):
        pass

    def Init_JSON_Gen(self): self.__JSON_Gen_ = Camera.JsonGenerator(self.__cap_path)

    class ImageStitch(object):
        r""" Stitching image from JSON or ram

        Example:
            image_stitch = ImageStitch()
        """

        @dataclass
        class JsonInfo(object):
            ImagePath: str
            Step: float
            Direction: bool
            MotionStartPoint: float

        def __init__(self, x_base_L:int = 2461790, x_base_R:int = 29057700, x_invert:int = 629, canvas_start = 7906, canvas_width:int = 21259, DPI:int = 300, hold_pix:int=500, YamlPath=None, log_cb=None, cal_sel="旧版") -> None:
            """ ImageStitch init
            :param x_base_L: X left base position
            :param x_base_R: X right base position
            :param x_invert: X axis invert offset, unit pixel, measured with ps (Reverse offset value may change if print parameters change)
            :param canvas_start: canvas start position
            :param canvas_width: width of canvas
            :param DPI: image DPI
            :param hold_pix: Offset pixels upwards to avoid light source dimming area, Note: do not exceed overlap pixels
            :param YamlPath: YAML path for calib
            :param log_cb: log callback
            :param cal_sel: calibration selection ("旧版" or "新版")
            :return:None
            :raises None
            :note : Yaml file SHALL BE loaded (by load_calib_yaml()) before any stitch function used
            """
            self.__K_Coef__ = (25.4 / DPI) * 10000.0
            self.__x_base_L = int(x_base_L / self.__K_Coef__)
            self.__x_base_R = int(x_base_R / self.__K_Coef__)
            self.__x_invert = x_invert
            self.__x_s_cut_ = canvas_start
            self.__x_e_cut_ = canvas_start + canvas_width

            self.__add_ons_ = []
            self.__upOffset = hold_pix

            self.__YamlPath = YamlPath
            self.__log_cb = log_cb

            self.__StepCopy = 0

            self.__params = None

            self.__calsel = True if cal_sel == "新版" else False

        def load_calib_yaml(self) -> bool:
            if self.__YamlPath and os.path.exists(self.__YamlPath):
                try:
                    if self.__calsel:
                        # Use the new Charuco module Calibration model
                        self.__params = Charuco.Calibration.from_yaml(self.__YamlPath)
                    else:
                        with open(self.__YamlPath, 'r', encoding='utf-8') as f:
                            self.__params = yaml.safe_load(f)
                    return True
                except Exception as e:
                    return False

            return False

        def calibration(self, img, params):
            """Rectify image using Charuco calibration parameters

            :param img: numpy array image
            :param params: Charuco.Calibration object
            :return: numpy.ndarray (Grayscale)
            :raises: 
            :note:: Only supports new Charuco calibration
            """
            if self.__calsel:
                return Charuco.calibration(img, params)
            else:
                return Charuco.calibration_origin(img, params)

        def _stitch_unit(self, image:np.ndarray, overlap:int, direction:bool, start_pos:int) -> ndarray:
            """ Stitching image to canvas
            :param image: first/previous image
            :param overlap: Y axis overlap (unit:pixel)
            :param direction: True for Left->Right and False for invert
            :param start_pos: X axis start position (unit:pixel)
            :return: fresh image, in type 'np.ndarray'
            :raises None
            :notes: X axis direction
            """

            """------------------------------------------------------------------- X axis handler --------------------------------------------------------"""

            alignment = start_pos - (self.__x_base_L if direction else self.__x_base_R)

            if alignment < 0:
                _image_ = np.pad( image [:,               :image.shape[1]-abs(alignment)], ((0, 0), (abs(alignment), 0)), mode='constant', constant_values=0)
            else:
                _image_ = np.pad( image [:, abs(alignment):                             ], ((0, 0), (0, abs(alignment))), mode='constant', constant_values=0)

            if not direction:
                _image_ = np.pad(_image_[:, self.__x_invert:], ((0, 0), (0, self.__x_invert)), mode='constant', constant_values=0)

            """---------------------------------------------------------------------- Cut Width ----------------------------------------------------------"""

            _image_ = _image_[:, self.__x_s_cut_:self.__x_e_cut_]

            """------------------------------------------------------------------- Y axis handler --------------------------------------------------------"""

            fresh = _image_[overlap-self.__upOffset:_image_.shape[0] - self.__upOffset, :]

            """------------------------------------------------------------------- Y axis handler --------------------------------------------------------"""
            if 0 == self.__StepCopy:
                self.__add_ons_.append(_image_[overlap - self.__upOffset - 834:overlap - self.__upOffset, :].copy())

            return fresh

        def stitch_from_ram(self, _image:np.ndarray, Step:float, Direction:bool, MotionStartPoint:float) -> (np.ndarray, int):
            """ Stitching images from ram
            :param _image: image to stitch
            :param Step: Y axis steps
            :param Direction: true or false (Left to Right or Right to Left)
            :param MotionStartPoint: X axis position
            :return: fresh image (in type 'np.ndarray') and Y step forward (in pix)
            :raises Exception on error
            :notes: This function automatically saves the step data from the previous stitching
            """
            t_start = time.perf_counter()
            _image_ = self.calibration(_image, self.__params) if Direction else self.calibration(_image[::-1, ...], self.__params)
            t_end = time.perf_counter()

            if self.__log_cb:
                self.__log_cb(f"Camera: Calibration cost: {(t_end - t_start) * 1000:.2f}ms")
            
            forward = round((Step - self.__StepCopy) / self.__K_Coef__)

            fresh = self._stitch_unit(_image_, _image_.shape[0] - forward, Direction, round(MotionStartPoint / self.__K_Coef__))

            self.__StepCopy = Step

            return fresh.copy(), forward

        def stitch_from_json(self, file_path:str, file_name:str= "LocalImageInfos.json") -> np.ndarray:
            """ Stitching images from JSON file
            :param file_path:
            :param file_name:
            :return: canvas in type 'np.ndarray'
            :raises Exception on error
            :notes: The file is a List JSON and at least one image
            """

            self.__StepCopy = 0

            with open(os.path.join(file_path, file_name), 'r', encoding='utf-8') as f:
                file = json.load(f)

            image_List = []
            for _, item in enumerate(file):
                Info = item["Info"]

                _Info = self.JsonInfo( ImagePath=item["ImagePath"], Step=Info["Step"], Direction=Info["Direction"], MotionStartPoint=Info["MotionStartPoint"])

                with Image.open(os.path.join(file_path, _Info.ImagePath)) as img:
                    _image_ = np.array(img)

                    _image, _ = self.stitch_from_ram(_image=_image_, Step=_Info.Step, Direction=_Info.Direction, MotionStartPoint=_Info.MotionStartPoint)
                    image_List.append(_image)

            return np.vstack(image_List)

        def set_L_base(self, base): self.__x_base_L = int(base / self.__K_Coef__)
        def set_R_base(self, base): self.__x_base_R = int(base / self.__K_Coef__)
        def set_Invert(self, invt): self.__x_invert = invt
        def set_YmPath(self, path): self.__YamlPath = path
        def step_Reset(self)      : self.__StepCopy = 0
        def get_addons(self      ): return self.__add_ons_.pop(0)

    class VisionModbus(object):
        r"""
            Example:
                client = VisionModbus()
                client.start()
                ...
                client.stop()
        """
        def __init__(self, ip: str="192.168.1.99", port: int=502, timeout: int=3, retries: int = 3) -> None:
            """
            :param ip:
            :param port:
            :param timeout: for tcp/ip server connection
            :param retries: retry times
            :raises Exception: on error
            """
            super().__init__()

            self.ip = ip
            self.port = port
            self.timeout = timeout
            self.retries = retries

            self.YaxisPosition      = 0.0000
            self.XaxisPosition      = 0.0000

            self.StatusPrint        = 0
            self.StatusDirection    = 0
            self.StatusEmergency    = 0
            self.StatusRipFormat    = 0
            self.StatusTrigger      = 0

            self.__client__ = ModbusTcpClient(self.ip, port=self.port, timeout=self.timeout, retries=self.retries)

        def close(self):
            """Close Modbus client connection

            :param: None
            :return: None
            :raises: None
            :note::
            """
            try:
                if self.__client__:
                    self.__client__.close()
            except:
                pass

        def connect(self):              return self.__client__.connect()

        def is_print(self):             return self.StatusPrint == 1
        def is_right_to_left(self):     return self.StatusDirection == 1
        def is_emergency(self):         return self.StatusEmergency == 1
        def is_triggered(self):         return self.StatusTrigger == 1
        def x_axis_pos(self):           return self.XaxisPosition*10000
        def y_axis_pos(self):           return self.YaxisPosition*10000


        def send_pause(self, pause:bool) -> bool:
            """ Send pause to server to stop machine

            :param pause: True or False
            :return: True or False
            :raises: ModbusException
            :note:: 0x8000 pause, restart needs manual continue. If not restored to 0, shows 'peripheral panel forbidden printing', 0x0000 allows printing, but doesn't have continue printing function
            """
            if self.__client__.connect():
                result = self.__client__.write_registers(192, values=[0x8000] if pause else [0], slave=0)

                return not result.isError()
            return False

        def get_info(self) -> bool:
            """ Get Modbus info

            :param: None
            :return: True or False
            :raises: ModbusException
            :note:: Use 'List' function or attribute to get certain data, after the function called
            """
            if self.__client__.connect():
                result = self.__client__.read_holding_registers(180, count=4, slave=0)  # 180&181 For X axis pos, 182&183 For Y axis pos

                if not result.isError():
                    data = self.__client__.convert_from_registers(result.registers, self.__client__.DATATYPE.FLOAT32, "little")

                    self.XaxisPosition = data[0]
                    self.YaxisPosition = data[1]
                else:
                    return False

                result = self.__client__.read_holding_registers(190, count=1, slave=0)  # 190 For Machine status

                if not result.isError():
                    bits = [(result.registers[0] >> i) & 1 for i in range(16)]

                    self.StatusPrint    = bits[15]
                    self.StatusDirection= bits[14]
                    self.StatusEmergency= bits[13]
                    self.StatusRipFormat= bits[12]
                    self.StatusTrigger  = bits[11]
                else:
                    return False

                return True
            return False

    class JsonGenerator(object):
        r""" Generate JSON for 'Step and Repeat', with certain format

        Example:
            json_generator = JsonGenerator(r'C:\Users\Jim\Desktop')
            json_generator.generate_json(y_steps=0.0, direction=True, x_pos=0.0)

        Note : Every time 'JsonGenerator' is called, it will generate a JSON file
        """
        def __init__(self, save_pathname: str) -> None:
            self.datetime_pathname = os.path.join(save_pathname, datetime.now().strftime('%Y%m%d%H%M%S'))

            os.makedirs(self.datetime_pathname, exist_ok=True)

            self.Image_path = 'Images'

            self.Img_save_pathname = os.path.join(self.datetime_pathname, self.Image_path)

            os.makedirs(self.Img_save_pathname, exist_ok=True)

            self.index : int = 0

        def _auto_image_pathname(self) -> str:
            pathname = os.path.join(self.Image_path, str(self.index)+'.tif')

            self.index += 1

            return pathname

        def generate_json(self, y_steps: float, direction: bool, x_pos: float) -> str:
            """ Create or append json file info

            :param y_steps: Y-axis steps
            :param direction: true or false (Left to Right or Right to Left)
            :param x_pos: X-axis position
            :return: current image save pathname
            :raises Exception on error
            :notes:
            """

            info = {'Step': y_steps, 'Direction': direction, 'MotionStartPoint': x_pos}
            _img = {"ImagePath": self._auto_image_pathname(), "Info": info}

            file_pathname = os.path.join(self.datetime_pathname, "LocalImageInfos.json")

            if os.path.exists(file_pathname) and os.path.isfile(file_pathname):
                with open(file_pathname, 'r', encoding='utf-8') as f:
                    file = json.load(f)

                file.append(_img)
            else:
                file = [_img]

            file = json.dumps(file, indent=4, separators=(',', ': '))

            with open(file_pathname, 'w', encoding='utf-8') as f:
                f.write(file)

            return os.path.join(self.datetime_pathname, _img['ImagePath'])

    class Illuminant:
        r"""Camera illuminant operator
            Example:
                light = Illuminant()
                light.set_port('COM3') # Can be selected from 'Illuminant.scan_serial_ports()'
                try:
                    light.set_brightness(50)
                except SerialException as e:
                    ...
        """

        def __init__(self, port: str = 'COM3', baud: int = 19200, tout: float = 0.1):
            """Set serial port, baudrate and timeout

            :param port: serial port
            :param baud: baudrate
            :param tout: timeout

            .. note::
                - function set_port(), set_baud(), set_tout() can be called after initialization
            """
            self.port = port
            self.baud = baud
            self.tout = tout

        def set_port(self, port: str): self.port = port
        def set_baud(self, baud: int): self.baud = baud
        def set_tout(self, tout: float): self.tout = tout

        def set_brightness(self, brightness: int) -> bool:
            """Set brightness of light.

            :param brightness: 0 ~ 100
            :return: False when timeout without right response or True
            :raises SerialException when serial port open error.
            """
            cmd = '$'
            cmd += 'S'
            cmd += 'A'
            cmd += f'{brightness:03d}'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(4).decode('utf-8')
                ser.close()

                return False if data is None or data != '$OK#' or data == '$NG#' else True

        def get_brightness(self) -> (bool, list):
            """Get brightness of light.

            :param:
            :return: False when timeout without right response or True, and brightness
            :raises SerialException when serial port open error.
            .. note::
                - Use int(return_value[0]) trans to int, if return True
            """
            cmd = '$'
            cmd += 'S'
            cmd += 'A'
            cmd += 'R'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(7).decode('utf-8')
                ser.close()

                return False if data is None or not re.match(r'^\$SA\d{3}#$', data) else True, re.findall(r'\d+', data)

        def set_strobe(self, strobe: int) -> bool:
            """Set strobe of light.

            :param strobe: strobe value (ms), 0 ~ 999
            :return: False when timeout without right response or True
            :raises SerialException when serial port open error.
            """
            cmd = '$'
            cmd += 'D'
            cmd += 'A'
            cmd += f'{strobe:03d}'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(4).decode('utf-8')
                ser.close()

                return False if data is None or data != '$OK#' or data == '$NG#' else True

        def get_strobe(self) -> (bool, list):
            """Get strobe of light.

            :param:
            :return: False when timeout without right response or True, and strobe value
            :raises SerialException when serial port open error.
            .. note::
                - Use int(return_value[0]) trans to int, if return True
            """
            cmd = '$'
            cmd += 'D'
            cmd += 'A'
            cmd += 'R'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(7).decode('utf-8')
                ser.close()

                return False if data is None or not re.match(r'^\$DA\d{3}#$', data) else True, re.findall(r'\d+', data)

        def set_voltage(self, level: bool) -> bool:
            """Set the voltage of light.

            :param level: True for High and False for Low
            :return: False when timeout without right response or True
            :raises SerialException when serial port open error.
            """
            cmd = '$'
            cmd += 'T'
            cmd += 'H' if True == level else 'L'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(4).decode('utf-8')
                ser.close()

                return False if data is None or data != '$OK#' or data == '$NG#' else True

        def get_voltage(self) -> (bool, list):
            """Get voltage of light.

            :param:
            :return: False when timeout without right response or True, and voltage value (['H'] or ['L'])
            :raises SerialException when serial port open error.
            .. note::
                - Use return_value[0] to check level, if return True
            """
            cmd = '$'
            cmd += 'T'
            cmd += 'R'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(4).decode('utf-8')
                ser.close()

                return False if data is None or not re.match(r'^\$(TL|TH)#$', data) else True, re.findall(r'T([LH])',
                                                                                                          data)

        def set_switch(self, switch: bool) -> bool:
            """Set switch of light.

            :param switch: True for On and False for Off
            :return: False when timeout without right response or True
            :raises SerialException when serial port open error.
            """
            cmd = '$'
            cmd += 'W'
            cmd += 'A'
            cmd += 'N' if True == switch else 'F'
            cmd += '#'
            try:
                serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout)
            except serial.SerialException:
                pass #这样才不会报错
            # with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
            #     ser.write(cmd.encode('utf-8'))
            #     data = "0"
            #     #data = ser.read(4).decode('utf-8')
            #     #ser.close()
            #
            #     return False if data is None or data != '$OK#' or data == '$NG#' else True

        def get_switch(self) -> (bool, list):
            """Get switch of light.

            :param:
            :return: False when timeout without right response or True, and switch value (['N'] or ['F'])
            :raises SerialException when serial port open error.
            .. note::
                - Use return_value[0] to check switch, if return True
            """
            cmd = '$'
            cmd += 'W'
            cmd += 'A'
            cmd += 'R'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(5).decode('utf-8')
                ser.close()

                return False if data is None or not re.match(r'^\$(WAN|WAF)#$', data) else True, re.findall(r'WA([NF])',
                                                                                                            data)

        def factory_reset(self) -> bool:
            """Reset to factory mode.

            :param:
            :return: False when timeout without right response or True
            :raises SerialException when serial port open error.
            """
            cmd = '$'
            cmd += 'REC'
            cmd += '#'

            with serial.Serial(port=self.port, baudrate=self.baud, timeout=self.tout) as ser:
                ser.write(cmd.encode('utf-8'))
                data = ser.read(4).decode('utf-8')
                ser.close()

                return False if data is None or data != '$OK#' or data == '$NG#' else True

        @staticmethod
        def scan_serial_ports() -> list:
            """Scan serial ports

            :param: None
            :return: Serial ports list
            :raises None
            """
            ports = serial.tools.list_ports.comports()

            available_ports = []
            for port in ports:
                available_ports.append(port.device)

            return available_ports
