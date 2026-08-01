#!/usr/bin/env python3
"""
Vision Pose Relay: bridges T265 /camera/pose/sample → /mavros/vision_pose/pose.
Converts nav_msgs/Odometry to geometry_msgs/PoseStamped with correct frame_id
and QoS matching for MAVROS.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry


class VisionPoseRelay(Node):
    def __init__(self):
        super().__init__("vision_pose_relay")

        # MAVROS vision_pose expects BEST_EFFORT QoS
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub = self.create_publisher(PoseStamped, "/mavros/vision_pose/pose", qos)

        # T265 pose/sample is Odometry with RELIABLE QoS
        self.create_subscription(
            Odometry, "/camera/pose/sample", self.callback, 10)
        self.get_logger().info("VisionPoseRelay started (T265 → MAVROS)")

    def callback(self, msg: Odometry):
        ps = PoseStamped()
        ps.header.stamp = msg.header.stamp
        ps.header.frame_id = "map"
        ps.pose = msg.pose.pose
        self.pub.publish(ps)


def main():
    rclpy.init()
    node = VisionPoseRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
