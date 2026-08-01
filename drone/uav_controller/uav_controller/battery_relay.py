#!/usr/bin/env python3
"""
Battery relay: reads /mavros/sys_status and publishes /mavros/battery
as sensor_msgs/BatteryState. No UDP bridge needed.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import BatteryState
from mavros_msgs.msg import SysStatus


class BatteryRelay(Node):
    def __init__(self):
        super().__init__("battery_relay")
        self.pub = self.create_publisher(BatteryState, "/mavros/battery", 10)
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(SysStatus, "/mavros/sys_status", self.callback, qos)
        self.get_logger().info("BatteryRelay started (subscribing /mavros/sys_status)")

    def callback(self, msg: SysStatus):
        bs = BatteryState()
        bs.header.stamp = self.get_clock().now().to_msg()
        bs.voltage = msg.voltage_battery / 1000.0
        bs.current = -(msg.current_battery * 0.01) if msg.current_battery > 0 else msg.current_battery * 0.01
        # MAVROS SysStatus.battery_remaining is 0.0-1.0, web panel expects 0-100
        bs.percentage = msg.battery_remaining * 100.0 if msg.battery_remaining >= 0 else float("nan")
        bs.present = True
        bs.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LIPO
        self.pub.publish(bs)


def main():
    rclpy.init()
    node = BatteryRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
