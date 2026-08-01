#!/usr/bin/env python3
"""
UAV 控制节点 — ROS2 (rclpy) 迁移版
=====================================
UGV → /ugv/uav_command (Topic) → 本节点 → /mavros/setpoint_position/local → MAVROS → PX4
                                    ↑
    /mavros/state ←── 飞控状态（模式、解锁状态、是否连接）
    /mavros/battery ←── 电池电量
    /mavros/local_position/pose ←── 当前位置（用于判断到达、返航到位）
    /mavros/rc/in ←── 遥控器通道值（检测人为接管）

ROS1 → ROS2 关键变化：
  - rospy.init_node() → class Node 子类
  - rospy.Subscriber() → self.create_subscription()
  - rospy.ServiceProxy() → self.create_client() (同步 → 异步)
  - rospy.Time.now() → self.get_clock().now()
  - rospy.loginfo() → self.get_logger().info()
"""
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State, RCIn
from sensor_msgs.msg import BatteryState
from mavros_msgs.srv import CommandBool, SetMode
from uav_controller_interfaces.msg import UavCommand


class UavController(Node):
    NORMAL, FAILSAFE, LANDING = range(3)

    def __init__(self):
        super().__init__('uav_controller_node')

        # ===== 安全参数 =====
        self.TIMEOUT       = 180.0
        self.BATTERY_MIN   = 0.20
        self.X_LIMIT       = 10.0
        self.Y_LIMIT       = 10.0
        self.Z_MAX         = 5.0

        # 启动时是否自动 ARM（默认否，需显式启用或外部指令触发）
        self.declare_parameter("auto_arm", False)
        self.ARRIVE_TOL    = 0.5

        self.last_cmd_time = self.get_clock().now()
        self.battery_level = 1.0
        self.state = self.NORMAL
        self.current_state = State()
        self._shutdown = False
        self._offboard_confirmed = False  # OFFBOARD 真正生效后才置 True

        # 当前位置和遥控器
        self.current_pos = (0.0, 0.0, 0.0)
        self.rc_channels = [0] * 8

        # 限速日志用
        self._last_log = {}

        # ===== QoS =====
        sensor_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        # ===== 订阅 =====
        self.create_subscription(State, '/mavros/state', self.state_cb, 10)
        self.create_subscription(
            PoseStamped, '/mavros/local_position/pose',
            self.local_pos_cb, sensor_qos
        )
        self.create_subscription(
            BatteryState, '/mavros/battery', self.battery_cb, sensor_qos
        )
        self.create_subscription(RCIn, '/mavros/rc/in', self.rc_cb, 10)
        self.create_subscription(
            UavCommand, '/ugv/uav_command', self.command_cb, 10
        )

        # ===== 发布 =====
        self.local_pos_pub = self.create_publisher(
            PoseStamped, '/mavros/setpoint_position/local', 10
        )

        # ===== Service 客户端（ROS2 异步）=====
        self.arming_client   = self.create_client(CommandBool, '/mavros/cmd/arming')
        self.set_mode_client = self.create_client(SetMode, '/mavros/set_mode')

        self.target = PoseStamped()
        self.target.header.frame_id = "map"

        # 初始化完成，_init_offboard 在 main() 中调用（等 spin 启动后）
        self.get_logger().info("UavController 初始化完毕，等待 offboard 启动…")

    # ============================================================
    #  初始化 Offboard（需在 spin 启动后调用）
    # ============================================================

    def init_offboard(self):
        """预发 100 setpoint + 切 Offboard + 解锁"""
        import time

        # 等待 mavros 服务上线（可能需要数十秒）
        self.get_logger().info("等待 mavros 服务…")
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if self.set_mode_client.wait_for_service(timeout_sec=2.0):
                break
            self.get_logger().info("  SetMode 服务尚未就绪，继续等待…")
        else:
            self.get_logger().error("SetMode service 不可用（30s 超时）")
            return False
        while time.time() < deadline:
            if self.arming_client.wait_for_service(timeout_sec=2.0):
                break
            self.get_logger().info("  Arming 服务尚未就绪，继续等待…")
        else:
            self.get_logger().error("CommandBool service 不可用（30s 超时）")
            return False

        self.get_logger().info("预发送 setpoint…")
        for _ in range(100):
            self.target.header.stamp = self.get_clock().now().to_msg()
            self.local_pos_pub.publish(self.target)
            time.sleep(0.05)

        # 切 Offboard
        req = SetMode.Request()
        req.custom_mode = 'OFFBOARD'
        future = self.set_mode_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done() or not future.result().mode_sent:
            self.get_logger().error("Offboard 模式切换失败！")
            return False
        self.get_logger().info("Offboard 模式已切换")

        # 验证 OFFBOARD 是否真正生效（真机可能因无 GPS/EKF 被拒绝）
        time.sleep(1.0)
        rclpy.spin_once(self, timeout_sec=0.5)
        actual_mode = str(self.current_state.mode).upper()
        if 'OFFBOARD' in actual_mode or 'AUTO' in actual_mode or 'CMODE' in actual_mode:
            self._offboard_confirmed = True
            self.get_logger().info(f"OFFBOARD 验证通过 (当前模式: {self.current_state.mode})")
        else:
            self.get_logger().warn(f"OFFBOARD 可能被 PX4 拒绝 (当前模式: {self.current_state.mode})，检查 GPS/EKF 状态")
            # 不 return False — 让控制器继续运行，后续可以重试

        # ARM：仅当 auto_arm 参数为 True 时自动解锁
        self.auto_arm = self.get_parameter("auto_arm").value
        if self.auto_arm:
            self.get_logger().info("auto_arm=True，自动解锁…")
            time.sleep(0.5)
            req2 = CommandBool.Request()
            req2.value = True
            future2 = self.arming_client.call_async(req2)
            rclpy.spin_until_future_complete(self, future2, timeout_sec=10.0)
            if not future2.done() or not future2.result().success:
                self.get_logger().error("解锁失败！")
                # 不 return False — 让控制器继续运行，后续可重试
            else:
                self.get_logger().info("ARM 成功！电机怠速中")
        else:
            self.get_logger().info("auto_arm=False，跳过自动解锁，等待外部指令…")
        return True

    # ============================================================
    #  回调
    # ============================================================

    def state_cb(self, msg):
        self.current_state = msg

    def battery_cb(self, msg):
        self.battery_level = msg.percentage

    def local_pos_cb(self, msg):
        p = msg.pose.position
        self.current_pos = (p.x, p.y, p.z)

    def rc_cb(self, msg):
        self.rc_channels = [c for c in msg.channels]

    def command_cb(self, msg):
        x = self._clamp(msg.x, -self.X_LIMIT, self.X_LIMIT)
        y = self._clamp(msg.y, -self.Y_LIMIT, self.Y_LIMIT)
        z = self._clamp(msg.z, 0, self.Z_MAX)

        if x != msg.x or y != msg.y or z != msg.z:
            self.get_logger().warn(f"目标点超出边界，已修正: ({x}, {y}, {z})")

        if msg.command == "land":
            self.state = self.LANDING
            return

        self.get_logger().info(f"收到指令: {msg.command} → ({x}, {y}, {z})")
        self.target.pose.position.x = x
        self.target.pose.position.y = y
        self.target.pose.position.z = z
        self.last_cmd_time = self.get_clock().now()

    # ============================================================
    #  安全检查 + 人为接管检测
    # ============================================================

    def _check_safety(self):
        # ── 人为接管检测 ──
        # PX4 解锁后可能从 OFFBOARD 进入 AUTO（位置控制），都是正常模式
        # 只有切到 MANUAL/STABILIZED/ACRO 等 RC 控制模式才算接管
        rc_modes = {'MANUAL', 'STABILIZED', 'ACRO', 'ALTCTL', 'RATTITUDE'}
        mode_str = str(self.current_state.mode).upper()
        is_rc_mode = any(m in mode_str for m in rc_modes)
        if is_rc_mode and self.state != self.LANDING and self._offboard_confirmed:
            self._log_throttle(
                f"检测到遥控器接管！当前模式: {self.current_state.mode}",
                'warn', 3.0, 'rc_takeover'
            )
            self._call_disarm()
            self._ctrl_timer.cancel()
            rclpy.shutdown()

        # ── 低电量迫降 ──
        if self.battery_level < self.BATTERY_MIN:
            self._log_throttle(
                f"低电量 {self.battery_level*100:.0f}%，强制降落！",
                'warn', 3.0, 'low_battery'
            )
            self.state = self.LANDING

        # ── 失联保护 ──
        dt = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        if dt > self.TIMEOUT and self.state == self.NORMAL:
            self._log_throttle(
                f"失联 {dt:.0f}s，触发返航！",
                'warn', 3.0, 'timeout'
            )
            self.state = self.FAILSAFE

    def _call_disarm(self):
        req = CommandBool.Request()
        req.value = False
        self.arming_client.call_async(req)

    # ============================================================
    #  辅助
    # ============================================================

    def _clamp(self, val, lo, hi):
        return max(lo, min(hi, val))

    def _distance_to(self, x, y, z):
        cx, cy, cz = self.current_pos
        return math.sqrt((cx - x)**2 + (cy - y)**2 + (cz - z)**2)

    def _log_throttle(self, msg, level, interval, key):
        """简易限速日志：同 key 消息最快 interval 秒输出一次"""
        now = self.get_clock().now().nanoseconds / 1e9
        if key in self._last_log and now - self._last_log[key] < interval:
            return
        self._last_log[key] = now
        getattr(self.get_logger(), level)(msg)

    def _sync_state(self, timeout=5.0):
        """等待 /mavros/state 首次回调更新 current_state，避免误判 RC 接管"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.current_state.connected:
                self.get_logger().info(f"飞控状态已同步: mode={self.current_state.mode}")
                return True
        self.get_logger().warn("飞控状态同步超时")
        return False

    # ============================================================
    #  主循环（Timer 回调，20Hz）
    # ============================================================

    def run(self):
        # 先启动 20Hz setpoint 流，防止 OFFBOARD 因断流退出
        self._ctrl_timer = self.create_timer(0.05, self._control_loop)
        self._sync_state()
        self._phase_start = self.get_clock().now()

        rclpy.spin(self)
        self._call_disarm()

    def _control_loop(self):
        self._check_safety()

        if self.state == self.NORMAL:
            self._phase_start = self.get_clock().now()

        elif self.state == self.FAILSAFE:
            self.target.pose.position.x = 0.0
            self.target.pose.position.y = 0.0
            self.target.pose.position.z = 2.0

            if self._distance_to(0, 0, 2.0) < self.ARRIVE_TOL:
                self.get_logger().info("已到达原点上方，开始降落")
                self.state = self.LANDING
                self._phase_start = self.get_clock().now()

        elif self.state == self.LANDING:
            self.target.pose.position.x = 0.0
            self.target.pose.position.y = 0.0
            self.target.pose.position.z = 0.0

            near_ground = self._distance_to(0, 0, 0) < 0.3
            dt = (self.get_clock().now() - self._phase_start).nanoseconds / 1e9
            timed_out = dt > 10.0
            if near_ground or timed_out:
                self._call_disarm()
                self.get_logger().info("已降落，电机上锁")
                self._ctrl_timer.cancel()
                rclpy.shutdown()
                return

        self.target.header.stamp = self.get_clock().now().to_msg()
        self.local_pos_pub.publish(self.target)


def main():
    rclpy.init()
    node = UavController()

    # 持续重试直到 OFFBOARD 初始化成功（MAVROS 可能需要 >30s）
    import time as _time
    while rclpy.ok():
        if node.init_offboard():
            break
        node.get_logger().warn("Offboard 初始化失败，10 秒后重试…")
        _time.sleep(10.0)

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
