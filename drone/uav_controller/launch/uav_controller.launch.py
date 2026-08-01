"""Launch MAVROS + UAV Controller + rosbridge + web_video_server for NX."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")

    return LaunchDescription([
        DeclareLaunchArgument(
            "fcu_url", default_value="serial:///dev/ttyTHS0:921600",
            description="MAVROS FCU URL. SITL: udp://:14540@127.0.0.1:14580"),
        DeclareLaunchArgument(
            "gcs_url", default_value="udp://127.0.0.1:14555",
            description="GCS UDP bridge URL for battery_relay"),

        # === 核心 ===
        Node(package="mavros", executable="mavros_node",
             parameters=[{"fcu_url": fcu_url, "gcs_url": gcs_url}],
             output="screen"),
        Node(package="uav_controller", executable="uav_controller_node",
             output="screen"),
        Node(package="uav_controller", executable="vision_pose_relay",
             output="screen"),
        Node(package="uav_controller", executable="battery_relay",
             output="screen"),

        # === Web 后端 ===
        Node(package="rosapi", executable="rosapi_node",
             output="screen"),
        Node(package="rosbridge_server", executable="rosbridge_websocket",
             output="screen"),
        Node(package="web_video_server", executable="web_video_server",
             parameters=[{"port": 8080}],
             output="screen"),
    ])
