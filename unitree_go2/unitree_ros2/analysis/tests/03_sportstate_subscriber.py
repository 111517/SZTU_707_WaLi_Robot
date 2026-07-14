#!/usr/bin/env python3
"""
03_sportstate_subscriber.py — Go2 高级运动状态订阅

功能：
  订阅 /sportmodestate 话题，以 1Hz 频率打印高层运动状态：
  - 世界坐标位置 (x, y, z) 与线速度向量
  - RPY 姿态、机体高度、抬脚高度
  - 步态类型、运动模式、步态进度
  - 前后左右四个方向障碍物检测距离

使用方式：
  source /opt/ros/foxy/setup.bash
  source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI="file://$HOME/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"
  python3 03_sportstate_subscriber.py

前提条件：
  机器人须处于高级运动模式（normal / ai 等），否则 Topic 无数据
  或数据全为零。idle 模式下 Topic 可订阅但障碍物/足端位置为空。

预期输出（每秒刷新）：
  ───── 16:30:01 ─────
  📍 位置  x= 0.012  y=-0.003  z= 0.050
  🏃 速度  前进= 0.30  横移= 0.00  垂直= 0.00  yaw=-0.01
  📐 姿态  roll=-0.01  pitch=-0.10  yaw=-0.06
           体高=0.25m  抬脚=0.08m
  🚶 步态  模式=locomotion(3)  步态=trot(1)  进度=0.45
  📏 障距  前=1.23m  后=0.00m  左=0.98m  右=0.56m

安全说明：
  仅订阅数据，不发送任何控制指令。可在任意运动模式下安全运行。
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
from unitree_go.msg import SportModeState

# ============================================================
# 枚举映射
# ============================================================

MODE_NAMES = {
    0:  "idle（待机）",
    1:  "balanceStand（平衡站立）",
    2:  "pose（姿态控制）",
    3:  "locomotion（运动模式）",
    5:  "lieDown（趴下）",
    6:  "wirelessRemote（遥控行走）",
    7:  "damping（阻尼）",
    8:  "recoveryStand（恢复站立）",
    10: "sit（坐下）",
    11: "frontFlip（前空翻）",
    12: "frontJump（前跳）",
    13: "frontPounce（前扑）",
}

GAIT_NAMES = {
    0: "idle",
    1: "trot（小跑）",
    2: "run（奔跑）",
    3: "climbStair（上楼梯）",
    4: "forwardDownStair（下楼梯）",
    9: "adjust（调整）",
}

FOOT_LABELS = ["FL", "FR", "RL", "RR"]

# 障碍物方向 — range_obstacle 数组索引顺序
OBS_DIRS = ["前", "后", "左", "右"]


# ============================================================
# SportModeState 订阅节点
# ============================================================

class SportStateSubscriber(Node):
    """Go2 高级运动状态订阅器 — 1Hz 刷新"""

    def __init__(self):
        super().__init__('go2_sportstate_subscriber')
        self._latest: SportModeState | None = None
        self._count = 0
        self._start = time.time()

        # 主话题
        self._sub = self.create_subscription(
            SportModeState, '/sportmodestate', self._on_state, 10
        )
        # 低频备用
        self._sub_lf = self.create_subscription(
            SportModeState, '/lf/sportmodestate', self._on_state, 10
        )

        self._timer = self.create_timer(1.0, self._print_state)
        self.get_logger().info("高级运动状态订阅器已启动 — 按 Ctrl+C 退出")

    def _on_state(self, msg: SportModeState):
        self._latest = msg
        self._count += 1

    # ---------- 格式化辅助 ----------

    def _mode_str(self, val):
        return MODE_NAMES.get(val, f"unknown({val})")

    def _gait_str(self, val):
        return GAIT_NAMES.get(val, f"unknown({val})")

    def _sgn(self, v):
        """带符号，左对齐数值"""
        return f"{v:+.3f}"

    def _progress_bar(self, p):
        """步态进度条 0.0–1.0"""
        width = 20
        filled = int(p * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {p:.0%}"

    # ---------- 打印 ----------

    def _print_state(self):
        s = self._latest
        if s is None:
            print("⏳ 等待 SportModeState…（机器人是否处于高级运动模式？）")
            return

        t = time.strftime('%H:%M:%S')
        elapsed = time.time() - self._start
        freq = self._count / elapsed if elapsed > 0 else 0

        print(f"\n{'─' * 55}")
        print(f"  {t} │ 收 {self._count} 条 ({freq:.0f} Hz)")
        print(f"{'─' * 55}")

        self._print_position(s)
        self._print_velocity(s)
        self._print_attitude(s)
        self._print_gait(s)
        self._print_obstacles(s)
        self._print_feet(s)

    # ---------- 位置 ----------

    def _print_position(self, s: SportModeState):
        px, py, pz = s.position
        print(f"\n  📍 世界坐标")
        print(f"    x = {px:+.4f}  y = {py:+.4f}  z = {pz:.4f}")

    # ---------- 速度 ----------

    def _print_velocity(self, s: SportModeState):
        vx, vy, vz = s.velocity
        yaw = s.yaw_speed
        print(f"\n  🏃 速度")
        print(f"    线速度  前进(vx)= {vx:+7.3f}  横移(vy)= {vy:+7.3f}  垂直(vz)= {vz:+7.3f} m/s")
        print(f"    角速度  yaw = {yaw:+7.3f} rad/s  ({math.degrees(yaw):+.1f}°/s)")

    # ---------- 姿态 ----------

    def _print_attitude(self, s: SportModeState):
        rpy = s.imu_state.rpy
        deg = [math.degrees(v) for v in rpy]
        bh = s.body_height
        frh = s.foot_raise_height

        print(f"\n  📐 姿态")
        print(f"    RPY     roll={rpy[0]:+.3f}({deg[0]:+.1f}°)  "
              f"pitch={rpy[1]:+.3f}({deg[1]:+.1f}°)  "
              f"yaw={rpy[2]:+.3f}({deg[2]:+.1f}°)")
        print(f"    体高    {bh:.3f} m")
        print(f"    抬脚    {frh:.3f} m")

    # ---------- 步态 ----------

    def _print_gait(self, s: SportModeState):
        mode_name = self._mode_str(s.mode)
        gait_name = self._gait_str(s.gait_type)
        bar = self._progress_bar(s.progress)
        ec = s.error_code

        print(f"\n  🚶 步态")
        print(f"    模式  {mode_name}")
        print(f"    步态  {gait_name}")
        print(f"    进度  {bar}")
        if ec:
            print(f"    错误  code={ec}")

    # ---------- 障碍物 ----------

    def _print_obstacles(self, s: SportModeState):
        obs = s.range_obstacle
        has_data = any(v > 0.01 for v in obs)

        print(f"\n  📏 障碍物距离")
        if has_data:
            for i, d in enumerate(OBS_DIRS):
                val = obs[i]
                if val > 0.01:
                    # 近距离高亮
                    mark = " ⚠ 近" if val < 0.5 else ""
                    print(f"    {d}  {val:.2f} m{mark}")
                else:
                    print(f"    {d}  ——")
        else:
            print(f"    (无数据 — 机器人可能处于 idle 模式或避障未启用)")

    # ---------- 足端 ----------

    def _print_feet(self, s: SportModeState):
        fp = s.foot_position_body
        ff = s.foot_force

        if len(fp) < 12:
            return

        has_pos = any(abs(v) > 0.001 for v in fp)
        has_force = any(v > 0 for v in ff) if len(ff) >= 4 else False

        if not has_pos and not has_force:
            return

        print(f"\n  🦶 足端")
        for i, label in enumerate(FOOT_LABELS):
            x = fp[i * 3]
            y = fp[i * 3 + 1]
            z = fp[i * 3 + 2]
            force = ff[i] if i < len(ff) else 0
            contact = "▼" if force > 5 else "△"
            print(f"    {label}  pos=({x:+6.3f}, {y:+6.3f}, {z:+6.3f})  "
                  f"力={force:>4d}  {contact}")


# ============================================================
# 入口
# ============================================================

def main():
    for k in ['RMW_IMPLEMENTATION']:
        if not os.environ.get(k):
            os.environ[k] = 'rmw_cyclonedds_cpp'
    if not os.environ.get('CYCLONEDDS_URI'):
        os.environ['CYCLONEDDS_URI'] = (
            'file:///home/unitree/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml'
        )

    rclpy.init(args=sys.argv)

    node = SportStateSubscriber()

    print()
    print("═" * 55)
    print("  Go2 高级运动状态订阅 (SportModeState)")
    print("  1 Hz 刷新 │ 按 Ctrl+C 退出")
    print("═" * 55)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        elapsed = time.time() - node._start
        print(f"\n\n停止。运行 {elapsed:.0f}s，收到 {node._count} 条数据。")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()