# -*- coding: utf-8 -*-
"""
    File        : CamSrv.py
    Brief       : Camera TCP Data Server (Multiprocessing Receiver)
    Author      : Trae Assistant
    Date        : 2026/05/12
    Note        : Receive image data and push to multiprocessing queue
"""

import socket
import struct
import threading
import multiprocessing
import json
from datetime import datetime

import numpy as np


class CameraServer:
    def __init__(self, host = '127.0.0.1', port = 9120):
        self.host = host
        self.port = port
        
        # Image data header config (28 bytes)
        self.header_size = 28
        self.magic = 0x4D414749  # "MAGI"

        # Command data header config (16 bytes): Magic(4B) | CmdType(4B) | PayloadLen(4B) | Sequence(4B)
        self.cmd_header_size = 16
        self.cmd_magic = 0x434D4421 # "CMD!"
        
        # 1. Establish multiprocessing Queues
        self._dat_queue = multiprocessing.Queue()  # For receiving image data
        self._cmd_queue = multiprocessing.Queue()  # For sending commands to client
        
        # 2. Start process
        self._process = multiprocessing.Process(target=self._run_server, daemon=True)
        self._process.start()

    def get_queue(self):
        """Return multiprocessing queue handles: (data_queue, command_queue)

        :param: None
        :return: (multiprocessing.Queue, multiprocessing.Queue)
        :raises: None
        :note::
        """
        return self._dat_queue, self._cmd_queue

    def _run_server(self):
        """Server logic running in a separate process

        :param: None
        :return: None
        :raises: Exception
        :note::
        """
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Optimization: set large receive buffer
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024*1024)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            while self.running:
                client_sock, addr = self.server_socket.accept()
                # Optimization: each client connection also enables high-performance options
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024*1024)
                # client_sock.settimeout(15.0) # Removed timeout protection, support long connections
                
                # Start receive thread
                recv_thread = threading.Thread(
                    target=self._handle_client_recv, 
                    args=(client_sock, addr), 
                    daemon=True
                )
                recv_thread.start()

                # Start send thread
                send_thread = threading.Thread(
                    target=self._handle_client_send,
                    args=(client_sock, addr),
                    daemon=True
                )
                send_thread.start()
        except Exception as e:
            pass
        finally:
            self.server_socket.close()

    def _handle_client_recv(self, client_socket, addr):
        """Handle client data reception

        :param client_socket: socket object
        :param addr: address tuple
        :return: None
        :raises: Exception
        :note::
        """
        try:
            while self.running:
                # 1. Standard loop to read Header
                header_data = b''
                while len(header_data) < self.header_size:
                    chunk = client_socket.recv(self.header_size - len(header_data))
                    if not chunk:
                        return # Connection lost
                    header_data += chunk
                
                # Unpack Header: Magic(I), TotalSize(I), Width(I), Height(I), DataSize(I), YStep(d)
                magic, total_size, width, height, img_leng, y_step = struct.unpack('<IIIIId', header_data)
                
                if magic != self.magic:
                    break
                
                # 2. Standard loop to read image data
                img_bytes= b''
                while len(img_bytes) < img_leng:
                    # Read remaining needed length or 1MB (whichever is smaller)
                    read_size = min(img_leng - len(img_bytes), 1024 * 1024)
                    chunk = client_socket.recv(read_size)
                    if not chunk:
                        return # Connection lost
                    img_bytes += chunk
                
                img_data = np.frombuffer(img_bytes, dtype=np.uint8).reshape((height, width))

                # 3. Put data into multiprocessing queue
                # Tuple format (img_data, y_step)
                self._dat_queue.put((img_data, y_step))

        except Exception as e:
            pass
        finally:
            client_socket.close()

    def _handle_client_send(self, client_socket, addr):
        """Handle sending commands to client (Scheme 1: Fixed header + JSON)

        :param client_socket: socket object
        :param addr: address tuple
        :return: None
        :raises: Exception
        :note::
        """
        sequence = 0
        try:
            while self.running:
                try:
                    # Get command from command queue (blocking mode, with timeout)
                    import queue
                    cmd_item = self._cmd_queue.get(timeout=1.0)
                    
                    # Construct Payload (JSON)
                    if isinstance(cmd_item, dict):
                        payload = json.dumps(cmd_item).encode('utf-8')
                        cmd_type = cmd_item.get('type', 1) # Default type 1
                    elif isinstance(cmd_item, str):
                        payload = cmd_item.encode('utf-8')
                        cmd_type = 1
                    else:
                        continue
                    
                    # Construct Header: Magic(I), CmdType(I), PayloadLen(I), Sequence(I)
                    header = struct.pack('<IIII', 
                                       self.cmd_magic, 
                                       cmd_type, 
                                       len(payload), 
                                       sequence)
                    
                    client_socket.sendall(header + payload)
                    sequence = (sequence + 1) % 0xFFFFFFFF # Cyclic sequence number
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    break
        except Exception as e:
            pass
        finally:
            client_socket.close()

    def stop(self):
        """Stop server

        :param: None
        :return: None
        :raises: None
        :note::
        """
        self.running = False
        if self._process.is_alive():
            self._process.terminate()
            self._process.join()
