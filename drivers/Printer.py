# -*- coding: utf-8 -*-
"""
    File        : Printer.py
    Brief       : TCP Printer Driver
    Author      : Jim
    Date        : 2026/5/11
    Note        : TCP data forwarding driver
"""

import socket, threading, struct, queue


class Printer(object):
    def __init__(self, 
                 listen_ip="127.0.0.1", 
                 listen_port=9111, 
                 target_ip="127.0.0.1", 
                 target_port=9100, 
                 print_length=100000, 
                 buffer_size=10240, 
                 log_cb=None,
                 fatal_error_cb=None):
        """Printer Driver Initialization

        :param listen_ip: IP to listen for incoming PRN data
        :param listen_port: Port to listen for incoming PRN data
        :param target_ip: Target printer/server IP
        :param target_port: Target printer/server Port
        :param print_length: Length of print in mm
        :param buffer_size: Buffer size in KB
        :param log_cb: Callback for logging (e.g. logger.info)
        :param fatal_error_cb: Callback for fatal errors
        """
        super().__init__()
        
        self.log_cb = log_cb
        self.fatal_error_cb = fatal_error_cb
        
        # Configuration
        self.listen_ip = listen_ip
        self.listen_port = int(listen_port)
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.print_length = int(print_length)
        self.buffer_size = int(buffer_size) * 1024 # KB to Bytes
        
        # Internal state
        self.running = False
        self.server_socket = None
        self.target_socket = None
        self.target_connected = False
        # Increase queue depth to 512, with 1MB chunk size, user-level buffer can reach 512MB
        self.forward_queue = queue.Queue(maxsize=512)
        self.index = 0

        self.HEADER_BYTE_SIZE = 48

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
        :return: True for success, False for failure
        :raises: None
        :note:: Automatically calls stop() on any failure
        """
        self.running = True
        self.index = 0
        
        # 1. Attempt to connect to target server
        if not self.target_connected:
            try:
                self.target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.target_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.target_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024 * 1024)

                self.target_socket.connect((self.target_ip, self.target_port))
                self.target_socket.settimeout(10.0)
                self.target_connected = True
                self._log(f"Connected to target server {self.target_ip}:{self.target_port}")
            except Exception as e:
                self.stop(f"Failed to connect to target server: {str(e)}")
                return False

        # 2. Attempt to start local listening service
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

            self.forward_thread = threading.Thread(target=self.forward_worker, daemon=True)
            self.forward_thread.start()
            
            return True
        except Exception as e:
            self.stop(f"Failed to start local server: {str(e)}")
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
                            self.forward_queue.put(chunk)

                        if remaining_size != 0:
                            self.stop(f"Packet #{self.index} transmission interrupted, {remaining_size} bytes remaining")
                        else:
                            self._log(f"Packet #{self.index} received successfully, queue size: {self.forward_queue.qsize()}")
                            client_socket.close() # close client socket actively

                        break

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
                
                if self.target_socket:
                    self.target_socket.sendall(chunk)
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
