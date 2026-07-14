#!/usr/bin/env python3
"""
test_01_connection.py — Go2 连接诊断测试

功能：
  1. 检查 ROS2 环境是否正确加载
  2. 列出 Go2 相关的所有 Topic
  3. 验证关键 Topic 是否有数据发布

使用方式：
  cd /home/unitree/unitree_ros2/analysis
  source ../setup.sh          # 或 source setup_local.sh
  python3 tests/test_01_connection.py

预期效果：
  ✅ 正常：显示 Go2 相关 Topic 列表及发布者数量
  ❌ 异常：提示网络未连接或 ROS2 环境配置错误
"""
import os
import sys

# 尝试加载 .env 配置
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

import rclpy
from rclpy.node import Node


class ConnectionTester(Node):
    """Go2 连接诊断节点"""

    def __init__(self):
        super().__init__('go2_connection_test')
        self.connected = False

    def run(self):
        print("\n" + "=" * 60)
        print("  Unitree Go2 连接诊断")
        print("=" * 60)

        # 1. 检查环境变量
        print("\n[1/4] 检查环境变量...")
        rmw = os.environ.get('RMW_IMPLEMENTATION', '未设置')
        dds_uri = os.environ.get('CYCLONEDDS_URI', '未设置')
        t_rmw = '✅' if 'cyclonedds' in rmw.lower() else '⚠️ '
        t_dds = '✅' if dds_uri != '未设置' else '⚠️ '
        print(f"  {t_rmw} RMW_IMPLEMENTATION = {rmw}")
        print(f"  {t_dds} CYCLONEDDS_URI = {dds_uri[:80]}...")

        # 2. 获取所有 Topic
        print("\n[2/4] 枚举 ROS2 Topic...")
        topic_info = self.get_topic_names_and_types()
        print(f"  共发现 {len(topic_info)} 个 Topic")

        # 3. 分类 Go2 相关 Topic
        print("\n[3/4] 过滤 Unitree/Go2 相关 Topic...")
        keywords = ['unitree', 'sportmode', 'lowstate', 'lowcmd',
                    'wireless', 'utlidar', 'bms', 'imu']

        unitree_topics = []
        for name, types in topic_info:
            tname = name.lower()
            if any(k in tname for k in keywords):
                publishers = self.count_publishers(name)
                subscribers = self.count_subscribers(name)
                unitree_topics.append((name, types[0] if types else '', publishers, subscribers))

        if not unitree_topics:
            print("  ❌ 未发现任何 Unitree 相关 Topic！")
            print("  可能原因：")
            print("    1. 未连接机器人 — 检查网线")
            print("    2. IP 地址不正确 — 本机应设为 192.168.123.99")
            print("    3. 环境变量未正确设置")
            self.connected = False
        else:
            print(f"  ✅ 发现 {len(unitree_topics)} 个 Unitree 相关 Topic:\n")
            for name, ttype, pubs, subs in sorted(unitree_topics):
                icon = '🟢' if pubs > 0 else '🔴'
                print(f"  {icon} {name}")
                print(f"     类型: {ttype}, 发布者: {pubs}, 订阅者: {subs}")

        # 4. 核心 Topic 数据流检查
        print("\n[4/4] 检查核心 Topic 数据流（5秒采样）...")
        core_topics = ['/sportmodestate', '/lf/sportmodestate',
                       '/lowstate', '/lf/lowstate',
                       '/wirelesscontroller']
        found_data = []

        for topic in core_topics:
            pubs = self.count_publishers(topic)
            if pubs > 0:
                found_data.append(topic)
                print(f"  ✅ {topic} — 有发布者")
            else:
                print(f"  🔴 {topic} — 无发布者")

        # 总结
        print("\n" + "=" * 60)
        if self.count_publishers('/sportmodestate') > 0:
            print("  ✅ 连接正常！Go2 在线，可以继续测试。")
            self.connected = True
        elif self.count_publishers('/lf/sportmodestate') > 0:
            print("  ✅ 连接正常（低频模式）！Go2 在线。")
            self.connected = True
        else:
            print("  ❌ 连接异常：未检测到 Go2 运动状态 Topic。")
            print("  请检查：")
            print("    1. Go2 是否开机并处于非休眠状态")
            print("    2. 网络配置: 本机 IP = 192.168.123.99")
            print("    3. 运行: ros2 topic list 查看完整列表")
            self.connected = False
        print("=" * 60 + "\n")


def main():
    rclpy.init(args=sys.argv)
    tester = ConnectionTester()
    tester.run()
    tester.destroy_node()
    rclpy.shutdown()
    return 0 if tester.connected else 1


if __name__ == '__main__':
    sys.exit(main())