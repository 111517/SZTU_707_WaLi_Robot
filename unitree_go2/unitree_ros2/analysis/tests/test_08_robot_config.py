#!/usr/bin/env python3
"""
test_08_robot_config.py — Go2 系统配置测试

功能：
  通过 /api/sport/request 接口进行配置管理：
  1. 获取自动恢复状态 (AutoRecoveryGet)
  2. 切换自动恢复开关 (AutoRecoverySet)
  3. 设置速度挡位 (SpeedLevel)
  4. 切换摇杆控制 (SwitchJoystick)
  5. 查询/切换避障模式 (SwitchAvoidMode)

  RobotStateClient API（Humble Only）：
  6. 获取服务列表 (ServiceList)
  7. 服务开关 (ServiceSwitch)
  8. 设置报告频率 (SetReportFreq)

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh
  python3 tests/test_08_robot_config.py [--humble]

  选项：
    --humble: 启用 RobotStateClient API（仅 ROS2 Humble 有效）

预期效果：
  交互式菜单，逐项查询/修改 Go2 系统配置。
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
from unitree_api.msg import Request, Response
from unitree_go.msg import SportModeState


class RobotConfigTest(Node):
    """Go2 系统配置测试"""

    def __init__(self, humble_mode=False):
        super().__init__('go2_robot_config_test')
        self.humble_mode = humble_mode

        # 运动控制请求
        self.sport_pub = self.create_publisher(Request, '/api/sport/request', 10)
        # 运动控制响应（用于 AutoRecoveryGet）
        self.sport_response = None
        self.sport_sub = self.create_subscription(
            Response, '/api/sport/response', self.sport_response_callback, 10
        )

        # RobotState API（Humble only）
        if humble_mode:
            self.state_pub = self.create_publisher(Request, '/api/robot_state/request', 10)
            self.state_response = None
            self.state_sub = self.create_subscription(
                Response, '/api/robot_state/response', self.state_response_callback, 10
            )

        # 状态订阅
        self.latest_state = None
        self.create_subscription(SportModeState, '/lf/sportmodestate', self.state_cb, 10)
        self.create_subscription(SportModeState, '/sportmodestate', self.state_cb, 10)

    def state_cb(self, msg):
        self.latest_state = msg

    def sport_response_callback(self, msg):
        self.sport_response = msg

    def state_response_callback(self, msg):
        self.state_response = msg

    def publish_and_wait(self, pub, api_id, param=None, timeout=2.0):
        """发布请求并等待响应"""
        self.sport_response = None
        self.state_response = None

        req = Request()
        req.header.identity.api_id = api_id
        if param:
            req.parameter = json.dumps(param)
        pub.publish(req)

        end = time.time() + timeout
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.05)

        return self.sport_response or self.state_response

    def wait_spin(self, s):
        end = time.time() + s
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.05)

    def cmd_send_only(self, api_id, param=None):
        """发布即忘的指令"""
        req = Request()
        req.header.identity.api_id = api_id
        if param:
            req.parameter = json.dumps(param)
        self.sport_pub.publish(req)
        print(f"  发送: API_ID={api_id} param={param}")

    # ===== 菜单功能 =====

    def menu_auto_recovery_get(self):
        print("\n--- 查询自动恢复状态 ---")
        resp = self.publish_and_wait(self.sport_pub, 2055)
        if resp and resp.data:
            try:
                data = json.loads(resp.data)
                status = data.get('data', 'unknown')
                print(f"  自动恢复状态: {status}")
            except:
                print(f"  原始响应: {resp.data[:200]}")
        else:
            print("  ⚠️  无响应（可能需要 Humble 环境）")

    def menu_auto_recovery_set(self):
        print("\n--- 设置自动恢复 ---")
        choice = input("  启用自动恢复？(y/N): ").strip().lower()
        flag = choice == 'y'
        self.cmd_send_only(2054, {"data": flag})

    def menu_speed_level(self):
        print("\n--- 设置速度挡位 ---")
        try:
            level = int(input("  请输入挡位 (整数): ").strip())
            self.cmd_send_only(1015, {"data": level})
        except ValueError:
            print("  ❌ 无效输入")

    def menu_switch_joystick(self):
        print("\n--- 切换摇杆控制 ---")
        choice = input("  启用摇杆？(y/N): ").strip().lower()
        flag = choice == 'y'
        self.cmd_send_only(1027, {"data": flag})

    def menu_avoid_mode(self):
        print("\n--- 切换避障模式 ---")
        self.cmd_send_only(2058)
        print("  已发送切换指令")

    def menu_gait_mode(self):
        print("\n--- 步态模式 ---")
        gaits = {
            '1': ('StaticWalk (静态步行)', 1061),
            '2': ('TrotRun (小跑)', 1062),
            '3': ('EconomicGait (节能)', 1063),
            '4': ('FreeWalk (自由行走)', 2045),
            '5': ('ClassicWalk (经典)', 2049),
        }
        for k, (name, _) in gaits.items():
            print(f"  [{k}] {name}")
        choice = input("  选择: ").strip()
        if choice in gaits:
            name, api_id = gaits[choice]
            if api_id >= 2045:
                flag_choice = input("  启用？(y/N): ").strip().lower() == 'y'
                self.cmd_send_only(api_id, {"data": flag_choice})
            else:
                self.cmd_send_only(api_id)
        else:
            print("  取消")

    # ===== Humble API =====

    def menu_service_list(self):
        if not self.humble_mode:
            print("  ⚠️  RobotState API 需要 --humble 模式")
            return
        print("\n--- 获取服务列表 ---")
        resp = self.publish_and_wait(self.state_pub, 1003)
        if resp and resp.data:
            try:
                services = json.loads(resp.data)
                print(f"  服务列表 ({len(services)} 个):")
                for svc in services:
                    print(f"    - name={svc.get('name', '?')} "
                          f"status={svc.get('status', '?')} "
                          f"protect={svc.get('protect', '?')}")
            except:
                print(f"  原始响应: {resp.data[:300]}")
        else:
            print("  ⚠️  无响应")

    def menu_service_switch(self):
        if not self.humble_mode:
            print("  ⚠️  RobotState API 需要 --humble 模式")
            return
        print("\n--- 服务开关 ---")
        name = input("  服务名 (如 sport_mode): ").strip()
        if not name:
            return
        sw = input("  开关 (1=开, 0=关): ").strip()
        try:
            sw = int(sw)
        except ValueError:
            return
        resp = self.publish_and_wait(self.state_pub, 1001, {"name": name, "switch": sw})
        if resp and resp.data:
            try:
                data = json.loads(resp.data)
                print(f"  响应: {data}")
            except:
                print(f"  {resp.data[:200]}")
        else:
            print("  ⚠️  无响应")

    def menu_report_freq(self):
        if not self.humble_mode:
            print("  ⚠️  RobotState API 需要 --humble 模式")
            return
        print("\n--- 设置报告频率 ---")
        try:
            interval = int(input("  间隔 (s): ").strip())
            duration = int(input("  时长 (s): ").strip())
            req = Request()
            req.header.identity.api_id = 1002
            req.parameter = json.dumps({"interval": interval, "duration": duration})
            self.state_pub.publish(req)
            print(f"  已发送: interval={interval}, duration={duration}")
        except ValueError:
            print("  ❌ 无效输入")

    def show_status(self):
        if self.latest_state:
            mode_map = {0: "idle", 1: "balanceStand", 2: "pose", 3: "locomotion",
                        5: "lieDown", 6: "jointLock", 7: "damping", 8: "recoveryStand"}
            gait_map = {0: "idle", 1: "trot", 2: "run", 3: "climbStair", 4: "downStair"}
            mode = mode_map.get(self.latest_state.mode, str(self.latest_state.mode))
            gait = gait_map.get(self.latest_state.gait_type, str(self.latest_state.gait_type))
            print(f"\n--- 机器人状态 ---")
            print(f"  模式: {mode}  步态: {gait}")
            print(f"  位置: ({self.latest_state.position[0]:.2f}, {self.latest_state.position[1]:.2f})")
            rpy = self.latest_state.imu_state.rpy
            print(f"  RPY: ({rpy[0]:.2f}, {rpy[1]:.2f}, {rpy[2]:.2f})")

    def run_menu(self):
        menu_items = [
            ("s",  "显示机器人状态", self.show_status),
            ("1",  "查询自动恢复 (AutoRecoveryGet)", self.menu_auto_recovery_get),
            ("2",  "设置自动恢复 (AutoRecoverySet)", self.menu_auto_recovery_set),
            ("3",  "设置速度挡位 (SpeedLevel)", self.menu_speed_level),
            ("4",  "切换摇杆控制 (SwitchJoystick)", self.menu_switch_joystick),
            ("5",  "切换避障模式 (SwitchAvoidMode)", self.menu_avoid_mode),
            ("6",  "步态模式选择", self.menu_gait_mode),
        ]

        if self.humble_mode:
            menu_items += [
                ("7", "获取服务列表 (ServiceList)", self.menu_service_list),
                ("8", "服务开关 (ServiceSwitch)", self.menu_service_switch),
                ("9", "设置报告频率 (SetReportFreq)", self.menu_report_freq),
            ]

        menu_items.append(("q", "退出", None))

        while rclpy.ok():
            print("\n" + "=" * 50)
            print("  Go2 系统配置")
            print("=" * 50)
            for key, desc, _ in menu_items:
                print(f"  [{key}] {desc}")

            choice = input("\n  选择: ").strip().lower()
            for key, _, func in menu_items:
                if choice == key:
                    if func is None:
                        return
                    func()
                    break
            else:
                print("  ❌ 无效选项")


def main():
    humble = '--humble' in sys.argv
    rclpy.init(args=sys.argv)
    tester = RobotConfigTest(humble_mode=humble)

    print("\n" + "=" * 50)
    print(f"  Go2 系统配置测试  {'(Humble 扩展)' if humble else '(基础)'}")
    print("=" * 50)

    if humble:
        print("  ℹ️  已启用 RobotStateClient API (Humble only)")

    try:
        tester.wait_spin(1)
        tester.run_menu()
    except KeyboardInterrupt:
        print("\n\n退出。")
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()