#!/usr/bin/env python3
"""
test_06_actions.py — Go2 表演和特技动作测试

⚠️  警告：
  - 特技动作（空翻/跳跃）要求 Go2 周围有足够空间（≥5m×5m 平地 + 缓冲垫）
  - 仅建议在有专业人员指导下执行特技动作
  - 默认跳过特技动作，需手动确认

功能：
  依次执行安全动作：
  1. 起立
  2. 打招呼 (Hello)
  3. 伸懒腰 (Stretch)
  4. 舞蹈 1 (Dance1)
  5. 比心 (Heart)
  6. 趴下

  可选特技（需交互确认）：
  — 前空翻 (FrontFlip)
  — 后空翻 (BackFlip)
  — 前跳 (FrontJump)

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh

  # 仅安全动作（默认）
  python3 tests/test_06_actions.py

  # 包含特技
  python3 tests/test_06_actions.py --extreme

预期效果：
  Go2 依次执行打招呼、伸懒腰、舞蹈等表演动作。
"""
import os
import sys
import time
import json

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_api.msg import Request
from unitree_go.msg import SportModeState


# 动作定义: (api_id, 名称, 间隔秒数, 是否特技, 参数)
SAFE_ACTIONS = [
    (1004, "起立 (StandUp)",        3, False, None),
    (1016, "打招呼 (Hello)",         4, False, None),
    (1017, "伸懒腰 (Stretch)",       4, False, None),
    (1022, "舞蹈1 (Dance1)",         5, False, None),
    (1023, "舞蹈2 (Dance2)",         5, False, None),
    (1036, "比心 (Heart)",           4, False, None),
    (1010, "从坐起身 (RiseSit)",     3, False, None),
]

EXTREME_ACTIONS = [
    (1030, "⚠️  前空翻 (FrontFlip)",   3, True, None),
    (2043, "⚠️  后空翻 (BackFlip)",    3, True, None),
    (1031, "⚠️  前跳 (FrontJump)",     3, True, None),
    (1032, "⚠️  前扑 (FrontPounce)",   3, True, None),
]


class ActionTest(Node):
    """Go2 动作测试"""

    def __init__(self, extreme=False):
        super().__init__('go2_action_test')
        self.req_pub = self.create_publisher(Request, '/api/sport/request', 10)
        self.latest_state = None
        self.state_sub = self.create_subscription(
            SportModeState, '/lf/sportmodestate', self.callback, 10
        )
        self.state_sub_hf = self.create_subscription(
            SportModeState, '/sportmodestate', self.callback, 10
        )

        self.actions = SAFE_ACTIONS[:]
        if extreme:
            self.actions += EXTREME_ACTIONS

    def callback(self, msg):
        self.latest_state = msg

    def send(self, api_id, param=None):
        req = Request()
        req.header.identity.api_id = api_id
        if param:
            req.parameter = json.dumps(param)
        self.req_pub.publish(req)

    def wait_spin(self, s):
        end = time.time() + s
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.1)

    def run(self):
        extreme = any(a[3] for a in self.actions)

        print("\n" + "=" * 60)
        if extreme:
            print("  ⚠️  Go2 表演动作测试（含特技！）")
            print("  ⚠️  确保 5m×5m 安全空间 + 缓冲垫！")
        else:
            print("  Go2 表演动作测试（仅安全动作）")
        print("  按 Ctrl+C 停止")
        print("=" * 60)

        for api_id, name, wait, is_extreme, param in self.actions:
            if is_extreme:
                print(f"\n{'='*40}")
                print(f"  >>> {name}")
                confirm = input("  确认执行？(y/N): ").strip().lower()
                if confirm != 'y':
                    print("  跳过")
                    continue

            print(f"\n>>> {name}")
            if param:
                print(f"  参数: {param}")
            self.send(api_id, param)
            self.wait_spin(wait)

        # 收尾
        print("\n>>> 趴下收尾...")
        self.send(1005)
        self.wait_spin(3)

        print("\n" + "=" * 60)
        print("  ✅ 动作测试完成")
        print("=" * 60 + "\n")


def main():
    rclpy.init(args=sys.argv)
    extreme = '--extreme' in sys.argv

    if extreme:
        print("\n" + "!" * 60)
        print("!!!  已启用特技动作模式  !!!")
        print("!!!  请确认机器人周围环境安全  !!!")
        print("!" * 60)

    tester = ActionTest(extreme=extreme)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n🛑 中断！发送停止...")
        tester.send(1003)
        tester.wait_spin(1)
        tester.send(1001)
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()