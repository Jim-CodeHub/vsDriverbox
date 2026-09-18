# -*- coding: utf-8 -*-
"""diag_y_placement.py — 复算 StreamRealtime 的 y 摆放，定位 strip 1 越界原因。

只算摆放数学，不需要图像。输入来自现场日志 20260912_143029.log 的真实
Step / Direction / MotionStartPoint，以及现场生效的标定文件。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import stitch_stream_final as S

TRUE_YAML = os.path.join(_ROOT, "calib", "4_registered_calib.yaml")
FALSE_YAML = os.path.join(_ROOT, "calib", "3_hflip_registered_calib.yaml")

# 现场日志 20260912_143029.log（第二次 143300 数值几乎相同）
STRIPS = [
    # (index, Direction, Step, MotionStartPoint)
    (0, True,  706244.9645996094,  0.0),
    (1, False, 1412507.0190429688, 29761010.7421875),
    (2, True,  2118354.034423828,  2961140.13671875),
    (3, False, 2824616.0888671875, 29691389.16015625),
    (4, True,  3530877.9907226562, 2961390.0756835938),
]

# 现场配置注入的逐机常数（cfgcxt 缺省 + StreamRealtime 注入）
CFG_D_STEP_X = 846.0527400801201
CFG_X_OFFSET_FALSE = 5.2406


def main():
    print("=== 常数 ===")
    print(f"  D_MSP_Y          = {S.D_MSP_Y}   (实时路径未注入，恒用此值)")
    print(f"  Y_OFFSET_TRUE_PX = {S.Y_OFFSET_TRUE_PX}   (未注入)")
    print(f"  Y_OFFSET_FALSE_PX= {S.Y_OFFSET_FALSE_PX}   (未注入)")
    print(f"  Y_MARGIN         = {S.Y_MARGIN}")
    print(f"  cfg  d_step_x    = {CFG_D_STEP_X}  (已注入)")
    print(f"  cfg  x_off_false = {CFG_X_OFFSET_FALSE}  (已注入)")

    tc = S.load_calibration_yaml(TRUE_YAML)
    fc = S.load_calibration_yaml(FALSE_YAML)
    true_shape = S.target_grid_shape(tc)
    false_shape = S.target_grid_shape(fc)
    print("\n=== 标定条带尺寸 (H, W) ===")
    print(f"  true_shape  = {true_shape}")
    print(f"  false_shape = {false_shape}")
    print("  （日志报错里 strip 1 需要 h=%d，应等于 false_shape[0]）" % 30785)

    H_true = int(true_shape[0])
    H_false = int(false_shape[0])

    print("\n=== 各 strip 的模型 y（top 行；越小越靠上）===")
    print(f"{'idx':>4} {'dir':>6} {'MSP':>16} {'top(raw_y)':>14}")
    tops = {}
    for idx, direction, step, msp in STRIPS:
        if direction:
            top = -msp / S.D_MSP_Y - H_true + S.Y_OFFSET_TRUE_PX
        else:
            top = -msp / S.D_MSP_Y + S.Y_OFFSET_FALSE_PX
        tops[idx] = top
        if msp == 0.0:
            print(f"{idx:>4} {str(direction):>6} {'0 (invalid)':>16} {'需修复':>14}")
        else:
            print(f"{idx:>4} {str(direction):>6} {msp:>16.2f} {top:>14.1f}")

    print("\n=== 有效 MSP 的 strip 之间 top 差（相邻两趟应几乎重合）===")
    valid = [i for i, d, s, m in STRIPS if m != 0.0]
    for a, b in zip(valid, valid[1:]):
        print(f"  strip {a} -> {b}: {tops[b] - tops[a]:+10.1f} px")

    # strip 0 的 MSP 被修复成什么值，才能让 strip 1 的 top 与 strip 0 对齐？
    # 反过来：由观测到的 canvas_y1=-270 反推 MSP0'
    # canvas_y1 = raw_y1 - raw_y0 + Y_MARGIN = -270
    MSP1 = 29761010.7421875
    raw_y1 = -MSP1 / S.D_MSP_Y + S.Y_OFFSET_FALSE_PX
    # raw_y0 = -MSP0'/D - H_true + Y_OFF_T
    # raw_y1 - raw_y0 = -270 - Y_MARGIN
    rhs = -270 - S.Y_MARGIN                     # = raw_y1 - raw_y0
    # rhs = -MSP1/D + Y_OFF_F + MSP0'/D + H_true - Y_OFF_T
    MSP0_prime = (rhs + MSP1 / S.D_MSP_Y - S.Y_OFFSET_FALSE_PX - H_true
                  + S.Y_OFFSET_TRUE_PX) * S.D_MSP_Y
    print("\n=== 反推 strip 0 被修复后的 MSP ===")
    print(f"  由 canvas_y1=-270 反推：MSP0' = {MSP0_prime:,.1f}")
    print(f"  同方向(strip 2/4)实测 MSP   = 2,961,140 / 2,961,350")
    print(f"  与 strip 2 的差            = {MSP0_prime - 2961140.13671875:+,.1f}")

    # 若 MSP0' 取 strip 2 的值（合理修复），strip 1 会落在哪？
    raw_y0 = -2961140.13671875 / S.D_MSP_Y - H_true + S.Y_OFFSET_TRUE_PX
    canvas_y1 = raw_y1 - raw_y0 + S.Y_MARGIN
    print(f"\n=== 若 MSP0' = 2,961,140（按同方向实测修复）===")
    print(f"  strip 1 的 canvas_y = {canvas_y1:+.1f}  （buffer 顶=0，Y_MARGIN={S.Y_MARGIN}）")
    print(f"  缓冲高度需覆盖 top..top+{H_false}")
    need = -canvas_y1 if canvas_y1 < 0 else 0
    print(f"  => 需要的上边距 = {need:.1f} px，当前 Y_MARGIN = {S.Y_MARGIN}")


if __name__ == "__main__":
    main()
