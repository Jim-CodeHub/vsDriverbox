# -*- coding: utf-8 -*-

import multiprocessing
import threading
import queue
import traceback
import sys

class ProcessProxy:
    """
    A proxy class that runs a given class in a separate process.
    It forwards method calls and redirects callbacks back to the main process.
    """
    def __init__(self, cls, *args, **kwargs):
        self._cls = cls
        self._args = args
        self._kwargs = kwargs
        
        # Queues for IPC
        self._cmd_queue = multiprocessing.Queue()
        self._msg_queue = multiprocessing.Queue()
        self._res_queue = multiprocessing.Queue()
        
        # Extract callbacks to be handled by the main process
        self._log_cb = kwargs.pop('log_cb', None)
        self._fatal_error_cb = kwargs.pop('fatal_error_cb', None)
        self._status_cb = kwargs.pop('status_cb', None)
        
        # Start the worker process
        self._process = multiprocessing.Process(
            target=self._run_process,
            args=(self._cmd_queue, self._msg_queue, self._res_queue, self._cls, self._args, self._kwargs),
            daemon=True
        )
        self._process.start()
        
        # Start a thread in the main process to listen for logs and status updates
        self._stop_event = threading.Event()
        self._listener_thread = threading.Thread(target=self._listen_msgs, daemon=True)
        self._listener_thread.start()

    @staticmethod
    def _run_process(cmd_queue, msg_queue, res_queue, cls, args, kwargs):
        """ The entry point for the child process. """
        
        # Define internal callbacks that forward messages to the main process
        def log_proxy(msg): msg_queue.put(('log', msg))
        def fatal_error_proxy(msg): msg_queue.put(('fatal_error', msg))
        def status_proxy(status): msg_queue.put(('status', status))
        
        # Inject the proxy callbacks back into kwargs
        kwargs['log_cb'] = log_proxy
        kwargs['fatal_error_cb'] = fatal_error_proxy
        
        # Check if status_cb is expected (Camera has it, Printer doesn't)
        if 'status_cb' in cls.__init__.__code__.co_varnames:
            kwargs['status_cb'] = status_proxy
            
        try:
            # Instantiate the actual driver class
            instance = cls(*args, **kwargs)
        except Exception as e:
            msg_queue.put(('fatal_error', f"Process initialization error in {cls.__name__}: {str(e)}\n{traceback.format_exc()}"))
            return
        
        # Command loop
        while True:
            try:
                cmd_data = cmd_queue.get(timeout=1.0)
                if cmd_data is None: 
                    # Special case: check if instance needs stopping before process exit
                    if hasattr(instance, 'stop'):
                        instance.stop()
                    break
                
                method_name, cmd_args, cmd_kwargs = cmd_data
                if hasattr(instance, method_name):
                    method = getattr(instance, method_name)
                    result = method(*cmd_args, **cmd_kwargs)
                    res_queue.put(('result', method_name, result))
                else:
                    res_queue.put(('error', method_name, f"Method {method_name} not found"))
                
            except queue.Empty:
                continue
            except Exception as e:
                msg_queue.put(('fatal_error', f"Process execution error in {cls.__name__}: {str(e)}\n{traceback.format_exc()}"))

    def _listen_msgs(self):
        """ Listens for messages from the child process and triggers local callbacks. """
        while not self._stop_event.is_set():
            try:
                msg = self._msg_queue.get(timeout=0.1)
                msg_type = msg[0]
                data = msg[1]
                
                if msg_type == 'log':
                    if self._log_cb: self._log_cb(data)
                elif msg_type == 'fatal_error':
                    if self._fatal_error_cb: self._fatal_error_cb(data)
                elif msg_type == 'status':
                    if self._status_cb: self._status_cb(data)
            except queue.Empty:
                continue
            except Exception:
                break

    def _call_method_sync(self, name, *args, **kwargs):
        """ Synchronously call a method in the child process and wait for result. """
        if not self._process.is_alive():
            return False, "Process is not running"
            
        self._cmd_queue.put((name, args, kwargs))
        try:
            # Wait for result with a timeout
            msg = self._res_queue.get(timeout=10.0)
            msg_type, method_name, result = msg
            if msg_type == 'result' and method_name == name:
                return result
            elif msg_type == 'error':
                return False, result
        except queue.Empty:
            return False, f"Method {name} timed out"

    def start(self):
        """ Forward start() call. """
        return self._call_method_sync('start')

    def stop(self, reason=None):
        """ Forward stop() call and terminate process. """
        # First call the instance's stop method
        res = self._call_method_sync('stop', reason)
        
        # Then signal the process loop to exit
        self._cmd_queue.put(None)
        self._stop_event.set()
        
        # Wait and cleanup
        self._process.join(timeout=2.0)
        if self._process.is_alive():
            self._process.terminate()
        return res

    def set_capMode(self, mode):
        """ Forward set_capMode() call (asynchronous). """
        self._cmd_queue.put(('set_capMode', (mode,), {}))

    def __getattr__(self, name):
        """ Generic forwarder for any other methods. """
        def wrapper(*args, **kwargs):
            return self._call_method_sync(name, *args, **kwargs)
        return wrapper
