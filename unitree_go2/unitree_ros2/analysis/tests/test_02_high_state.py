#!/usr/bin/env python3
"""
test_02_high_state.py — Go2 高层运动状态读取

功能：
  实时读取 Go2 的高层运动状态并格式化打印：
  - 位置、速度、机体高度
  - 运动模式、步态类型
  - IMU 数据（RPY 欧拉角）
  - 足端位置、足端力

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_02_high_state.py

预期效果：
  持续打印 Go2 的运动状态信息，示意输出：
  ────────────────────────────────────
  位置: x=0.57 y=0.21 yaw=0.05
  速度: vx=-0.01 vy=0.00 vz=-0.02
  模式: locomotion(3)  步态: trot(1)
  IMU: roll=0.01 pitch=0.02 yaw=0.05
  机体高度: 0.32m  抬腿: 0.09m
  足端力: FL=12 FR=15 RL=18 RR=10
  ────────────────────────────────────
"""
import os
import sys
import signal

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_go.msg import SportModeState

# 运动模式名称映射
MODE_NAMES = {
    0: "idle", 1: "balanceStand", 2: "pose", 3: "locomotion",
    5: "lieDown", 6: "jointLock", 7: "damping", 8: "recoveryStand",
    10: "sit", 11: "frontFlip", 12: "frontJump", 13: "frontPounce",
}

# 步态名称映射
GAIT_NAMES = {
    0: "idle", 1: "trot", 2: "run", 3: "climbStair",
    4: "downStair", 9: "adjust",
}


class HighStateReader(Node):
    """Go2 高层运动状态读取器"""

    def __init__(self):
        super().__init__('go2_high_state_reader')
        self.count = 0

        # 订阅高频状态
        self.sub_high = self.create_subscription(
            SportModeState,
            '/sportmodestate',
            self.high_callback,
            10
        )

        # 备用低频订阅
        self.sub_lowfreq = self.create_subscription(
            SportModeState,
            '/lf/sportmodestate',
            self.lf_callback,
            10
        )

        self.get_logger().info("Go2 高层状态读取器已启动")

    def high_callback(self, msg):
        self._print_state(msg, 'H')

    def lf_callback(self, msg):
        self._print_state(msg, 'L')

    def _print_state(self, msg, freq_tag):
        self.count += 1
        mode_name = MODE_NAMES.get(msg.mode, f"unknown({msg.mode})")
        gait_name = GAIT_NAMES.get(msg.gait_type, f"unknown({msg.gait_type})")
        rpy = msg.imu_state.rpy

        print(f"\n── {freq_tag}F #{self.count} ──────────────────────────────")
        print(f"  位置: x={msg.position[0]:.3f}  y={msg.position[1]:.3f}  yaw={msg.position[2]:.3f}")
        print(f"  速度: vx={msg.velocity[0]:.3f}  vy={msg.velocity[1]:.3f}  vz={msg.velocity[2]:.3f}")
        print(f"  偏航速: {msg.yaw_speed:.3f} rad/s")
        print(f"  模式: {mode_name}({msg.mode})  步态: {gait_name}({msg.gait_type})")
        print(f"  IMU:  roll={rpy[0]:.3f}  pitch={rpy[1]:.3f}  yaw={rpy[2]:.3f}")
        print(f"  机体高度: {msg.body_height:.3f}m  抬腿: {msg.foot_raise_height:.3f}m")
        print(f"  足端力: FL={msg.foot_force[0]}  FR={msg.foot_force[1]}  RL={msg.foot_force[2]}  RR={msg.foot_force[3]}")
        print(f"  障碍物: F={msg.range_obstacle[0]:.2f} B={msg.range_obstacle[1]:.2f} L={msg.range_obstacle[2]:.2f} R={msg.range_obstacle[3]:.2f}")
        print(f"  足端位置(Body系): FL=({msg.foot_position_body[0]:.3f},{msg.foot_position_body[1]:.3f},{msg.foot_position_body[2]:.3f})")
        print(f"                     FR=({msg.foot_position_body[3]:.3f},{msg.foot_position_body[4]:.3f},{msg.foot_position_body[5]:.3f})")
        print(f"                     RL=({msg.foot_position_body[6]:.3f},{msg.foot_position_body[7]:.3f},{msg.foot_position_body[8]:.3f})")
        print(f"                     RR=({msg.foot_position_body[9]:.3f},{msg.foot_position_body[10]:.3f},{msg.foot_position_body[11]:.3f})")
        print(f"  错误码: {msg.error_code}  动作进度: {msg.progress:.1%}")


def main():
    rclpy.init(args=sys.argv)
    node = HighStateReader()

    print("\n" + "=" * 60)
    print("  Go2 高层运动状态读取")
    print("  按 Ctrl+C 停止")
    print("=" * 60)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n\n停止读取。共收到 {} 条状态。".format(node.count))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()