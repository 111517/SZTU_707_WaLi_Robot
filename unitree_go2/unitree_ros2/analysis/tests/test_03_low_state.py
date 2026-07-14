#!/usr/bin/env python3
"""
test_03_low_state.py — Go2 底层状态读取

功能：
  实时读取 Go2 底层状态并格式化打印：
  - 关节电机角度、角速度、力矩估计、温度
  - IMU 数据（加速度计、陀螺仪）
  - 电池状态（电压、电流、电量）
  - 足端力（传感器 + 估算值）

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_03_low_state.py

预期效果：
  每 0.5 秒打印一次底层状态快照：
  ═══ Go2 底层状态 ═══
  🔋 电池: 85% | 29.4V | 2.1A
  📐 IMU Acc: [0.1, 0.0, 9.8] m/s²
  🔄 关节:
    FL_hip: angle=0.12 velocity=0.05 tau=0.3 temp=35°C
    FL_thigh: angle=1.36 velocity=0.02 tau=1.2 temp=38°C
    ...
  🦶 足力: [12, 15, 18, 10] | 估计: [14, 16, 20, 11]
"""
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_go.msg import LowState

# 关节名称
JOINT_NAMES = [
    "FL_hip", "FL_thigh", "FL_calf",     # 前左腿
    "FR_hip", "FR_thigh", "FR_calf",     # 前右腿
    "RL_hip", "RL_thigh", "RL_calf",     # 后左腿
    "RR_hip", "RR_thigh", "RR_calf",     # 后右腿
]

# 足端名称
FOOT_NAMES = ["FL", "FR", "RL", "RR"]


class LowStateReader(Node):
    """Go2 底层状态读取器"""

    def __init__(self):
        super().__init__('go2_low_state_reader')
        self.latest_state = None
        self.count = 0

        # 高频订阅
        self.sub_high = self.create_subscription(
            LowState, '/lowstate', self.callback, 10
        )
        # 低频备用
        self.sub_lowfreq = self.create_subscription(
            LowState, '/lf/lowstate', self.callback, 10
        )

        # 定时打印
        self.timer = self.create_timer(0.5, self.print_state)

        self.get_logger().info("Go2 底层状态读取器已启动")

    def callback(self, msg):
        self.latest_state = msg
        self.count += 1

    def print_state(self):
        state = self.latest_state
        if state is None:
            print("⏳ 等待底层状态数据...")
            return

        bms = state.bms_state
        imu = state.imu_state
        motors = state.motor_state

        print(f"\n╔══ Go2 底层状态 #{self.count} ══════════════════════╗")

        # 电池
        voltage = state.power_v
        current = state.power_a
        power = voltage * current
        print(f"║ 🔋 电池: {bms.soc}% | {voltage:.1f}V | {current:.1f}A | {power:.1f}W")
        print(f"║    电芯电压(mV): {list(bms.cell_vol[:4])}...")

        # IMU
        acc = imu.accelerometer
        gyro = imu.gyroscope
        rpy = imu.rpy
        print(f"║ 📐 IMU Acc: [{acc[0]:.2f}, {acc[1]:.2f}, {acc[2]:.2f}] m/s²")
        print(f"║     Gyro: [{gyro[0]:.2f}, {gyro[1]:.2f}, {gyro[2]:.2f}] rad/s")
        print(f"║     RPY:  [{rpy[0]:.2f}, {rpy[1]:.2f}, {rpy[2]:.2f}] rad")

        # 关节 (Go2 有 12 个主动关节)
        print(f"║ 🔄 关节数据 (tick={state.tick}):")
        for i in range(12):
            m = motors[i]
            show = abs(m.q) > 0.001 or abs(m.dq) > 0.001
            marker = "" if show else " (静止)"
            print(f"║   {JOINT_NAMES[i]:12s}: q={m.q:7.3f} dq={m.dq:7.3f} "
                  f"τ_est={m.tau_est:6.2f} T={m.temperature:3d}°C{marker}")

        # 足端力
        print(f"║ 🦶 足力: [{state.foot_force[0]}, {state.foot_force[1]}, "
              f"{state.foot_force[2]}, {state.foot_force[3]}]")
        print(f"║    估计: [{state.foot_force_est[0]}, {state.foot_force_est[1]}, "
              f"{state.foot_force_est[2]}, {state.foot_force_est[3]}]")

        # 风扇
        print(f"║ 🌬️  风扇: {list(state.fan_frequency)} RPM")

        # CRC
        print(f"║ ✅ CRC: {state.crc:#010x}")
        print(f"╚══════════════════════════════════════════════╝")


def main():
    rclpy.init(args=sys.argv)
    node = LowStateReader()

    print("\n" + "=" * 60)
    print("  Go2 底层状态读取")
    print("  按 Ctrl+C 停止")
    print("=" * 60)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n\n停止。共收到 {} 条底层状态数据。".format(node.count))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()