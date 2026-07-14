#!/usr/bin/env python3
"""
02_lowstate_subscriber.py — Go2 低级状态订阅

功能：
  订阅 /lowstate 话题，以 1Hz 频率打印完整的低级传感器数据：
  - IMU：四元数、RPY 欧拉角、陀螺仪角速度、加速度
  - 关节：全部 12 个关节的角度/角速度/估算力矩/温度
  - 电池：电压、电流、电量百分比
  - 足端力：四条腿的接触力传感器原始读数

使用方式：
  source /opt/ros/foxy/setup.bash
  source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI="file://$HOME/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"
  python3 02_lowstate_subscriber.py

预期输出（每秒刷新）：
  ───── 16:30:01 │ tick=294217 ─────
  📐 IMU  RPY: roll=-0.01  pitch=-0.10  yaw=-0.06
          四元数: (0.998, -0.005, -0.048, -0.031)
          陀螺仪: [ 0.002  0.001 -0.011] rad/s
          加速度: [ 0.919 -0.165  9.348] m/s²

  🔋 电池  电量: 95%  电压: 31.36V  电流: 0.14A
  🦶 足力  FL=  0  FR= 11  RL= 11  RR= 15

  🔧 关节状态
  #   关节          角度°   速度     力矩   温度
  ──────────────────────────────────────────
   0  FR_hip          -3.5    0.7    0.05    30
   1  FR_thigh        70.6   -0.2   -0.07    29
   ...

安全说明：
  本脚本仅订阅数据，不发送任何控制指令。
  可在机器人任意运动状态下安全运行，不影响当前行为。
"""
import os
import sys
import time
import math

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_go.msg import LowState

# ============================================================
# 关节编号与名称
#   宇树 Go2 每条腿 3 个自由度（hip/thigh/calf），共 12 个主动关节
#   编号顺序：前右(FR) → 前左(FL) → 后右(RR) → 后左(RL)
# ============================================================
JOINT_NAMES = [
    "FR_hip",   "FR_thigh",   "FR_calf",    # 0-2   前右腿
    "FL_hip",   "FL_thigh",   "FL_calf",    # 3-5   前左腿
    "RR_hip",   "RR_thigh",   "RR_calf",    # 6-8   后右腿
    "RL_hip",   "RL_thigh",   "RL_calf",    # 9-11  后左腿
]

FOOT_NAMES = ["FL", "FR", "RL", "RR"]

# 电机模式
MOTOR_MODE_NAMES = {0: "待机", 1: "伺服(FOC)", 2: "校准"}


# ============================================================
# LowState 订阅节点
# ============================================================

class LowStateSubscriber(Node):
    """Go2 低级状态订阅器 —— 1Hz 刷新"""

    def __init__(self):
        super().__init__('go2_lowstate_subscriber')
        self._latest: LowState | None = None
        self._count = 0
        self._start_time = time.time()

        # 高频话题（机器狗持续发布）
        self._sub = self.create_subscription(
            LowState, '/lowstate', self._on_state, 10
        )
        # 低频备用
        self._sub_lf = self.create_subscription(
            LowState, '/lf/lowstate', self._on_state, 10
        )

        # 每秒刷新一次
        self._timer = self.create_timer(1.0, self._print_state)

        self.get_logger().info("低级状态订阅器已启动 — 按 Ctrl+C 退出")

    def _on_state(self, msg: LowState):
        self._latest = msg
        self._count += 1

    # ---------- 打印 ----------

    def _print_state(self):
        state = self._latest
        if state is None:
            print("⏳ 等待 LowState 数据…")
            return

        # 时间戳
        t = time.strftime('%H:%M:%S')
        elapsed = time.time() - self._start_time
        freq = self._count / elapsed if elapsed > 0 else 0

        print(f"\n{'─' * 50}")
        print(f"  {t} │ tick={state.tick} │ 数据 {self._count} 条 ({freq:.0f} Hz)")
        print(f"{'─' * 50}")

        self._print_imu(state)
        self._print_power(state)
        self._print_foot(state)
        self._print_joints(state)

    # ---------- IMU ----------

    def _print_imu(self, state: LowState):
        imu = state.imu_state
        rpy = imu.rpy
        quat = imu.quaternion
        gyro = imu.gyroscope
        acc = imu.accelerometer

        # 度数也显示出来，便于人类理解
        rpy_deg = [math.degrees(v) for v in rpy]

        print(f"\n  📐 IMU")
        print(f"    RPY (rad):  roll={rpy[0]:+.3f}  pitch={rpy[1]:+.3f}  yaw={rpy[2]:+.3f}")
        print(f"    RPY (deg):  roll={rpy_deg[0]:+.1f}°  pitch={rpy_deg[1]:+.1f}°  yaw={rpy_deg[2]:+.1f}°")
        print(f"    四元数:     (w={quat[0]:.3f}, x={quat[1]:+.3f}, y={quat[2]:+.3f}, z={quat[3]:+.3f})")
        print(f"    陀螺仪:     [ {gyro[0]:+7.4f}  {gyro[1]:+7.4f}  {gyro[2]:+7.4f} ] rad/s")
        print(f"    加速度:     [ {acc[0]:+7.3f}  {acc[1]:+7.3f}  {acc[2]:+7.3f} ] m/s²")
        print(f"    温度:       {imu.temperature} °C")

    # ---------- 电池 ----------

    def _print_power(self, state: LowState):
        bms = state.bms_state
        voltage = state.power_v
        current = state.power_a
        power_w = voltage * current

        # 充放电方向
        if current > 0.1:
            direction = "⬆ 放电"
        elif current < -0.1:
            direction = "⬇ 充电"
        else:
            direction = "— 静置"

        print(f"\n  🔋 电池")
        print(f"    电量: {bms.soc}%   电压: {voltage:.2f}V   电流: {current:.2f}A   {direction}")
        print(f"    功率: {power_w:.1f}W   循环: {bms.cycle} 次")

        # 电芯电压（首尾各取2个）
        cells = list(bms.cell_vol)
        print(f"    电芯: [{cells[0]} {cells[1]} … {cells[-2]} {cells[-1]}] mV")

    # ---------- 足端力 ----------

    def _print_foot(self, state: LowState):
        ff = state.foot_force       # 原始足端力
        ffe = state.foot_force_est  # 估计足端力

        # 原始读数
        parts = []
        for i, name in enumerate(FOOT_NAMES):
            parts.append(f"{name}={ff[i]:>4d}")
        line = "  ".join(parts)
        print(f"\n  🦶 足端力")
        print(f"    原始: {line}")

        # 估计值（如果有）
        if any(abs(v) > 0 for v in ffe):
            parts_est = []
            for i, name in enumerate(FOOT_NAMES):
                parts_est.append(f"{name}={ffe[i]:>4d}")
            print(f"    估计: {'  '.join(parts_est)}")

        # 触地判断
        contact = []
        for i, name in enumerate(FOOT_NAMES):
            contact.append(f"{name}={'🟢' if ff[i] > 5 else '⚪'}")
        print(f"    触地: {'  '.join(contact)}")

    # ---------- 关节 ----------

    def _print_joints(self, state: LowState):
        motors = state.motor_state

        print(f"\n  🔧 关节状态")
        print(f"  {'#':>2s}  {'关节':12s}  {'角度°':>8s}  {'角速度':>8s}  {'力矩':>8s}  {'温度':>5s}  {'模式':>8s}")
        print(f"  {'─' * 58}")

        for i in range(12):
            m = motors[i]
            angle_deg = math.degrees(m.q)
            mode_name = MOTOR_MODE_NAMES.get(m.mode, f"mode={m.mode}")

            # 颜色标记：力矩大时标黄
            tau_icon = ""
            if abs(m.tau_est) > 5:
                tau_icon = "⚠ "

            print(f"  {i:2d}  {JOINT_NAMES[i]:12s}  "
                  f"{angle_deg:+7.1f}  "
                  f"{m.dq:+7.2f}  "
                  f"{tau_icon}{m.tau_est:+6.2f}  "
                  f"{m.temperature:4d}°C  "
                  f"{mode_name:>8s}")

        # 统计
        temps = [m.temperature for m in motors[:12]]
        print(f"  {'─' * 58}")
        print(f"  温度范围: {min(temps)}–{max(temps)}°C  (平均 {sum(temps)/12:.0f}°C)")


# ============================================================
# 入口
# ============================================================

def main():
    # 确保环境变量
    for k in ['RMW_IMPLEMENTATION']:
        if not os.environ.get(k):
            os.environ[k] = 'rmw_cyclonedds_cpp'
    if not os.environ.get('CYCLONEDDS_URI'):
        os.environ['CYCLONEDDS_URI'] = (
            'file:///home/unitree/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml'
        )

    rclpy.init(args=sys.argv)

    node = LowStateSubscriber()

    print()
    print("═" * 50)
    print("  Go2 低级状态订阅 (LowState)")
    print("  1 Hz 刷新 │ 按 Ctrl+C 退出")
    print("═" * 50)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        elapsed = time.time() - node._start_time
        print(f"\n\n停止。运行 {elapsed:.0f}s，收到 {node._count} 条数据。")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()