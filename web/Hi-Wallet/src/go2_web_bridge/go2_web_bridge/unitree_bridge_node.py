# Copyright (c) 2024, RoboVerse community
# SPDX-License-Identifier: BSD-3-Clause

"""
Bridge all official unitree_ros2 topics to standard ROS2 types.

Converts unitree_go custom message types to standard sensor_msgs/nav_msgs
so that rosbridge, RViz2, and web clients don't need unitree_ros2 sourced.

Integrates lowstate_to_joint_states + pose_to_tf logic for RViz2 compatibility:
  - /lowstate → /joint_states (direct motor order 0-11, pos+vel+effort)
  - /utlidar/robot_pose + /utlidar/robot_odom → TF odom→base (timer-driven, 20Hz)

Usage:
  source /opt/ros/humble/setup.bash
  source /root/unitree_ros2/setup.sh       # needed to subscribe to unitree types
  ros2 run go2_robot_sdk unitree_bridge_node
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy

from geometry_msgs.msg import PoseStamped, TransformStamped
from sensor_msgs.msg import JointState, PointCloud2, Imu as RosImu, BatteryState, Image, CameraInfo
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_msgs.msg import Float32, String, Bool, Int32
from tf2_ros import TransformBroadcaster

from unitree_go.msg import LowState, SportModeState, UwbState, UwbSwitch, Go2FrontVideoData


class UnitreeBridgeNode(Node):
    """Bridges ALL official unitree topics to standard ROS2 types.

    Joint mapping uses direct motor order (0-11) to match the GO2_URDF
    link/joint tree verified with RViz2 RobotModel.
    """

    JOINT_NAMES = [
        'FL_hip_joint', 'FL_thigh_joint', 'FL_calf_joint',
        'FR_hip_joint', 'FR_thigh_joint', 'FR_calf_joint',
        'RL_hip_joint', 'RL_thigh_joint', 'RL_calf_joint',
        'RR_hip_joint', 'RR_thigh_joint', 'RR_calf_joint',
    ]

    def __init__(self):
        super().__init__('unitree_bridge_node')
        qos = QoSProfile(depth=10)
        be = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST, depth=1)

        # === Standard publishers ===
        self.joint_pub = self.create_publisher(JointState, 'joint_states', qos)
        self.odom_pub = self.create_publisher(Odometry, 'odom', qos)
        self.imu_pub = self.create_publisher(RosImu, 'imu/data', qos)
        self.cloud_pub = self.create_publisher(PointCloud2, 'point_cloud2', be)
        self.tf_broadcaster = TransformBroadcaster(self, qos=qos)

        # Battery & power
        self.battery_pub = self.create_publisher(BatteryState, 'battery_state', qos)
        self.battery_voltage_pub = self.create_publisher(Float32, 'battery/voltage', qos)
        self.battery_current_pub = self.create_publisher(Float32, 'battery/current', qos)
        self.battery_percent_pub = self.create_publisher(Float32, 'battery/percent', qos)

        # Robot state as standard types
        self.gait_type_pub = self.create_publisher(Int32, 'robot/gait_type', qos)
        self.body_height_pub = self.create_publisher(Float32, 'robot/body_height', qos)
        self.velocity_x_pub = self.create_publisher(Float32, 'robot/velocity/x', qos)
        self.velocity_y_pub = self.create_publisher(Float32, 'robot/velocity/y', qos)
        self.velocity_yaw_pub = self.create_publisher(Float32, 'robot/velocity/yaw', qos)
        self.foot_force_pub = self.create_publisher(Float32, 'robot/foot_force', qos)

        # UWB & sensors
        self.uwb_state_pub = self.create_publisher(String, 'uwb_state', qos)
        self.uwb_switch_pub = self.create_publisher(Bool, 'uwb_switch', qos)

        # Diagnostics
        self.diag_pub = self.create_publisher(DiagnosticArray, 'diagnostics', qos)

        # === Pose → TF state (timer-driven, integrated from pose_to_tf.py) ===
        self.latest_frame_id = 'odom'
        self.latest_pose = None
        self.pose_source = 'none'
        self.create_timer(0.05, self._publish_latest_tf)

        # === Subscribers to official unitree topics ===
        self.create_subscription(LowState, '/lowstate', self._on_lowstate, qos)
        self.create_subscription(SportModeState, '/sportmodestate', self._on_sport_state, qos)
        self.create_subscription(PoseStamped, '/utlidar/robot_pose', self._on_pose, qos)
        self.create_subscription(Odometry, '/utlidar/robot_odom', self._on_odom, qos)
        self.create_subscription(PointCloud2, '/utlidar/cloud', self._on_cloud, be)
        self.create_subscription(UwbState, '/uwbstate', self._on_uwb_state, qos)
        self.create_subscription(UwbSwitch, '/uwbswitch', self._on_uwb_switch, qos)

        # Passthrough relays (std_msgs/String topics -> republish under standard names)
        self._relay_sub(self, '/servicestate', String, 'robot/service_state', qos)
        self._relay_sub(self, '/lf/battery_alarm', String, 'robot/battery_alarm', qos)
        self._relay_sub(self, '/gas_sensor', String, 'sensor/gas', qos)
        self._relay_sub(self, '/gpt_state', String, 'ai/gpt_state', qos)

        # === Throttle / rate-limiting state ===
        self._last_publish = {}
        self._throttle_intervals = {}

        throttle_defaults = {
            'throttle.joint_states': 0.05,    # 20 Hz  – smooth robot model animation
            'throttle.odom':         0.05,    # 20 Hz  – smooth TF / position tracking
            'throttle.imu':          0.1,     # 10 Hz  – orientation display
            'throttle.point_cloud2': 0.2,     #  5 Hz  – large messages, viz sufficient
            'throttle.velocity':     0.1,     # 10 Hz  – velocity indicators
            'throttle.body_height':  1.0,     #  1 Hz  – changes gradually
            'throttle.gait_type':    0.5,     #  2 Hz  – changes very rarely
            'throttle.foot_force':   1.0,     #  1 Hz  – monitoring metric
            'throttle.battery':      120.0,   # 1/2min – drifts over minutes
            'throttle.diagnostics':  10.0,    # 0.1 Hz – status logging, not real-time
        }
        for name, default in throttle_defaults.items():
            self.declare_parameter(name, default)
            self._throttle_intervals[name] = (
                self.get_parameter(name).get_parameter_value().double_value)

        self.get_logger().info(
            'UnitreeBridgeNode: bridging ALL unitree topics to standard ROS2 types '
            '(joints: direct 0-11, TF: timer 20Hz, frame: odom→base)')

    def _relay_sub(self, node, src_topic, src_type, dst_topic, qos):
        """Create a subscriber that republishes same-type messages to a new topic."""
        pub = node.create_publisher(src_type, dst_topic, qos)
        node.create_subscription(src_type, src_topic, lambda msg: pub.publish(msg), qos)

    def _should_publish(self, throttle_key: str) -> bool:
        """Return True if the throttle interval for *throttle_key* has elapsed
        since the last publish (or on first call). Updates the last-publish
        timestamp when returning True."""
        now = self.get_clock().now()
        interval = self._throttle_intervals.get(throttle_key)
        if interval is None:
            return True  # no throttle configured for this key

        last = self._last_publish.get(throttle_key)
        if last is None:
            self._last_publish[throttle_key] = now
            return True

        elapsed_s = (now - last).nanoseconds * 1e-9
        if elapsed_s >= interval:
            self._last_publish[throttle_key] = now
            return True
        return False

    # ── LowState → joint_states + battery + IMU ──────────────────────

    def _on_lowstate(self, msg: LowState) -> None:
        if len(msg.motor_state) < 12:
            return
        now = self.get_clock().now().to_msg()

        # JointState — direct motor order 0-11 matching GO2_URDF joint sequence
        if self._should_publish('throttle.joint_states'):
            js = JointState()
            js.header.stamp = now
            js.header.frame_id = ''
            js.name = list(self.JOINT_NAMES)
            js.position = [float(msg.motor_state[i].q) for i in range(12)]
            js.velocity = [float(msg.motor_state[i].dq) for i in range(12)]
            js.effort = [float(msg.motor_state[i].tau_est) for i in range(12)]
            self.joint_pub.publish(js)

        # Battery — throttled to ~1/min (drifts slowly)
        if self._should_publish('throttle.battery'):
            v, a = float(msg.power_v), float(msg.power_a)
            bs = BatteryState()
            bs.header.stamp = now
            bs.voltage = v
            bs.current = a
            pct = min(100.0, max(0.0, ((v - 22.0) / (29.4 - 22.0)) * 100.0))
            bs.percentage = pct
            bs.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
            self.battery_pub.publish(bs)
            self.battery_voltage_pub.publish(Float32(data=v))
            self.battery_current_pub.publish(Float32(data=a))
            self.battery_percent_pub.publish(Float32(data=pct))

        # IMU — throttled to 10 Hz
        if self._should_publish('throttle.imu'):
            imu = msg.imu_state
            rimu = RosImu()
            rimu.header.stamp = now
            rimu.header.frame_id = 'imu'
            rimu.orientation.x = float(imu.quaternion[1])
            rimu.orientation.y = float(imu.quaternion[2])
            rimu.orientation.z = float(imu.quaternion[3])
            rimu.orientation.w = float(imu.quaternion[0])
            rimu.angular_velocity.x = float(imu.gyroscope[0])
            rimu.angular_velocity.y = float(imu.gyroscope[1])
            rimu.angular_velocity.z = float(imu.gyroscope[2])
            rimu.linear_acceleration.x = float(imu.accelerometer[0])
            rimu.linear_acceleration.y = float(imu.accelerometer[1])
            rimu.linear_acceleration.z = float(imu.accelerometer[2])
            self.imu_pub.publish(rimu)

        # Foot force (average of 4 feet) — throttled to 1 Hz
        if self._should_publish('throttle.foot_force'):
            ff = sum(abs(float(f)) for f in msg.foot_force) / 4.0
            self.foot_force_pub.publish(Float32(data=ff))

    # ── SportModeState → gait + body + velocity ──────────────────────

    def _on_sport_state(self, msg: SportModeState) -> None:
        now = self.get_clock().now().to_msg()

        # IMU from sport state (higher rate than lowstate) — throttled to 10 Hz
        if self._should_publish('throttle.imu'):
            imu = msg.imu_state
            rimu = RosImu()
            rimu.header.stamp = now
            rimu.header.frame_id = 'imu'
            rimu.orientation.x = float(imu.quaternion[1])
            rimu.orientation.y = float(imu.quaternion[2])
            rimu.orientation.z = float(imu.quaternion[3])
            rimu.orientation.w = float(imu.quaternion[0])
            rimu.angular_velocity.x = float(imu.gyroscope[0])
            rimu.angular_velocity.y = float(imu.gyroscope[1])
            rimu.angular_velocity.z = float(imu.gyroscope[2])
            rimu.linear_acceleration.x = float(imu.accelerometer[0])
            rimu.linear_acceleration.y = float(imu.accelerometer[1])
            rimu.linear_acceleration.z = float(imu.accelerometer[2])
            self.imu_pub.publish(rimu)

        # Robot motion state — separate throttle per semantic group
        if self._should_publish('throttle.gait_type'):
            self.gait_type_pub.publish(Int32(data=int(msg.gait_type)))

        if self._should_publish('throttle.body_height'):
            self.body_height_pub.publish(Float32(data=float(msg.body_height)))

        if self._should_publish('throttle.velocity'):
            self.velocity_x_pub.publish(Float32(data=float(msg.velocity[0])))
            self.velocity_y_pub.publish(Float32(data=float(msg.velocity[1])))
            self.velocity_yaw_pub.publish(Float32(data=float(msg.yaw_speed)))

        # Diagnostics — throttled to 0.1 Hz (every 10 s)
        if self._should_publish('throttle.diagnostics'):
            diag = DiagnosticArray()
            diag.header.stamp = now
            s = DiagnosticStatus()
            s.name = 'Go2 Sport Mode'
            s.level = DiagnosticStatus.OK
            s.message = f'Gait {msg.gait_type} Body {msg.body_height:.2f}m'
            s.values = [
                KeyValue(key='mode', value=str(msg.mode)),
                KeyValue(key='gait_type', value=str(msg.gait_type)),
                KeyValue(key='body_height', value=f'{msg.body_height:.3f}'),
                KeyValue(key='velocity_x', value=f'{msg.velocity[0]:.2f}'),
                KeyValue(key='velocity_y', value=f'{msg.velocity[1]:.2f}'),
                KeyValue(key='yaw_speed', value=f'{msg.yaw_speed:.2f}'),
                KeyValue(key='foot_raise_height', value=f'{msg.foot_raise_height:.3f}'),
                KeyValue(key='position_x', value=f'{msg.position[0]:.3f}'),
                KeyValue(key='position_y', value=f'{msg.position[1]:.3f}'),
                KeyValue(key='position_z', value=f'{msg.position[2]:.3f}'),
            ]
            diag.status.append(s)
            self.diag_pub.publish(diag)

    # ── Pose → TF (integrated from pose_to_tf.py) ────────────────────

    def _send_tf(self, frame_id: str, pose) -> None:
        """Publish a single odom→base transform."""
        tf = TransformStamped()
        tf.header.stamp = self.get_clock().now().to_msg()
        tf.header.frame_id = frame_id if frame_id else 'odom'
        tf.child_frame_id = 'base'
        tf.transform.translation.x = pose.position.x
        tf.transform.translation.y = pose.position.y
        tf.transform.translation.z = pose.position.z
        tf.transform.rotation = pose.orientation
        self.tf_broadcaster.sendTransform(tf)

    def _publish_latest_tf(self) -> None:
        """Timer callback — publish the latest known pose as TF at 20 Hz."""
        if self.latest_pose is None:
            pose = PoseStamped().pose
            self._send_tf('odom', pose)
            return
        self._send_tf(self.latest_frame_id, self.latest_pose)

    def _on_pose(self, msg: PoseStamped) -> None:
        """Handle /utlidar/robot_pose (primary pose source)."""
        self.latest_frame_id = msg.header.frame_id or 'odom'
        self.latest_pose = msg.pose
        if self.pose_source != 'pose':
            self.pose_source = 'pose'
            self.get_logger().info(f'Pose source: PoseStamped (frame={self.latest_frame_id})')

        # Publish odometry — throttled to 20 Hz
        if self._should_publish('throttle.odom'):
            now = self.get_clock().now().to_msg()
            odom = Odometry()
            odom.header.stamp = now
            odom.header.frame_id = self.latest_frame_id
            odom.child_frame_id = 'base'
            odom.pose.pose.position.x = msg.pose.position.x
            odom.pose.pose.position.y = msg.pose.position.y
            odom.pose.pose.position.z = msg.pose.position.z
            odom.pose.pose.orientation = msg.pose.orientation
            self.odom_pub.publish(odom)

    def _on_odom(self, msg: Odometry) -> None:
        """Handle /utlidar/robot_odom (fallback pose source)."""
        self.latest_frame_id = msg.header.frame_id or 'odom'
        self.latest_pose = msg.pose.pose
        if self.pose_source != 'odom':
            self.pose_source = 'odom'
            self.get_logger().info(f'Pose source: Odometry (frame={self.latest_frame_id})')

    # ── LiDAR passthrough (throttled to 5 Hz) ─────────────────────────

    def _on_cloud(self, msg: PointCloud2) -> None:
        if self._should_publish('throttle.point_cloud2'):
            self.cloud_pub.publish(msg)

    # ── UWB sensors ─────────────────────────────────────────────────

    def _on_uwb_state(self, msg: UwbState) -> None:
        self.uwb_state_pub.publish(String(data=str(msg)))

    def _on_uwb_switch(self, msg: UwbSwitch) -> None:
        self.uwb_switch_pub.publish(Bool(data=bool(msg.enabled)))


def main():
    rclpy.init()
    node = UnitreeBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
