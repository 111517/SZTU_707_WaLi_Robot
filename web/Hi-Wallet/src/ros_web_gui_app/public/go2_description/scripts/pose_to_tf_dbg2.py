import time
import traceback
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from tf2_ros import TransformBroadcaster
from geometry_msgs.msg import TransformStamped

class PoseToTF(Node):
    def __init__(self):
        super().__init__('pose_to_tf_dbg2')
        self.br = TransformBroadcaster(self)
        self.sub = self.create_subscription(PoseStamped, '/utlidar/robot_pose', self.cb, 10)
        self.get_logger().info('PoseToTF_DBG2 started, subscribing /utlidar/robot_pose')

    def cb(self, msg: PoseStamped):
        self.get_logger().info(f'received pose stamp={msg.header.stamp.sec}.{msg.header.stamp.nanosec} frame_id={msg.header.frame_id}')
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = msg.header.frame_id if msg.header.frame_id else 'odom'
        t.child_frame_id = 'base'
        t.transform.translation.x = msg.pose.position.x
        t.transform.translation.y = msg.pose.position.y
        t.transform.translation.z = msg.pose.position.z
        t.transform.rotation = msg.pose.orientation
        self.br.sendTransform(t)


def run_once():
    rclpy.init()
    node = PoseToTF()
    try:
        while rclpy.ok():
            try:
                rclpy.spin_once(node, timeout_sec=1.0)
            except Exception as e:
                node.get_logger().error(f'spin_once exception: {e}')
                traceback.print_exc()
                raise
            time.sleep(0.01)
    finally:
        try:
            rclpy.shutdown()
        except Exception as e:
            print('shutdown error:', e)


def main():
    attempts = 0
    while True:
        attempts += 1
        try:
            print('Attempt', attempts, 'starting rclpy')
            run_once()
        except Exception as e:
            print('run_once failed:', e)
            traceback.print_exc()
        print('Sleeping before retry...')
        time.sleep(1.0)

if __name__ == '__main__':
    main()
