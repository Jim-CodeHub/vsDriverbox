# -*- coding: utf-8 -*-
"""
    File        : Printer.py
    Brief       : TCP Printer Driver
    Author      : Jim
    Date        : 2026/5/11
    Note        : TCP data forwarding driver
"""

import socket, threading, struct, queue, time, os, re


class Printer(object):
    def __init__(self, 
                 listen_mode="TCP/IP",
                 listen_ip="127.0.0.1", 
                 listen_port=9111, 
                 listen_dir="",
                 poll_interval=100,
                 forward_mode="TCP/IP",
                 target_ip="127.0.0.1", 
                 target_port=9100, 
                 print_length=100000, 
                 buffer_size=10240, 
                 target_delay=500,
                 target_timeout=5,
                 log_cb=None,
                 fatal_error_cb=None):
        """Printer Driver Initialization

        :param listen_mode: Data listening mode (TCP/IP or Hot Folder)
        :param listen_ip: IP to listen for incoming PRN data
        :param listen_port: Port to listen for incoming PRN data
        :param listen_dir: Directory to watch for hot folder mode
        :param poll_interval: Polling interval for hot folder in ms
        :param forward_mode: Forwarding mode (TCP/IP or HS DLL)
        :param target_ip: Target printer/server IP
        :param target_port: Target printer/server Port
        :param print_length: Length of print in mm
        :param buffer_size: Buffer size in KB
        :param target_delay: Delay before forwarding to target in ms
        :param target_timeout: Timeout for target server connection in seconds
        :param log_cb: Callback for logging (e.g. logger.info)
        :param fatal_error_cb: Callback for fatal errors
        """
        super().__init__()
        
        self.log_cb = log_cb
        self.fatal_error_cb = fatal_error_cb
        
        # Configuration
        self.listen_mode = listen_mode
        self.listen_ip = listen_ip
        self.listen_port = int(listen_port)
        self.listen_dir = listen_dir
        self.poll_interval = int(poll_interval) / 1000.0 # ms to seconds
        self.forward_mode = forward_mode
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.print_length = int(print_length)
        self.buffer_size = int(buffer_size) * 1024 # KB to Bytes
        self.target_delay = int(target_delay) / 1000.0 # ms to seconds
        self.target_timeout = float(target_timeout)
        
        # Internal state
        self.running = False
        self.server_socket = None
        self.target_socket = None
        self.target_connected = False
        # Increase queue depth to 512, with 1MB chunk size, user-level buffer can reach 512MB
        self.forward_queue = queue.Queue(maxsize=512)
        self.index = 0
        self.HEADER_BYTE_SIZE = 48
        
        # Hot Folder state
        self.next_expected_index = 0
        self.pending_files = {} # {index: file_path}
        self.missing_start_time = None
        self.hot_folder_thread = None

    def _log(self, msg, level="info"):
        if self.log_cb:
            self.log_cb(f"Printer: {msg}")

    def _log_error(self, msg):
        if self.log_cb:
            # We assume log_cb can handle error messages if needed, 
            # or just call it as is. Usually callers pass logger.info or similar.
            self.log_cb(f"Printer ERROR: {msg}")

    def get_prn_file_size(self, data: bytes) -> int:
        """Parse PRN file header to get total file size

        :param data: PRN file header byte data
        :return: Total file size (Header + Data)
        :raises: ValueError
        :note::
        """
        header = data[:self.HEADER_BYTE_SIZE]
        magic = int.from_bytes(header[0:4], "little")
        if magic != 0x5555:
            raise ValueError("Invalid PRN file magic number")
        bytes_per_line = int.from_bytes(header[12:16], "little")
        height = int.from_bytes(header[16:20], "little")
        channel_num = int.from_bytes(header[28:32], "little")
        header_size = self.HEADER_BYTE_SIZE
        actual_height = height * channel_num
        data_size = bytes_per_line * actual_height
        total_size = header_size + data_size
        return total_size

    def _set_header(self, data: bytes, length: int) -> bytearray:
        """Modify PRN header's printing height based on set length

        :param data: Original header bytes
        :param length: Target printing length (mm)
        :return: Modified header bytearray
        :raises: None
        :note:: Internally calculates new pixel height based on Y-DPI
        """
        header = bytearray(data[:self.HEADER_BYTE_SIZE])
        if len(header) >= 20:
            y_dpi = struct.unpack('<I', header[8:12])[0]
            new_height = int(length / (25.4 / y_dpi))
            header[16:20] = struct.pack('<I', new_height)
        return header

    def start(self):
        """Start driver: Connect to target server and start local listening service.

        :param: None
        :return: (True, None) for success, (False, error_msg) for failure
        :raises: None
        :note:: Automatically calls stop() on any failure
        """
        self.running = True
        self.index = 0
        
        # 1. Attempt to connect to target server (Only if mode is TCP/IP)
        if self.forward_mode == "TCP/IP" and not self.target_connected:
            try:
                self.target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.target_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.target_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024 * 1024)

                self.target_socket.connect((self.target_ip, self.target_port))
                self.target_socket.settimeout(self.target_timeout)
                self.target_connected = True
                self._log(f"Connected to target server {self.target_ip}:{self.target_port}")
            except Exception as e:
                err_msg = f"打印机连接失败，请检查IP和端口: {str(e)}"
                self.stop(err_msg)
                return False, err_msg
        elif self.forward_mode == "HS DLL":
            self._log("Forwarding mode set to HS DLL (Simulation mode, no TCP connection)")
            # In a real scenario, you might load a DLL here.
            self.target_connected = True

        # 2. Attempt to start local listening service
        if self.listen_mode == "TCP/IP":
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((self.listen_ip, self.listen_port))
                self.server_socket.settimeout(1.0)
                self.server_socket.listen(1)
                self._log(f"Server started, listening on {self.listen_ip}:{self.listen_port}")

                # Start core background threads
                self.accept_thread = threading.Thread(target=self.server_loop, daemon=True)
                self.accept_thread.start()
            except Exception as e:
                err_msg = f"打印转发服务启动失败，请检查端口占用: {str(e)}"
                self.stop(err_msg)
                return False, err_msg
        elif self.listen_mode == "热文件夹":
             self._log(f"Listen mode set to Hot Folder: {self.listen_dir}")
             if not os.path.exists(self.listen_dir):
                 try:
                     os.makedirs(self.listen_dir)
                 except Exception as e:
                     err_msg = f"无法创建热文件夹目录: {str(e)}"
                     self.stop(err_msg)
                     return False, err_msg
             
             self.next_expected_index = 0
             self.pending_files.clear()
             self.missing_start_time = None
             
             self.hot_folder_thread = threading.Thread(target=self.hot_folder_loop, daemon=True)
             self.hot_folder_thread.start()

         # 3. Start forward worker thread
        try:
            self.forward_thread = threading.Thread(target=self.forward_worker, daemon=True)
            self.forward_thread.start()
            
            return True, None
        except Exception as e:
            err_msg = f"转发线程启动失败: {str(e)}"
            self.stop(err_msg)
            return False, err_msg

    def hot_folder_loop(self):
        """Main loop for hot folder monitoring and sequential processing"""
        self._log("Hot folder monitor thread started")
        
        while self.running:
            try:
                # 1. Scan directory for new files
                files = os.listdir(self.listen_dir)
                prn_files = [f for f in files if f.lower().endswith('.prn')]
                
                found_higher_index = False
                
                for filename in prn_files:
                    # Extract index from filename (pure digits)
                    match = re.search(r'(\d+)', filename)
                    if match:
                        idx = int(match.group(1))
                        file_path = os.path.join(self.listen_dir, filename)
                        
                        if idx == self.next_expected_index:
                            # Found the expected file, process it
                            self._log(f"Processing expected file: {filename} (Index: {idx})")
                            self.missing_start_time = None # Reset timeout
                            
                            if self.process_hot_file(file_path):
                                # Delete file after successful processing
                                try:
                                    os.remove(file_path)
                                    self._log(f"Deleted processed file: {filename}")
                                except Exception as e:
                                    self._log_error(f"Failed to delete file {filename}: {str(e)}")
                                
                                self.next_expected_index += 1
                                # After processing one, re-scan to check pending_files in next iteration
                                break 
                        elif idx > self.next_expected_index:
                            if idx not in self.pending_files:
                                self._log(f"Found future file: {filename} (Index: {idx}), waiting for {self.next_expected_index}")
                                self.pending_files[idx] = file_path
                            found_higher_index = True
                
                # 2. Check for missing file timeout
                if found_higher_index and self.next_expected_index not in [int(re.search(r'(\d+)', f).group(1)) for f in prn_files if re.search(r'(\d+)', f)]:
                    if self.missing_start_time is None:
                        self.missing_start_time = time.time()
                        self._log(f"Started 10s timeout for missing index: {self.next_expected_index}")
                    elif time.time() - self.missing_start_time > 10.0:
                        err_msg = f"热文件夹错误：期待的打印文件编号 {self.next_expected_index} 缺失，已超时 10 秒"
                        self.stop(err_msg)
                        break
                else:
                    # If expected file is present or no higher files, reset timeout
                    self.missing_start_time = None

                # 3. Check pending_files for next expected
                if self.next_expected_index in self.pending_files:
                    # The file was previously seen, check if it still exists
                    pending_path = self.pending_files.pop(self.next_expected_index)
                    if os.path.exists(pending_path):
                        # We'll pick it up in the next scan iteration naturally
                        pass

                time.sleep(self.poll_interval)
                
            except Exception as e:
                if self.running:
                    self._log_error(f"Hot folder loop error: {str(e)}")
                time.sleep(1.0)

    def process_hot_file(self, file_path):
        """Stream a single PRN file to the forward queue"""
        try:
            with open(file_path, 'rb') as f:
                # 1. Read and parse header
                header = b''
                while len(header) < self.HEADER_BYTE_SIZE and self.running:
                    chunk = f.read(self.HEADER_BYTE_SIZE - len(header))
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    header += chunk
                
                if not self.running: return False
                
                try:
                    expected_size = self.get_prn_file_size(header)
                except Exception as e:
                    self._log_error(f"Failed to parse PRN header for {file_path}: {str(e)}")
                    return False

                self._log(f"Streaming file {os.path.basename(file_path)}, expected size: {expected_size}")
                
                # 2. Modify and send header
                self.index += 1
                if self.index == 1:
                    self.forward_queue.put(self._set_header(header, self.print_length))
                
                # 3. Stream body
                curr_pos = self.HEADER_BYTE_SIZE
                local_buffer = bytearray()
                
                while curr_pos < expected_size and self.running:
                    f.seek(curr_pos)
                    read_size = min(expected_size - curr_pos, self.buffer_size)
                    chunk = f.read(read_size)
                    
                    if not chunk:
                        # Wait for more data from RIP
                        time.sleep(0.02)
                        continue
                    
                    local_buffer.extend(chunk)
                    curr_pos += len(chunk)
                    
                    # Send in buffer_size chunks
                    while len(local_buffer) >= self.buffer_size:
                        self.forward_queue.put(bytes(local_buffer[:self.buffer_size]))
                        del local_buffer[:self.buffer_size]
                
                # Flush remaining
                if len(local_buffer) > 0 and self.running:
                    self.forward_queue.put(bytes(local_buffer))
                
                if not self.running: return False
                
                self._log(f"File {os.path.basename(file_path)} streamed successfully")
                return True
                
        except Exception as e:
            self._log_error(f"Error processing hot file {file_path}: {str(e)}")
            return False

    def server_loop(self):
        """Main listening loop, serial processing of single connection"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                self._log(f"Accepted connection from: {addr[0]}:{addr[1]}")

                try:
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024 * 1024)
                    client_socket.settimeout(10.0)

                    while self.running:
                        try:
                            header = b''
                            while len(header) < self.HEADER_BYTE_SIZE:
                                packet = client_socket.recv(self.HEADER_BYTE_SIZE - len(header))
                                if not packet:
                                    break
                                header += packet

                            if len(header) < self.HEADER_BYTE_SIZE:
                                if len(header) > 0:
                                    self.stop(f"Connection lost, header incomplete ({len(header)}/48)")
                                break
                        except Exception as e:
                            if self.running:
                                self.stop(f"Header reception exception: {str(e)}")
                            break

                        self.index += 1

                        try:
                            expected_size = self.get_prn_file_size(header)
                        except Exception as e:
                            self.stop(f"Failed to parse PRN header: {str(e)}")
                            break

                        remaining_size = expected_size - self.HEADER_BYTE_SIZE

                        if self.index == 1:
                            self.forward_queue.put(self._set_header(header, self.print_length))

                        local_buffer = bytearray()
                        while remaining_size > 0 and self.running:
                            try:
                                read_size = min(remaining_size, self.buffer_size)
                                chunk = client_socket.recv(read_size)
                            except socket.timeout:
                                self.stop(f"Reception timeout: {addr[0]}:{addr[1]}")
                                break
                            except Exception as e:
                                if self.running:
                                    self.stop(f"Body data read exception: {str(e)}")
                                break

                            if not chunk:
                                break

                            remaining_size -= len(chunk)
                            local_buffer.extend(chunk)

                            # Accumulate until buffer_size is reached
                            if len(local_buffer) >= self.buffer_size:
                                self.forward_queue.put(bytes(local_buffer))
                                local_buffer.clear()

                        # Flush remaining data in local_buffer
                        if len(local_buffer) > 0:
                            self.forward_queue.put(bytes(local_buffer))

                        if remaining_size != 0:
                            self.stop(f"Packet #{self.index} transmission interrupted, {remaining_size} bytes remaining")
                            break
                        else:
                            self._log(f"Packet #{self.index} received successfully, queue size: {self.forward_queue.qsize()}")

                            client_socket.close() # close client socket actively
                            if self.target_delay > 0:
                                time.sleep(self.target_delay)
                            break

                            #client_socket.close() # close client socket actively
                            #break
                            #接收完一个包后，到recv返回为空（客户端主动关闭socket），需要0.5秒，考虑都打印板卡缓冲负载问题，刚好使用这个时机

                except Exception as e:
                    if self.running:
                        self.stop(f"Client data processing error: {str(e)}")
                finally:
                    client_socket.close()
                    self._log(f"Connection closed: {addr[0]}:{addr[1]}, queue size: {self.forward_queue.qsize()}")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.stop(f"Main listening loop critical exception: {str(e)}")

    def forward_worker(self):
        """Background thread for forwarding data to the target server"""
        while self.running:
            try:
                # Use timeout and poison pill for graceful exit
                chunk = self.forward_queue.get(block=True, timeout=1.0)
                if chunk is None:
                    break
                
                if self.forward_mode == "TCP/IP" and self.target_socket:
                    self.target_socket.sendall(chunk)
                elif self.forward_mode == "HS DLL":
                    # DLL forwarding logic would go here
                    pass
                    
                self.forward_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    self.stop(f"Data forwarding exception to target server: {str(e)}")

    def stop(self, reason=None):
        """Stop driver: Stop listening service and disconnect from target server.

        :param reason: Reason for stopping, if provided records error and triggers fatal error handling
        :return: True for success, False for failure
        :raises: None
        :note:: Records error and triggers fatal error handling if reason is provided
        """
        self.running = False
        success = True

        # Send poison pill to wakeup and terminate forward_worker
        try:
            self.forward_queue.put(None)
        except:
            pass

        if reason:
            self._log_error(f"Abnormal stop: {reason}")
            if self.fatal_error_cb:
                self.fatal_error_cb(reason)
        
        if self.server_socket:
            try:
                self.server_socket.close()
                self.server_socket = None
            except Exception as e:
                self._log_error(f"Failed to close local server: {str(e)}")
                success = False
            
        if self.target_socket:
            try:
                self.target_socket.close()
                self.target_socket = None
                self.target_connected = False
                self._log("Disconnected from target server")
            except Exception as e:
                self._log_error(f"Failed to disconnect from target server: {str(e)}")
                success = False
        
        self._log("Driver service stopped completely")
        return success
