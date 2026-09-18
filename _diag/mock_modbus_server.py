# -*- coding: utf-8 -*-
"""mock_modbus_server.py — 本地 Modbus TCP 模拟板卡，用于端到端验证 VisionModbus 修复。

寄存器布局与真实板卡一致（Camera.VisionModbus 的口径）：
  180-183 : FLOAT32 x2, little-endian —— X 轴位置, Y 轴位置
  190     : 机器状态位（bit15=打印中, bit14=方向, bit13=急停, bit12=RIP格式, bit11=触发）
  192     : 暂停寄存器（0x8000=暂停, 0x0000=允许打印）
"""
import struct
import threading
import time

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartTcpServer, ServerStop

HOST = "127.0.0.1"
PORT = 15020  # >1024, 随便挑一个不冲突的

# 模拟值：X=1.25, Y=-2.5（单位：0.0001mm 的基准值，VisionModbus 里再 *10000）
X_POS, Y_POS = 1.25, -2.5
regs_180 = list(struct.unpack("<4H", struct.pack("<ff", X_POS, Y_POS)))
STATUS_190 = 0xC000          # bit15=1 打印中, bit14=1 (right->left)
PAUSE_192 = 0

# 一整段连续块：180..192 全覆盖（中间的 184-189 填 0）
values = regs_180 + [0] * 6 + [STATUS_190] + [0] + [PAUSE_192]
assert len(values) == 13 and 180 + len(values) - 1 == 192

context = ModbusServerContext(
    devices=ModbusDeviceContext(
        # pymodbus 3.14 的 SequentialDataBlock 内部把起始地址存成 address-1，
        # 即客户端地址 A 取 values[A-start+1]。要让客户端 180 读到 values[0]，
        # start 必须写 181。
        hr=ModbusSequentialDataBlock(181, values)
    ),
    single=True,  # 任意 device_id 都路由到同一份 context（含 0）
)

server_thread = threading.Thread(
    target=StartTcpServer,
    kwargs={"context": context, "address": (HOST, PORT)},
    daemon=True,
)
server_thread.start()
time.sleep(1.0)

print(f"[mock] Modbus TCP server on {HOST}:{PORT}, X={X_POS}, Y={Y_POS}, status=0x{STATUS_190:04X}")

# ------------------------------------------------------------------
# 用【真实的】Camera.VisionModbus 走完整链路
# ------------------------------------------------------------------
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drivers.camera.Camera import Camera, _MODBUS_ID

print(f"[test] resolved Modbus id kwarg: {_MODBUS_ID}")
assert _MODBUS_ID.get("device_id") == 0, f"unexpected kwarg: {_MODBUS_ID}"

vm = Camera.VisionModbus(ip=HOST, port=PORT, timeout=2, retries=1)

# --- get_info() ---
ok = vm.get_info()
assert ok, "get_info() returned False"
print(f"[test] get_info() OK -> X={vm.XaxisPosition}, Y={vm.YaxisPosition}")
assert vm.XaxisPosition == X_POS, f"X mismatch: {vm.XaxisPosition}"
assert vm.YaxisPosition == Y_POS, f"Y mismatch: {vm.YaxisPosition}"
print(f"[test] scaled: x_axis_pos()={vm.x_axis_pos()}, y_axis_pos()={vm.y_axis_pos()}")
assert vm.is_print() is True
assert vm.is_right_to_left() is True
assert vm.is_emergency() is False
assert vm.is_triggered() is False
print("[test] status bits OK (print=1, direction=1, emergency=0, trigger=0)")

# --- send_pause() ---
ok = vm.send_pause(True)
assert ok, "send_pause(True) returned False"
print("[test] send_pause(True) OK")

vm.close()

# --- 从模拟器 datastore 验证 192 寄存器确实被写为 0x8000 ---
# 直接连客户端读回验证（绕过 datastore 内部结构差异）
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient(HOST, port=PORT, timeout=2)
c.connect()
rr = c.read_holding_registers(192, count=1, device_id=0)
assert not rr.isError(), f"readback isError: {rr}"
print(f"[test] register 192 readback = 0x{rr.registers[0]:04X}")
assert rr.registers[0] == 0x8000, f"pause not written: {rr.registers[0]}"
c.close()

ServerStop()
print("\n=== ALL PASSED: VisionModbus works with pymodbus 3.14 (device_id path) ===")
