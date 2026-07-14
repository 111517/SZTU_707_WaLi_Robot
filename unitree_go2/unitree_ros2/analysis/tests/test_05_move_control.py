#!/usr/bin/env python3
"""
test_05_move_control.py — Go2 移动控制测试

⚠️  测试前请确保：
  1. Go2 周围有足够空间（建议 3m×3m 以上平坦区域）
  2. 手动将 Go2 起立
  3. 或使用 test_04_basic_motion.py 先起立

功能：
  1. 自动起立
  2. 前进 3 秒
  3. 左转 2 秒
  4. 后退 2 秒
  5. 右转 2 秒
  6. 停止并趴下

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_05_move_control.py [vx] [vyaw] [duration]

  参数（可选）：
    vx      — 前进速度 m/s（默认 0.3）
    vyaw    — 旋转速度 rad/s（默认 0.5）
    duration— 每段持续时间秒（默认 3）

示例：
  python3 tests/test_05_move_control.py 0.2 0.3 2    # 慢速短距
  python3 tests/test_05_move_control.py               # 默认参数

预期效果：
  Go2 前进→左转→后退→右转→停止→趴下。
"""
import os
import sys
import time
import json
import math

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_api.msg import Request
from unitree_go.msg import SportModeState


class MoveControlTest(Node):
    """Go2 移动控制测试"""

    def __init__(self, vx, vyaw, duration):
        super().__init__('go2_move_control_test')
        self.vx = vx
        self.vyaw = vyaw
        self.duration = duration
        self.req_pub = self.create_publisher(Request, '/api/sport/request', 10)
        self.latest_state = None

        self.state_sub = self.create_subscription(
            SportModeState, '/lf/sportmodestate', self.callback, 10
        )
        self.state_sub_hf = self.create_subscription(
            SportModeState, '/sportmodestate', self.callback, 10
        )

    def callback(self, msg):
        self.latest_state = msg

    def send(self, api_id, param=None):
        req = Request()
        req.header.identity.api_id = api_id
        if param:
            req.parameter = json.dumps(param)
        self.req_pub.publish(req)
        name = {
            1003: "StopMove", 1004: "StandUp", 1005: "StandDown",
            1007: "Euler", 1008: "Move",
        }.get(api_id, f"API_{api_id}")
        self.get_logger().info(f"➡️  {name}: {param or '()'}")

    def wait_spin(self, s):
        end = time.time() + s
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.05)

    def run(self):
        print("\n" + "=" * 60)
        print(f"  Go2 移动控制测试")
        print(f"  vx={self.vx} m/s | vyaw={self.vyaw} rad/s | 每段={self.duration}s")
        print("  按 Ctrl+C 紧急停止")
        print("=" * 60)

        try:
            # 1. 起立
            print("\n[1/7] 起立...")
            self.send(1004)
            self.wait_spin(3)

            # 2. 前进
            print(f"\n[2/7] 前进 ({self.duration}s)...")
            self.send(1008, {"x": self.vx, "y": 0.0, "z": 0.0})
            self.wait_spin(self.duration)

            # 3. 左转
            print(f"\n[3/7] 左转 ({self.duration}s)...")
            self.send(1008, {"x": 0.0, "y": 0.0, "z": self.vyaw})
            self.wait_spin(self.duration)

            # 4. 后退
            print(f"\n[4/7] 后退 ({self.duration}s)...")
            self.send(1008, {"x": -self.vx, "y": 0.0, "z": 0.0})
            self.wait_spin(self.duration)

            # 5. 右转
            print(f"\n[5/7] 右转 ({self.duration}s)...")
            self.send(1008, {"x": 0.0, "y": 0.0, "z": -self.vyaw})
            self.wait_spin(self.duration)

            # 6. 停止
            print("\n[6/7] 停止...")
            self.send(1003)
            self.wait_spin(2)

            # 7. 趴下
            print("\n[7/7] 趴下...")
            self.send(1005)
            self.wait_spin(3)

        except KeyboardInterrupt:
            print("\n🛑 紧急停止！")
            self.send(1003)
            self.wait_spin(1)
            self.send(1001)  # Damp

        if self.latest_state:
            pos = self.latest_state.position
            print(f"\n最终位置: x={pos[0]:.3f} y={pos[1]:.3f} yaw={pos[2]:.3f}")

        print("=" * 60)
        print("  ✅ 移动控制测试完成")
        print("=" * 60 + "\n")


def main():
    rclpy.init(args=sys.argv)
    vx = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    vyaw = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    tester = MoveControlTest(vx, vyaw, duration)
    tester.run()
    tester.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()