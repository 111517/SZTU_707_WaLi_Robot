#!/usr/bin/env python3
"""
test_07_joystick.py — Go2 遥控器状态读取

功能：
  读取 Go2 遥控器（配套手持遥控器）的实时状态：
  - 左右摇杆数值
  - 按键状态（位掩码解码）
  - 摇杆可视化（简易 ASCII）

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_07_joystick.py

预期效果：
  实时显示遥控器状态，移动摇杆时可视化反馈：
  ╔══ 遥控器状态 ══════════════════╗
  ║ L: (-0.5, 0.0)  R: (0.8, 0.0) ║
  ║ 按键: 0x0001                   ║
  ║     L           R              ║
  ║  (-0.5,0.0)  ( 0.8,0.0)       ║
  ╚════════════════════════════════╝
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_go.msg import WirelessController

# 遥控器按键位掩码定义（参考宇树文档）
KEY_BITS = {
    0:  "R1",
    1:  "L1",
    2:  "START",
    3:  "SELECT",
    4:  "R2",
    5:  "L2",
    6:  "F1",
    7:  "F2",
    8:  "A",
    9:  "B",
    10: "X",
    11: "Y",
    12: "UP",
    13: "RIGHT",
    14: "DOWN",
    15: "LEFT",
}


class JoystickReader(Node):
    """Go2 遥控器状态读取"""

    def __init__(self):
        super().__init__('go2_joystick_reader')
        self.latest = None
        self.sub = self.create_subscription(
            WirelessController, '/wirelesscontroller', self.callback, 10
        )
        self.timer = self.create_timer(0.2, self.print_state)
        self.get_logger().info("遥控器读取器已启动")

    def callback(self, msg):
        self.latest = msg

    def decode_keys(self, keys_val):
        """解码按键位掩码"""
        pressed = []
        for bit, name in KEY_BITS.items():
            if keys_val & (1 << bit):
                pressed.append(name)
        return pressed

    def joystick_viz(self, lx, ly, rx, ry):
        """简单的摇杆 ASCII 可视化"""
        # 归一化到 -1..1 范围显示
        def to_char(v):
            if v > 0.5: return '█'
            if v > 0.1: return '▓'
            if v > -0.1: return '·'
            if v > -0.5: return '░'
            return ' '

        ly_c = to_char(-ly)  # Y 轴反转
        lx_c = to_char(lx)

        lines = []
        lines.append(f"      L stick         R stick")
        lines.append(f"   ({lx:+.2f}, {ly:+.2f})    ({rx:+.2f}, {ry:+.2f})")
        lines.append(f"       {ly_c}                {to_char(-ry)}")
        lines.append(f"    {to_char(-lx)} {lx_c} {to_char(lx)}        {to_char(-rx)} {to_char(rx)} {to_char(rx)}")
        lines.append(f"       {to_char(ly)}                {to_char(ry)}")
        return "\n".join(lines)

    def print_state(self):
        if self.latest is None:
            print("⏳ 等待遥控器数据...")
            return

        msg = self.latest
        pressed_keys = self.decode_keys(msg.keys)
        keys_str = ", ".join(pressed_keys) if pressed_keys else "(无)"

        print("\n" + "╔" + "═" * 40 + "╗")
        print(f"║ 🎮 遥控器状态 (keys=0x{msg.keys:04X})           ║")
        print(f"║ L: ({msg.lx:+.2f}, {msg.ly:+.2f})  R: ({msg.rx:+.2f}, {msg.ry:+.2f})       ║")
        print(f"║ 按键: {keys_str:<30} ║")
        print("╠" + "═" * 40 + "╣")
        for line in self.joystick_viz(msg.lx, msg.ly, msg.rx, msg.ry).split('\n'):
            print(f"║ {line:<38} ║")
        print("╚" + "═" * 40 + "╝")


def main():
    rclpy.init(args=sys.argv)
    node = JoystickReader()

    print("\n" + "=" * 45)
    print("  Go2 遥控器状态读取")
    print("  按 Ctrl+C 停止")
    print("=" * 45)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n停止。")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()