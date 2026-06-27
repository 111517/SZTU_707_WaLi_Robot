"""
Go2 Web Dashboard — Master Launch File

Starts all backend services needed by the web frontend:
  1. unitree_bridge_node  — converts unitree_go → standard ROS2 types
  2. robot_state_publisher — publishes full TF tree from URDF + /joint_states
  3. rosbridge_websocket   — WebSocket bridge (port 9090) with rosapi

Usage:
  source /opt/ros/humble/setup.bash
  source /root/unitree_ros2/setup.sh          # required for unitree_go types
  source /root/ws/install/setup.bash
  ros2 launch go2_web_bridge dashboard.launch.py

Optional env vars:
  GO2_URDF_PATH   — override URDF path (default: go2_description package)
  ROSBRIDGE_PORT  — override rosbridge port (default: 9090)
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _find_workspace_urdf() -> str:
    """Find go2_description URDF. Prefer workspace install, then env var, then well-known paths."""
    # 1. GO2_URDF_PATH env var (for portability)
    env_path = os.environ.get('GO2_URDF_PATH', '')
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Search relative to this launch file's workspace install
    #    install/go2_web_bridge/share/go2_web_bridge/launch/  →  install/
    launch_dir = os.path.dirname(os.path.realpath(__file__))
    install_dir = os.path.normpath(os.path.join(launch_dir, '..', '..', '..', '..'))
    ws_urdf = os.path.join(install_dir, 'go2_description', 'share', 'go2_description', 'urdf', 'go2_description.urdf')
    if os.path.isfile(ws_urdf):
        return ws_urdf

    # 3. Try ament index (may find old installs — use as last resort)
    try:
        from ament_index_python.packages import get_package_share_directory
        pkg_urdf = os.path.join(get_package_share_directory('go2_description'), 'urdf', 'go2_description.urdf')
        if os.path.isfile(pkg_urdf):
            return pkg_urdf
    except Exception:
        pass

    # 4. Fallback: workspace-relative using abspath (works with symlink-install)
    launch_dir_no_real = os.path.dirname(os.path.abspath(__file__))
    install_dir_no_real = os.path.normpath(os.path.join(launch_dir_no_real, '..', '..', '..', '..'))
    fallback = os.path.join(install_dir_no_real, 'go2_description', 'share', 'go2_description', 'urdf', 'go2_description.urdf')
    return fallback


def generate_launch_description():
    default_urdf = _find_workspace_urdf()
    urdf_path = LaunchConfiguration('urdf_path', default=default_urdf)
    rosbridge_port = LaunchConfiguration('rosbridge_port', default='9090')

    return LaunchDescription([
        DeclareLaunchArgument('urdf_path', default_value=default_urdf,
                              description='Path to Go2 URDF file'),
        DeclareLaunchArgument('rosbridge_port', default_value='9090',
                              description='WebSocket port for rosbridge'),

        LogInfo(msg=['Starting Go2 Web Dashboard backend...']),
        LogInfo(msg=['URDF: ', urdf_path]),
        LogInfo(msg=['Rosbridge port: ', rosbridge_port]),

        # 1. Unitree Bridge — converts unitree_go custom types to standard ROS2
        Node(
            package='go2_web_bridge',
            executable='unitree_bridge_node',
            name='unitree_bridge_node',
            output='screen',
            parameters=[],
        ),

        # 2. Robot State Publisher — publishes full TF tree from URDF + /joint_states
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='go2_robot_state_publisher',
            output='screen',
            arguments=[urdf_path],
            parameters=[{'use_sim_time': False}],
        ),

        # 3. Rosbridge WebSocket — bridges ROS2 topics to web clients via port 9090
        # Uses the standard rosbridge_server launch which includes rosapi.
        Node(
            package='rosbridge_server',
            executable='rosbridge_websocket',
            name='rosbridge_websocket',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('rosbridge_port'),
                'use_compression': True,
            }],
            # rosapi_node must be started separately IF rosbridge_websocket is used
            # as a standalone node (not via the .xml launch). We start it here too.
        ),

        # 4. Rosapi — topic/service discovery for the web frontend
        Node(
            package='rosapi',
            executable='rosapi_node',
            name='rosapi',
            output='screen',
        ),

        LogInfo(msg=['Go2 Web Dashboard backend started. WebSocket at ws://0.0.0.0:', rosbridge_port]),
    ])
