import rclpy
from rclpy.context import Context
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from unitree_go.msg import LowState
from tf2_ros import TransformBroadcaster
import math


BODY_HEIGHT_OFFSET = 0.32


def quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> Quaternion:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)

    quaternion = Quaternion()
    quaternion.w = cr * cp * cy + sr * sp * sy
    quaternion.x = sr * cp * cy - cr * sp * sy
    quaternion.y = cr * sp * cy + sr * cp * sy
    quaternion.z = cr * cp * sy - sr * sp * cy
    return quaternion


def yaw_from_quaternion(quaternion: Quaternion) -> float:
    siny_cosp = 2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y)
    cosy_cosp = 1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z)
    return math.atan2(siny_cosp, cosy_cosp)


class PoseToTF(Node):
    def __init__(self, context: Context):
        super().__init__("pose_to_tf", context=context)
        self.br = TransformBroadcaster(self)
        self.latest_frame_id = "odom"
        self.latest_pose = None
        self.latest_imu_rpy = None
        self.source_name = "none"
        self.pose_sub = self.create_subscription(PoseStamped, "/utlidar/robot_pose", self.pose_cb, 10)
        self.odom_sub = self.create_subscription(Odometry, "/utlidar/robot_odom", self.odom_cb, 10)
        self.lowstate_sub = self.create_subscription(LowState, "/lowstate", self.lowstate_cb, 10)
        self.timer = self.create_timer(0.05, self.publish_latest_tf)
        self.get_logger().info("PoseToTF started, subscribing /utlidar/robot_pose, /utlidar/robot_odom and /lowstate")

    def lowstate_cb(self, msg: LowState):
        if hasattr(msg, "imu_state") and hasattr(msg.imu_state, "rpy") and len(msg.imu_state.rpy) >= 3:
            self.latest_imu_rpy = (
                float(msg.imu_state.rpy[0]),
                float(msg.imu_state.rpy[1]),
                float(msg.imu_state.rpy[2]),
            )

    def publish_tf(self, frame_id: str, pose):
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = frame_id if frame_id else "odom"
        transform.child_frame_id = "base"
        transform.transform.translation.x = pose.position.x
        transform.transform.translation.y = pose.position.y
        transform.transform.translation.z = pose.position.z
        if transform.transform.translation.z < 0.15:
            transform.transform.translation.z += BODY_HEIGHT_OFFSET

        if self.latest_imu_rpy is not None:
            roll, pitch, _ = self.latest_imu_rpy
            yaw = yaw_from_quaternion(pose.orientation)
            transform.transform.rotation = quaternion_from_rpy(roll, pitch, yaw)
        else:
            transform.transform.rotation = pose.orientation
        self.br.sendTransform(transform)

    def publish_latest_tf(self):
        if self.latest_pose is None:
            pose = PoseStamped().pose
            self.publish_tf("odom", pose)
            return
        self.publish_tf(self.latest_frame_id, self.latest_pose)

    def pose_cb(self, msg: PoseStamped):
        self.latest_frame_id = msg.header.frame_id or "odom"
        self.latest_pose = msg.pose
        if self.source_name != "pose":
            self.source_name = "pose"
            self.get_logger().info(f"Received PoseStamped from frame={self.latest_frame_id}")

    def odom_cb(self, msg: Odometry):
        self.latest_frame_id = msg.header.frame_id or "odom"
        self.latest_pose = msg.pose.pose
        if self.source_name != "odom":
            self.source_name = "odom"
            self.get_logger().info(f"Received Odometry from frame={self.latest_frame_id}")


def main(args=None):
    context = Context()
    rclpy.init(args=args, context=context)
    node = PoseToTF(context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        pass
    finally:
        executor.remove_node(node)
        node.destroy_node()
        rclpy.shutdown(context=context)


if __name__ == "__main__":
    main()
