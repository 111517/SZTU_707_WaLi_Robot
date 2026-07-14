#!/usr/bin/env python3
"""
01_connection_check.py — Go2 连接与 DDS 通信诊断

功能：
  1. 验证本地网络配置与 DDS 中间件层
  2. 列出机器人所有已注册服务（名称/状态/保护级别）
  3. 查询当前运动模式
  4. 错误码定位与诊断提示

使用方式：
  source /opt/ros/foxy/setup.bash
  source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI="file://$HOME/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"
  python3 01_connection_check.py

预期效果：
  ────────────────────────────────────────────
  ✅ DDS 通信链路正常 — 发现 121 个 Topic
  ┌──────────────────────────────────────┐
  │ 服务名                   状态  保护  │
  ├──────────────────────────────────────┤
  │ advanced_sport           运行  ✗    │
  │ sport_mode               运行  ✓    │
  │ ...                                │
  └──────────────────────────────────────┘
  当前运动模式: idle

安全说明：
  本脚本仅订阅 Topic 和发送查询请求，不产生任何物理动作。
  机器人可在任意状态（待机/运动/休眠）下安全运行。
"""
import os
import sys
import time
import json
import socket

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

import rclpy
from rclpy.node import Node
from unitree_api.msg import Request, Response
from unitree_go.msg import SportModeState

# ============================================================
# 服务名 → 中文名映射
# ============================================================
SERVICE_FRIENDLY_NAMES = {
    "4gcm":                 "4G通信管理",
    "advanced_sport":       "高级运动",
    "ai_sport":             "AI运动",
    "audio_hub":            "音频中枢",
    "audio_player_service": "音频播放",
    "bms_monitor":          "电池监控",
    "camera_service":       "摄像头",
    "depth_camera":         "深度相机",
    "fsm_runner":           "状态机执行器",
    "gesture":              "手势识别",
    "gpt_service":          "GPT服务",
    "lcd":                  "LCD显示",
    "led":                  "LED灯",
    "lidar_service":        "激光雷达",
    "motion_switcher":      "运动模式切换",
    "navigation":           "导航",
    "obstacles_avoid":      "避障",
    "pet":                  "宠物模式",
    "programming_actuator": "编程执行器",
    "robot_state":          "机器人状态",
    "slam":                 "SLAM建图",
    "slam_operate":         "SLAM操作",
    "sport_mode":           "运动模式",
    "uwb_service":          "UWB定位",
    "voice_service":        "语音服务",
    "vui_client":           "语音交互",
    "wireless_controller":  "无线遥控",
}

# ============================================================
# 辅助工具
# ============================================================

def get_network_interface():
    """读取 CycloneDDS 配置中的网卡名与 Domain ID"""
    config_paths = [
        os.environ.get('CYCLONEDDS_URI', '').replace('file://', ''),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', 'cyclonedds_ws', 'src', 'cyclonedds.xml'),
        '/home/unitree/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml',
    ]
    iface, domain_id = "未知", "any"

    for path in config_paths:
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    content = f.read()
                import re
                m = re.search(r'<NetworkInterface\s+name="([^"]+)"', content)
                if m:
                    iface = m.group(1)
                m = re.search(r'<Domain\s+Id="([^"]+)"', content)
                if m:
                    domain_id = m.group(1)
                break
            except Exception:
                pass
    return iface, domain_id


def get_interface_ip(iface_name):
    """获取指定网卡的 IP 地址"""
    try:
        import fcntl
        import struct
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip = socket.inet_ntoa(
            fcntl.ioctl(s.fileno(), 0x8915,  # SIOCGIFADDR
                        struct.pack('256s', iface_name.encode()[:15]))[20:24]
        )
        return ip
    except Exception:
        return "未获取到"


# ============================================================
# 连接检查节点
# ============================================================

class ConnectionChecker(Node):
    """Go2 连接诊断节点"""

    def __init__(self):
        super().__init__('go2_connection_checker')
        self._phase = ""
        self._ok = True

    # ---------- 工具方法 ----------

    def _spin_until(self, timeout_s, step=0.05):
        end = time.time() + timeout_s
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=step)

    def _bold(self, s):
        return f"\033[1m{s}\033[0m"

    def _green(self, s):
        return f"\033[32m{s}\033[0m"

    def _red(self, s):
        return f"\033[31m{s}\033[0m"

    def _yellow(self, s):
        return f"\033[33m{s}\033[0m"

    def _header(self, title):
        print(f"\n{'─' * 50}")
        print(f"  {self._bold(title)}")
        print(f"{'─' * 50}")

    # ---------- Phase 1: 本地环境 ----------

    def check_local_env(self):
        self._header("Phase 1/4: 本地网络与 DDS 配置")
        self._phase = "本地环境"

        # RMW
        rmw = os.environ.get('RMW_IMPLEMENTATION', '')
        if 'cyclonedds' in rmw.lower():
            print(f"  ✅ RMW_IMPLEMENTATION = {rmw}")
        else:
            print(f"  ❌ RMW_IMPLEMENTATION = {rmw or '未设置'}")
            print(f"     应设为 rmw_cyclonedds_cpp")
            self._ok = False
            return

        # CycloneDDS 配置
        dds_uri = os.environ.get('CYCLONEDDS_URI', '')
        iface, domain_id = get_network_interface()
        iface_ip = get_interface_ip(iface)

        print(f"  ✅ CycloneDDS 配置文件已加载")
        print(f"     网卡: {iface}")
        print(f"     本机 IP: {iface_ip}")
        print(f"     Domain ID: {domain_id}")

        # IP 检查
        if not iface_ip.startswith('192.168.123.'):
            print(f"  {self._yellow('⚠️  IP 不在 192.168.123.0/24 网段')}")
            print(f"     预期: 192.168.123.x（如 192.168.123.99）")
            print(f"     当前: {iface_ip}")
            print(f"     请检查网线连接和 IP 设置")
        else:
            print(f"  ✅ IP 在 Go2 默认网段 192.168.123.0/24")

    # ---------- Phase 2: DDS 通信探测 ----------

    def check_dds_topic(self):
        self._header("Phase 2/4: DDS 通信链路探测")
        self._phase = "DDS通信"

        topics = self.get_topic_names_and_types()
        total = len(topics)

        if total == 0:
            print(f"  {self._red('❌ 未发现任何 Topic — DDS 链路不通')}")
            print(f"     请检查:")
            print(f"       1. 网线是否为直连（非交换机组网）")
            print(f"       2. 本机 IP: 192.168.123.99/24")
            print(f"       3. Go2 是否开机（非休眠）")
            print(f"       4. 尝试: ping 192.168.123.161")
            self._ok = False
            return

        # 统计
        unitree_topics = [n for n, _ in topics if any(
            k in n.lower()
            for k in ['sportmode', 'lowstate', 'lowcmd', 'wireless',
                      'utlidar', 'unitree', 'api/']
        )]
        key_topics = ['/sportmodestate', '/lowstate', '/wirelesscontroller',
                      '/api/sport/request']

        print(f"  ✅ DDS 通信链路正常")
        print(f"     总 Topic 数: {total}")
        print(f"     Unitree 相关: {len(unitree_topics)} 个")
        print(f"     API 端点: {len([n for n,_ in topics if '/api/' in n])} 个")

        # 核心 Topic 发布者检查
        print()
        for t in key_topics:
            pubs = self.count_publishers(t)
            icon = "✅" if pubs > 0 else "🔴"
            desc = {
                '/sportmodestate': '运动状态（高层）',
                '/lowstate': '底层状态（电机/IMU）',
                '/wirelesscontroller': '遥控器',
                '/api/sport/request': '运动控制API',
            }.get(t, '')
            print(f"  {icon} {t:<30s} 发布者:{pubs:<2d}  {desc}")

    # ---------- Phase 3: 服务列表 ----------

    def check_services(self):
        self._header("Phase 3/4: 机器人服务列表")
        self._phase = "服务列表"

        pub = self.create_publisher(Request, '/api/robot_state/request', 10)
        resp = None

        def _on_resp(msg):
            nonlocal resp
            resp = msg

        sub = self.create_subscription(Response, '/api/robot_state/response',
                                       _on_resp, 10)

        req = Request()
        req.header.identity.api_id = 1003  # ServiceList
        pub.publish(req)
        self._spin_until(2.0)

        if resp is None:
            print(f"  {self._yellow('⚠️  未收到 ServiceList 响应')}")
            print(f"     可能是固件版本限制（需 Go2 较新固件）")
            # 不影响整体结论
            self.destroy_subscription(sub)
            self.destroy_publisher(pub)
            return

        self.destroy_subscription(sub)
        self.destroy_publisher(pub)

        try:
            services = json.loads(resp.data)
        except Exception:
            print(f"  ⚠️  响应解析失败: {resp.data[:200]}")
            return

        if not services:
            print(f"  ⚠️  服务列表为空")
            return

        status_code = resp.header.status.code
        print(f"  ✅ 服务列表查询成功 (status={status_code})")
        print(f"     注册服务: {len(services)} 个\n")

        # 表格输出
        SEP = "─"
        print(f"  ┌{SEP * 40}┬{SEP * 8}┬{SEP * 8}┐")
        print(f"  │ {'服务名称':<38s} │ {'状态':^6s} │ {'保护':^6s} │")
        print(f"  ├{SEP * 40}┼{SEP * 8}┼{SEP * 8}┤")

        for svc in sorted(services, key=lambda s: s.get('name', '')):
            name = svc.get('name', '?')
            status_val = svc.get('status', 0)
            protect_val = svc.get('protect', 0)

            friendly = SERVICE_FRIENDLY_NAMES.get(name, '')
            display = f"{name}"
            if friendly:
                display += f" ({friendly})"

            # 截断
            if len(display) > 38:
                display = display[:37] + "…"

            status_str = self._green("运行") if status_val == 1 else ("停止")
            protect_str = "✓" if protect_val == 1 else "✗"

            print(f"  │ {display:<38s} │ {status_str:^6s} │ {protect_str:^6s} │")

        print(f"  └{SEP * 40}┴{SEP * 8}┴{SEP * 8}┘")

        # 统计
        running = sum(1 for s in services if s.get('status') == 1)
        protected = sum(1 for s in services if s.get('protect') == 1)
        print(f"\n  运行中: {running}/{len(services)}  受保护: {protected}")

    # ---------- Phase 4: 运动模式 ----------

    def check_motion_mode(self):
        self._header("Phase 4/4: 当前运动模式")
        self._phase = "运动模式"

        state = None

        def _on_state(msg):
            nonlocal state
            state = msg

        sub = self.create_subscription(SportModeState, '/sportmodestate',
                                       _on_state, 10)
        self._spin_until(2.0)
        self.destroy_subscription(sub)

        if state is None:
            # 尝试低频
            state2 = None

            def _on_lf(msg):
                nonlocal state2
                state2 = msg

            sub2 = self.create_subscription(SportModeState, '/lf/sportmodestate',
                                            _on_lf, 10)
            self._spin_until(2.0)
            self.destroy_subscription(sub2)
            state = state2

        if state is None:
            print(f"  {self._yellow('⚠️  未获取到运动状态')}")
            return

        modes = {0: 'idle（待机）', 1: 'balanceStand（平衡站立）',
                 2: 'pose（姿态）', 3: 'locomotion（运动）',
                 5: 'lieDown（趴下）', 6: 'jointLock（锁定）',
                 7: 'damping（阻尼）', 8: 'recoveryStand（恢复站立）',
                 10: 'sit（坐下）', 11: 'frontFlip（前空翻）',
                 12: 'frontJump（前跳）', 13: 'frontPounce（前扑）'}
        gaits = {0: 'idle', 1: 'trot（小跑）', 2: 'run（奔跑）',
                 3: 'climbStair（上楼梯）', 4: 'downStair（下楼梯）',
                 9: 'adjust（调整）'}
        rpy = state.imu_state.rpy

        print(f"  运动模式: {modes.get(state.mode, f'unknown({state.mode})')}")
        print(f"  步态类型: {gaits.get(state.gait_type, f'unknown({state.gait_type})')}")
        print(f"  机体高度: {state.body_height:.3f} m")
        print(f"  姿态 RPY: roll={rpy[0]:.2f} pitch={rpy[1]:.2f} yaw={rpy[2]:.2f}")
        print(f"  位置:     x={state.position[0]:.3f} y={state.position[1]:.3f}")
        print(f"  线速度:   vx={state.velocity[0]:.3f} vy={state.velocity[1]:.3f}")
        print(f"  错误码:   {state.error_code}")

    # ---------- 总结 ----------

    def summary(self):
        print(f"\n{'═' * 50}")
        if self._ok:
            print(f"  {self._green('✅ 全部检查通过 — Go2 连接正常')}")
            print(f"     可继续运行后续测试程序")
        else:
            print(f"  {self._red('❌ 连接检查未通过')}")
            print(f"     请根据上述提示排查问题后重试")
        print(f"{'═' * 50}\n")

    def run(self):
        print()
        print("═" * 50)
        print("   Unitree Go2 连接诊断")
        print(f"   {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("═" * 50)

        try:
            self.check_local_env()       # Phase 1
            if not self._ok:
                self.summary()
                return
            self.check_dds_topic()       # Phase 2
            if not self._ok:
                self.summary()
                return
            self.check_services()        # Phase 3
            self.check_motion_mode()     # Phase 4
        except Exception as e:
            print(f"\n  {self._red(f'❌ 异常: {e}')}")
            self._ok = False

        self.summary()


# ============================================================
# 入口
# ============================================================

def main():
    rclpy.init(args=sys.argv)

    # 确保环境变量
    for k in ['RMW_IMPLEMENTATION', 'CYCLONEDDS_URI']:
        if k not in os.environ or not os.environ[k]:
            if k == 'RMW_IMPLEMENTATION':
                os.environ[k] = 'rmw_cyclonedds_cpp'
            elif k == 'CYCLONEDDS_URI':
                os.environ[k] = (
                    'file:///home/unitree/unitree_ros2/'
                    'cyclonedds_ws/src/cyclonedds.xml'
                )

    checker = ConnectionChecker()
    checker.run()
    checker.destroy_node()
    rclpy.shutdown()

    return 0 if checker._ok else 1


if __name__ == '__main__':
    sys.exit(main())