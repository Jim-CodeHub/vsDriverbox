# _*_ coding: utf-8 _*_
"""
Python wrapper for Honson shared memory client-side port (IHsAutoPrintPort_Rip.h).
Attention: the caller must correctly pair Open/Close and StartSend/StopSend or FinishSend.
"""

from ctypes import *
import ctypes
import platform
import os
import time

# -------- load dynamic library ----------
dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DLL/KMemMapRipPrint.dll')
lib = windll.LoadLibrary(dll_path)

# -------- constants ----------
SEND_SIZE_ONCE = 8 * 1024 * 1024   # 8 MB per send

# -------- function prototypes and bindings ----------

# bool IsOpendedMemMap(void)
lib.IsOpendedMemMap.argtypes = []
lib.IsOpendedMemMap.restype = c_bool

def IsOpendedMemMap():
    """Check if shared memory is already opened."""
    return lib.IsOpendedMemMap()

# int OpenAutoPrintPort_Rip(void)
lib.OpenAutoPrintPort_Rip.argtypes = []
lib.OpenAutoPrintPort_Rip.restype = c_int

def OpenAutoPrintPort_Rip():
    """Open shared memory. Returns 0 on success, negative on error."""
    return lib.OpenAutoPrintPort_Rip()

# int StartSendRipTask_Rip(void)
lib.StartSendRipTask_Rip.argtypes = []
lib.StartSendRipTask_Rip.restype = c_int

def StartSendRipTask_Rip():
    """Ready to send data to shared memory. Returns 0 on success, negative on error."""
    return lib.StartSendRipTask_Rip()

# bool IsCanSendData(uint64_t size)
lib.IsCanSendData.argtypes = [c_uint64]
lib.IsCanSendData.restype = c_bool

def IsCanSendData(size):
    """Check if printer buffer has enough free space for given size."""
    return lib.IsCanSendData(size)

# int SendDataAutoPrintPort_Rip(unsigned char *p, uint64_t size)
lib.SendDataAutoPrintPort_Rip.argtypes = [c_void_p, c_uint64]
lib.SendDataAutoPrintPort_Rip.restype = c_int

def SendDataAutoPrintPort_Rip(p, size):
    """
    Send data to shared memory.
    p    : pointer to data buffer (bytes-like object or ctypes pointer)
    size : number of bytes to send
    Returns 0 on success, negative on error.
    """
    # If p is a bytes-like object, we can use ctypes.c_void_p(ctypes.addressof(...))
    # but here we assume the caller passes a valid pointer.
    return lib.SendDataAutoPrintPort_Rip(p, size)

# uint64_t GetMemMapAllWriteSize(void)
lib.GetMemMapAllWriteSize.argtypes = []
lib.GetMemMapAllWriteSize.restype = c_uint64

def GetMemMapAllWriteSize():
    """Get total written size since last StartSendRipTask_Rip."""
    return lib.GetMemMapAllWriteSize()

# int FinishSendRipTask_Rip(void)
lib.FinishSendRipTask_Rip.argtypes = []
lib.FinishSendRipTask_Rip.restype = c_int

def FinishSendRipTask_Rip():
    """Finish data sending (after the last SendData). Returns 0 on success."""
    return lib.FinishSendRipTask_Rip()

# int StopSendRipTask_Rip(void)
lib.StopSendRipTask_Rip.argtypes = []
lib.StopSendRipTask_Rip.restype = c_int

def StopSendRipTask_Rip():
    """Stop data sending task. Returns 0 on success."""
    return lib.StopSendRipTask_Rip()

# int CloseAutoPrintPort_Rip(void)
lib.CloseAutoPrintPort_Rip.argtypes = []
lib.CloseAutoPrintPort_Rip.restype = c_int

def CloseAutoPrintPort_Rip():
    """Close shared memory. Returns 0 on success."""
    return lib.CloseAutoPrintPort_Rip()
