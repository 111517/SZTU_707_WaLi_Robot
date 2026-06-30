import time
import traceback
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from tf2_ros import TransformBroadcaster
from geometry_msgs.msg import TransformStamped

class PoseToTF(Node):
    def __init__(self):
        super().__init__('pose_to_tf_dbg')
        self.br = TransformBroadcaster(self)
        self.sub = self.create_subscription(PoseStamped, '/utlidar/robot_pose', self.cb, 10)
        self.get_logger().info('PoseToTF_DBG started, subscribing /utlidar/robot_pose')
        self.msg_count = 0

    def cb(self, msg: PoseStamped):
        self.msg_count += 1
        self.get_logger().info(f'received pose #{self.msg_count} stamp={msg.header.stamp.sec}.{msg.header.stamp.nanosec} frame_id={msg.header.frame_id}')
        t = TransformStamped()
        try:
            t.header.stamp = self.get_clock().now().to_msg()
            t.header.frame_id = msg.header.frame_id if msg.header.frame_id else 'odom'
            t.child_frame_id = 'base'
            t.transform.translation.x = msg.pose.position.x
            t.transform.translation.y = msg.pose.position.y
            t.transform.translation.z = msg.pose.position.z
            t.transform.rotation = msg.pose.orientation
            self.br.sendTransform(t)
        except Exception as e:
            self.get_logger().error('Exception in cb: %s' % str(e))
            traceback.print_exc()


def main(args=None):
    print('DEBUG: about to rclpy.init()')
    try:
        rclpy.init(args=args)
    except Exception as e:
        print('rclpy.init failed:', e)
        traceback.print_exc()
        return
    print('DEBUG: rclpy.init done')
    node = None
    try:
        node = PoseToTF()
        print('DEBUG: node created')
        # spin loop with spin_once to capture exceptions
        while rclpy.ok():
            try:
                rclpy.spin_once(node, timeout_sec=1.0)
            except Exception as e:
                print('spin_once exception:', e)
                traceback.print_exc()
                break
            time.sleep(0.01)
    except Exception as e:
        print('Exception in main loop:', e)
        traceback.print_exc()
    finally:
        print('DEBUG: shutting down rclpy')
        try:
            rclpy.shutdown()
        except Exception as e:
            print('rclpy.shutdown exception:', e)
            traceback.print_exc()

if __name__ == '__main__':
    main()
