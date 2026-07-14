#!/usr/bin/env python3
"""
test_04_basic_motion.py — Go2 基本运动控制测试

⚠️  测试前请确保：
  1. Go2 周围有至少 2m×2m 安全空地
  2. Go2 处于非休眠状态
  3. 已 source setup.sh 配置环境

功能：
  依次执行以下基本动作（每个动作间隔 3 秒）：
  1. 起立 (StandUp)
  2. 平衡站立 (BalanceStand)
  3. 趴下 (StandDown)
  4. 再起立 (StandUp)
  5. 阻尼模式 (Damp)

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_04_basic_motion.py

预期效果：
  机器人依次完成起立→平衡→趴下→起立→阻尼的动作序列。
  终端打印每个动作的执行状态。
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


class BasicMotionTest(Node):
    """Go2 基本运动控制测试"""

    def __init__(self):
        super().__init__('go2_basic_motion_test')

        # 创建请求发布者
        self.req_pub = self.create_publisher(Request, '/api/sport/request', 10)

        # 订阅状态用于验证
        self.latest_state = None
        self.state_sub = self.create_subscription(
            SportModeState, '/lf/sportmodestate', self.state_callback, 10
        )
        # 备用高频
        self.state_sub_hf = self.create_subscription(
            SportModeState, '/sportmodestate', self.state_callback_hf, 10
        )

        self.get_logger().info("基本运动控制测试节点已启动")

    def state_callback(self, msg):
        self.latest_state = msg

    def state_callback_hf(self, msg):
        if self.latest_state is None:
            self.latest_state = msg

    def send_command(self, api_id, parameter=None):
        """发送运动控制指令"""
        req = Request()
        req.header.identity.api_id = api_id
        if parameter:
            req.parameter = json.dumps(parameter)
        self.req_pub.publish(req)
        self.get_logger().info(f"发送指令: API_ID={api_id} param={parameter}")

    def get_current_mode(self):
        """获取当前运动模式"""
        if self.latest_state:
            mode_names = {
                0: "idle", 1: "balanceStand", 2: "pose", 3: "locomotion",
                5: "lieDown", 6: "jointLock", 7: "damping", 8: "recoveryStand",
                10: "sit",
            }
            return mode_names.get(self.latest_state.mode, str(self.latest_state.mode))
        return "unknown"

    def wait_spin(self, seconds):
        """等待指定时间，期间持续 spin"""
        end = time.time() + seconds
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.1)

    def run_sequence(self):
        print("\n" + "=" * 60)
        print("  ⚠️  Go2 基本运动控制测试")
        print("  确保机器人周围安全！按 Ctrl+C 紧急停止")
        print("=" * 60)

        sequence = [
            (None, 2, "等待初始化..."),
            (1004, 3, "Step 1/5: 起立 (StandUp)"),
            (1002, 3, "Step 2/5: 平衡站立 (BalanceStand)"),
            (1005, 3, "Step 3/5: 趴下 (StandDown)"),
            (1004, 4, "Step 4/5: 再次起立 (StandUp)"),
            (1001, 2, "Step 5/5: 阻尼模式 (Damp) — 测试结束"),
        ]

        for api_id, wait, desc in sequence:
            print(f"\n>>> {desc}")
            mode_prev = self.get_current_mode()
            print(f"  当前模式: {mode_prev}")

            if api_id is not None:
                self.send_command(api_id)
                self.wait_spin(wait)
                mode_cur = self.get_current_mode()
                print(f"  执行后模式: {mode_cur}")
            else:
                self.wait_spin(wait)

        print("\n" + "=" * 60)
        print("  ✅ 基本运动控制测试完成")
        print("=" * 60)


def main():
    rclpy.init(args=sys.argv)
    tester = BasicMotionTest()
    try:
        tester.run_sequence()
    except KeyboardInterrupt:
        print("\n\n🛑 用户中断！发送紧急停止...")
        tester.send_command(1003)  # StopMove
        time.sleep(1)
        tester.send_command(1001)  # Damp
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()