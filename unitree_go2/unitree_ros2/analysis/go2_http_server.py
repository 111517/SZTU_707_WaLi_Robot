#!/usr/bin/env python3
"""
go2_http_server.py — Go2 机器狗增强型 HTTP 控制接口 (v7)

新增：
- 订阅 IMU (sensor_msgs/Imu) — 从 /utlidar/imu
- 订阅雷达里程计 (nav_msgs/Odometry) — 从 /utlidar/robot_odom
- 订阅 SLAM 定位 (nav_msgs/Odometry) — 从 /uslam/localization/odom
- 雷达点云信息 & 地图信息
- 定位 API：查询位置、轨迹、重置定位
- 轨迹追踪
- Web 面板增加定位/轨迹可视化
"""
import os
import sys
import time
import json
import math
import base64
import threading
import signal
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict

logging.getLogger('werkzeug').setLevel(logging.WARNING)

try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

from flask import Flask, request, jsonify, Response

# ROS2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from unitree_api.msg import Request as ApiRequest
from unitree_go.msg import SportModeState, LowState

# ROS2 standard messages
from sensor_msgs.msg import Imu as RosImu
from nav_msgs.msg import Odometry, OccupancyGrid
from geometry_msgs.msg import PoseStamped

import io
import numpy as np
from PIL import Image as PilImage

# Optional camera
try:
    import cv2
    from cv_bridge import CvBridge
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    CvBridge = None

# ========== 常量 ==========
API_ID = {
    "Damp": 1001, "BalanceStand": 1002, "StopMove": 1003,
    "StandUp": 1004, "StandDown": 1005, "RecoveryStand": 1006,
    "Move": 1008, "Sit": 1009, "RiseSit": 1010,
    "SpeedLevel": 1015, "Hello": 1016, "Stretch": 1017,
    "Pose": 1028, "Dance1": 1022, "Dance2": 1023, "Scrape": 1029,
    "FrontFlip": 1030, "FrontJump": 1031, "FrontPounce": 1032,
    "Heart": 1036, "StaticWalk": 1061, "TrotRun": 1062,
    "EconomicGait": 1063, "FreeWalk": 2045, "SwitchAvoid": 2058,
}

ACTION_MAP = OrderedDict([
    ("hello", 1016), ("stretch", 1017), ("dance", 1022),
    ("heart", 1036), ("scrape", 1029),
])

MODE_NAMES = {0: "idle", 1: "balanceStand", 3: "locomotion",
              7: "damping", 10: "sit"}


# ========== 状态监测 (增强版) ==========
class Go2Status:
    """线程安全的集中状态管理 — 支持多话题订阅"""
    def __init__(self):
        self._lock = threading.Lock()

        # Core state
        self._sport_state = None
        self._low_state = None
        self._sport_ts = 0.0
        self._low_ts = 0.0

        # Sensor state
        self._imu = None          # /utlidar/imu (sensor_msgs/Imu)
        self._imu_ts = 0.0
        self._odom = None         # /utlidar/robot_odom (nav_msgs/Odometry)
        self._odom_ts = 0.0
        self._slam_pose = None    # /uslam/localization/odom (nav_msgs/Odometry)
        self._slam_ts = 0.0
        self._robot_pose = None   # /utlidar/robot_pose (geometry_msgs/PoseStamped)
        self._robot_pose_ts = 0.0

        # Trajectory (up to last 500 points)
        self._trajectory = []
        self._trajectory_max = 500
        self._last_traj_x = None
        self._last_traj_y = None

        # SLAM map
        self._map_grid = None
        self._map_grid_ts = 0.0
        self._map_png = None

        # Camera frame
        self._camera_frame = None
        self._camera_frame_ts = 0.0

        self._start_time = time.time()
        self._last_cmd_time = 0.0
        self._last_cmd_name = ""
        self._last_cmd_result = None
        self._ros_ok = False
        self._error_flags = []

    def update_sport(self, msg):
        with self._lock:
            self._sport_state = msg
            self._sport_ts = time.time()

    def update_low(self, msg):
        with self._lock:
            self._low_state = msg
            self._low_ts = time.time()

    def update_imu(self, msg):
        with self._lock:
            self._imu = msg
            self._imu_ts = time.time()

    def update_odom(self, msg):
        with self._lock:
            self._odom = msg
            self._odom_ts = time.time()
            # Track trajectory
            x = round(msg.pose.pose.position.x, 3)
            y = round(msg.pose.pose.position.y, 3)
            if self._last_traj_x is None or abs(x - self._last_traj_x) > 0.01 or abs(y - self._last_traj_y) > 0.01:
                self._trajectory.append({"x": x, "y": y, "t": time.time()})
                if len(self._trajectory) > self._trajectory_max:
                    self._trajectory = self._trajectory[-self._trajectory_max:]
                self._last_traj_x = x
                self._last_traj_y = y

    def update_slam_odom(self, msg):
        with self._lock:
            self._slam_pose = msg
            self._slam_ts = time.time()

    def update_robot_pose(self, msg):
        with self._lock:
            self._robot_pose = msg
            self._robot_pose_ts = time.time()

    def update_map_grid(self, msg):
        with self._lock:
            self._map_grid = msg
            self._map_grid_ts = time.time()
            # Render to PNG immediately
            try:
                w, h = msg.info.width, msg.info.height
                data = np.array(msg.data, dtype=np.int8).reshape(h, w)
                img = np.zeros((h, w), dtype=np.uint8)
                img[data == -1] = 127
                img[data == 0] = 255
                img[data > 0] = 0
                pil_img = PilImage.fromarray(img, 'L')
                buf = io.BytesIO()
                pil_img.save(buf, format='PNG')
                self._map_png = buf.getvalue()
            except Exception:
                pass

    def get_map_png(self):
        with self._lock:
            if self._map_png is not None and time.time() - self._map_grid_ts < 10.0:
                return self._map_png
            return None

    def update_camera_frame(self, cv_img):
        with self._lock:
            self._camera_frame = cv_img
            self._camera_frame_ts = time.time()

    def get_camera_frame(self):
        with self._lock:
            # 返回 5 秒内的帧
            if self._camera_frame is not None and time.time() - self._camera_frame_ts < 5.0:
                return self._camera_frame
            return None

    def set_error(self, flags):
        self._error_flags = flags if isinstance(flags, list) else [str(flags)]

    def clear_errors(self):
        self._error_flags = []

    def set_ros_ok(self, ok):
        self._ros_ok = ok

    def record_cmd(self, name, result):
        self._last_cmd_time = time.time()
        self._last_cmd_name = name
        self._last_cmd_result = result

    def get_trajectory(self):
        """获取轨迹点"""
        with self._lock:
            return list(self._trajectory)

    def clear_trajectory(self):
        with self._lock:
            self._trajectory = []
            self._last_traj_x = None
            self._last_traj_y = None

    def get(self):
        """获取当前完整状态字典"""
        now = time.time()
        with self._lock:
            s = self._sport_state
            l = self._low_state
            imu = self._imu
            odom = self._odom
            slam = self._slam_pose
            pose = self._robot_pose

        status = {
            "timestamp": now,
            "uptime": round(now - self._start_time, 1),
            "ros_connected": self._ros_ok,
            "sport_state_age": round(now - self._sport_ts, 1) if self._sport_ts > 0 else None,
            "errors": self._error_flags,
        }

        # === Sport mode state ===
        if s:
            try:
                status["mode"] = MODE_NAMES.get(int(s.mode), f"mode_{s.mode}")
                status["mode_code"] = int(s.mode)
                status["position"] = {
                    "x": round(float(s.position[0]), 2),
                    "y": round(float(s.position[1]), 2),
                    "z": round(float(s.position[2]), 2),
                }
                status["velocity"] = {
                    "vx": round(float(s.velocity[0]), 2),
                    "vy": round(float(s.velocity[1]), 2),
                    "vyaw": round(float(s.velocity[2]), 2),
                }
                try:
                    status["euler"] = {
                        "roll": round(float(s.euler[0]), 2),
                        "pitch": round(float(s.euler[1]), 2),
                        "yaw": round(float(s.euler[2]), 2),
                    }
                except:
                    status["euler"] = None
                try:
                    status["error_code"] = int(s.error[0]) if len(s.error) > 0 else 0
                except:
                    status["error_code"] = None
            except Exception as e:
                status["sport_parse_error"] = str(e)

        # === Low state (battery, motor, foot) ===
        if l:
            try:
                soc = int(l.bms_state.soc)
                status["battery"] = soc
                try:
                    status["battery_temperature"] = int(l.bms_state.temperature)
                except:
                    try:
                        status["battery_temperature"] = int(l.bms_state.temp)
                    except:
                        status["battery_temperature"] = None
                try:
                    status["battery_voltage"] = round(float(l.bms_state.voltage), 2)
                except:
                    status["battery_voltage"] = None
                try:
                    status["battery_current"] = round(float(l.bms_state.current), 2)
                except:
                    status["battery_current"] = None

                # Body IMU from low state
                try:
                    status["body_imu"] = {
                        "quaternion": [round(float(l.imu_state.quaternion[i]), 4) for i in range(4)],
                        "gyroscope": [round(float(l.imu_state.gyroscope[i]), 2) for i in range(3)],
                        "accelerometer": [round(float(l.imu_state.accelerometer[i]), 2) for i in range(3)],
                    }
                except:
                    status["body_imu"] = None

                # Foot force
                foot_force = []
                if hasattr(l, 'foot_force') and l.foot_force is not None:
                    try:
                        foot_force = [round(float(l.foot_force[i]), 2) for i in range(4)]
                    except:
                        pass
                status["foot_force"] = foot_force
                status["tick"] = int(l.tick)

            except Exception as e:
                status["low_parse_error"] = str(e)

        # === Lidar IMU (/utlidar/imu) ===
        if imu:
            try:
                status["lidar_imu"] = {
                    "orientation": {
                        "x": round(imu.orientation.x, 4),
                        "y": round(imu.orientation.y, 4),
                        "z": round(imu.orientation.z, 4),
                        "w": round(imu.orientation.w, 4),
                    },
                    "angular_velocity": {
                        "x": round(imu.angular_velocity.x, 3),
                        "y": round(imu.angular_velocity.y, 3),
                        "z": round(imu.angular_velocity.z, 3),
                    },
                    "linear_acceleration": {
                        "x": round(imu.linear_acceleration.x, 3),
                        "y": round(imu.linear_acceleration.y, 3),
                        "z": round(imu.linear_acceleration.z, 3),
                    },
                }
            except:
                status["lidar_imu"] = None
            status["lidar_imu_age"] = round(now - self._imu_ts, 1)

        # === Radar odometry (/utlidar/robot_odom) ===
        if odom:
            try:
                status["odometry"] = {
                    "position": {
                        "x": round(odom.pose.pose.position.x, 3),
                        "y": round(odom.pose.pose.position.y, 3),
                        "z": round(odom.pose.pose.position.z, 3),
                    },
                    "orientation": {
                        "x": round(odom.pose.pose.orientation.x, 4),
                        "y": round(odom.pose.pose.orientation.y, 4),
                        "z": round(odom.pose.pose.orientation.z, 4),
                        "w": round(odom.pose.pose.orientation.w, 4),
                    },
                    "linear_velocity": {
                        "x": round(odom.twist.twist.linear.x, 3),
                        "y": round(odom.twist.twist.linear.y, 3),
                        "z": round(odom.twist.twist.linear.z, 3),
                    },
                    "angular_velocity": {
                        "x": round(odom.twist.twist.angular.x, 3),
                        "y": round(odom.twist.twist.angular.y, 3),
                        "z": round(odom.twist.twist.angular.z, 3),
                    },
                }
            except:
                status["odometry"] = None
            status["odometry_age"] = round(now - self._odom_ts, 1)

        # === SLAM localization (/uslam/localization/odom) ===
        if slam:
            try:
                status["slam_odometry"] = {
                    "position": {
                        "x": round(slam.pose.pose.position.x, 3),
                        "y": round(slam.pose.pose.position.y, 3),
                        "z": round(slam.pose.pose.position.z, 3),
                    },
                    "orientation": {
                        "x": round(slam.pose.pose.orientation.x, 4),
                        "y": round(slam.pose.pose.orientation.y, 4),
                        "z": round(slam.pose.pose.orientation.z, 4),
                        "w": round(slam.pose.pose.orientation.w, 4),
                    },
                }
            except:
                status["slam_odometry"] = None
            status["slam_age"] = round(now - self._slam_ts, 1)

        # === Robot pose (/utlidar/robot_pose) ===
        if pose:
            try:
                status["robot_pose"] = {
                    "position": {
                        "x": round(pose.pose.position.x, 3),
                        "y": round(pose.pose.position.y, 3),
                        "z": round(pose.pose.position.z, 3),
                    },
                    "orientation": {
                        "x": round(pose.pose.orientation.x, 4),
                        "y": round(pose.pose.orientation.y, 4),
                        "z": round(pose.pose.orientation.z, 4),
                        "w": round(pose.pose.orientation.w, 4),
                    },
                }
            except:
                status["robot_pose"] = None

        # === Trajectory summary ===
        status["trajectory_points"] = len(self._trajectory)

        # === Last command ===
        if self._last_cmd_time > 0:
            status["last_command"] = {
                "name": self._last_cmd_name,
                "time_ago": round(now - self._last_cmd_time, 1),
            }
        else:
            status["last_command"] = None

        return status


# ========== Go2 控制器 (增强版) ==========
class Go2Controller:
    def __init__(self):
        self.status = Go2Status()
        self._node = None
        self._lock = threading.Lock()
        self._sport_pub = None
        # Continuous walk state
        self._walking = False
        self._walk_thread = None
        self._walk_params = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
        self._camera = None
        self._running = False
        self._spin_timer = None

    def start(self):
        try:
            rclpy.init(args=sys.argv)
        except Exception as e:
            print(f"  ⚠️ rclpy.init {e}")

        try:
            self._node = Node('go2_http_v7')
        except Exception as e:
            print(f"  ⚠️ ROS2 节点创建失败: {e}")
            self._node = None
            self.status.set_ros_ok(False)
            self.status.set_error(["ros_node_failed"])
            print("  控制面板将运行在离线模式")
            return

        self.status.set_ros_ok(True)
        self.status.clear_errors()

        try:
            # Core subscriptions — 使用 BEST_EFFORT 匹配狗端发布 QoS
            best_effort_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
            self._node.create_subscription(SportModeState, '/sportmodestate',
                lambda m: self.status.update_sport(m), best_effort_qos)
            self._node.create_subscription(LowState, '/lowstate',
                lambda m: self.status.update_low(m), best_effort_qos)

            # New: Lidar IMU
            self._node.create_subscription(RosImu, '/utlidar/imu',
                lambda m: self.status.update_imu(m), 1)
            print("  ✓ 订阅 /utlidar/imu")

            # New: Lidar odometry
            self._node.create_subscription(Odometry, '/utlidar/robot_odom',
                lambda m: self.status.update_odom(m), 1)
            print("  ✓ 订阅 /utlidar/robot_odom")

            # New: SLAM localization
            try:
                self._node.create_subscription(Odometry, '/uslam/localization/odom',
                    lambda m: self.status.update_slam_odom(m), 1)
                print("  ✓ 订阅 /uslam/localization/odom")
            except Exception as e:
                print(f"  ⚠️ 无法订阅 /uslam/localization/odom: {e}")

            # New: Robot pose
            try:
                self._node.create_subscription(PoseStamped, '/utlidar/robot_pose',
                    lambda m: self.status.update_robot_pose(m), 1)
                print("  ✓ 订阅 /utlidar/robot_pose")
            except Exception as e:
                print(f"  ⚠️ 无法订阅 /utlidar/robot_pose: {e}")

            # SLAM map (/map → OccupancyGrid)
            try:
                self._node.create_subscription(OccupancyGrid, '/map',
                    lambda m: self.status.update_map_grid(m), 1)
                print("  ✓ 订阅 /map")
            except Exception as e:
                print(f"  ⚠️ 无法订阅 /map: {e}")

            # RealSense camera (for /photo endpoint)
            try:
                self._ros_cv_bridge = CvBridge()
                from sensor_msgs.msg import Image as RosImage
                def camera_cb(msg):
                    try:
                        cv_img = self._ros_cv_bridge.imgmsg_to_cv2(msg, 'bgr8')
                        self.status.update_camera_frame(cv_img)
                    except:
                        pass
                self._node.create_subscription(RosImage, '/camera/color/image_raw',
                    camera_cb, 1)
                print("  ✓ 订阅 /camera/color/image_raw (RealSense)")
            except Exception as e:
                self._ros_cv_bridge = None
                print(f"  ⚠️ 无法订阅 RealSense 相机: {e}")

            # Publisher for control
            self._sport_pub = self._node.create_publisher(ApiRequest, '/api/sport/request', 1)
        except Exception as e:
            print(f"  ⚠️ 订阅/发布创建失败: {e}")
            self.status.set_ros_ok(False)
            self.status.set_error(["pubsub_failed"])

        self._running = True
        if self._node:
            self._schedule_spin()
        print("  ✓ Go2 ROS2 控制已就绪")

    def _schedule_spin(self):
        if not self._running or not self._node:
            return
        try:
            rclpy.spin_once(self._node, timeout_sec=0.02)
        except:
            pass
        self._spin_timer = threading.Timer(0.05, self._schedule_spin)
        self._spin_timer.daemon = True
        self._spin_timer.start()

    def _publish(self, api_id, param=None):
        if not self._sport_pub:
            return {"ok": False, "error": "ros_not_connected"}
        with self._lock:
            try:
                req = ApiRequest()
                req.header.identity.api_id = api_id
                if param:
                    req.parameter = json.dumps(param)
                self._sport_pub.publish(req)
                return {"ok": True, "api_id": api_id, "param": param}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def cmd(self, name, **kwargs):
        """通用命令入口"""
        fn = getattr(self, name, None)
        if not fn:
            result = {"ok": False, "error": f"unknown_command: {name}"}
            self.status.record_cmd(name, result)
            return result
        try:
            result = fn(**kwargs)
            if isinstance(result, dict):
                self.status.record_cmd(name, result)
                return result
            return result
        except Exception as e:
            result = {"ok": False, "error": str(e)}
            self.status.record_cmd(name, result)
            return result

    # === 基本姿态 ===
    def stand(self):
        return self._publish(API_ID["StandUp"])

    def sit(self):
        return self._publish(API_ID["Sit"])

    def lie(self):
        return self._publish(API_ID["StandDown"])

    def stop(self):
        self._walking = False
        return self._publish(API_ID["StopMove"])

    def damping(self):
        return self._publish(API_ID["Damp"])

    def balance_stand(self):
        return self._publish(API_ID["BalanceStand"])

    def recovery_stand(self):
        return self._publish(API_ID["RecoveryStand"])

    def switch_avoid(self):
        """切换避障模式 (开/关)"""
        return self._publish(API_ID["SwitchAvoid"])

    # === 移动 (持续脉冲) ===
    def _continuous_walk_loop(self):
        """后台线程: 以 ~20Hz 持续发送 Move 脉冲"""
        # 先切换步态，只做一次
        self._publish(API_ID["FreeWalk"])
        time.sleep(0.08)
        while self._walking:
            p = self._walk_params
            self._publish(API_ID["Move"], {"x": p["vx"], "y": p["vy"], "z": -p["vyaw"]})
            time.sleep(0.05)

    def walk(self, vx=0.3, vy=0.0, vyaw=0.0):
        """持续行走 — 启动后台线程连续发脉冲，直到 stop() 被调用"""
        self._walk_params = {"vx": vx, "vy": vy, "vyaw": vyaw}
        if not self._walking:
            self._walking = True
            self._walk_thread = threading.Thread(target=self._continuous_walk_loop, daemon=True)
            self._walk_thread.start()
        return {"ok": True, "api_id": API_ID["Move"], "param": self._walk_params}

    def walk_distance(self, meters=1.0, vx=0.3, vy=0.0, vyaw=0.0, timeout=30.0):
        """
        精准距离行走 — 利用 odometry 闭环反馈
        - meters: 目标距离 (米)
        - vx: 前进速度
        - timeout: 超时秒数，防止死循环
        """
        status = self.status.get()
        odom = status.get("odometry", {})
        if not odom.get("position"):
            return {"ok": False, "error": "odometry_unavailable"}

        start_x = odom["position"]["x"]
        start_y = odom["position"]["y"]

        self.walk(vx=vx, vy=vy, vyaw=vyaw)

        t0 = time.time()
        while self._walking:
            if time.time() - t0 > timeout:
                self.stop()
                return {"ok": False, "error": "timeout"}
            status = self.status.get()
            odom = status.get("odometry", {})
            if odom.get("position"):
                dx = odom["position"]["x"] - start_x
                dy = odom["position"]["y"] - start_y
                dist = math.sqrt(dx*dx + dy*dy)
                if dist >= meters:
                    self.stop()
                    break
            time.sleep(0.05)

        final_odom = self.status.get().get("odometry", {})
        actual_dist = 0.0
        if final_odom.get("position"):
            dx = final_odom["position"]["x"] - start_x
            dy = final_odom["position"]["y"] - start_y
            actual_dist = round(math.sqrt(dx*dx + dy*dy), 3)

        return {"ok": True, "target_meters": meters, "actual_meters": actual_dist}

    def back(self, vx=-0.2):
        return self.walk(vx=vx)

    def back(self, vx=-0.2):
        return self.walk(vx=vx)

    def turn(self, vyaw=0.5):
        return self.walk(vx=0.0, vyaw=vyaw)

    def turn_left(self):
        return self.turn(vyaw=0.5)

    def turn_right(self):
        return self.turn(vyaw=-0.5)

    def forward(self, vx=0.3):
        return self.walk(vx=vx)

    # === 动作 ===
    def action(self, name):
        aid = ACTION_MAP.get(name)
        if not aid:
            return {"ok": False, "error": f"unknown_action: {name}, known: {list(ACTION_MAP.keys())}"}
        return self._publish(aid)

    def hello(self):
        return self.action("hello")

    def dance(self):
        return self.action("dance")

    def stretch(self):
        return self.action("stretch")

    def heart(self):
        return self.action("heart")

    def scrape(self):
        return self.action("scrape")

    # === 其他 ===
    def jump(self):
        return self._publish(API_ID["FrontJump"])

    def front_flip(self):
        return self._publish(API_ID["FrontFlip"])

    def emergency_stop(self):
        return self._publish(API_ID["Damp"])

    # === 定位相关 ===
    def get_position(self):
        """获取当前位置"""
        s = self.status.get()
        pose_data = {}
        if "odometry" in s and s["odometry"]:
            pose_data["odom"] = s["odometry"]
        if "slam_odometry" in s and s["slam_odometry"]:
            pose_data["slam"] = s["slam_odometry"]
        if "robot_pose" in s and s["robot_pose"]:
            pose_data["pose"] = s["robot_pose"]
        return {"ok": True, "position": pose_data}

    def get_trajectory(self):
        """获取轨迹"""
        traj = self.status.get_trajectory()
        return {"ok": True, "trajectory": traj, "count": len(traj)}

    def clear_trajectory(self):
        """清除轨迹"""
        self.status.clear_trajectory()
        return {"ok": True}

    # === 拍照 ===
    def capture_photo(self):
        if not CV2_AVAILABLE:
            return None
        # 1) 优先从 ROS RealSense 话题获取图像
        if self._node and hasattr(self, '_ros_cv_bridge'):
            latest = self.status.get_camera_frame()
            if latest is not None:
                _, buf = cv2.imencode('.jpg', latest)
                return buf.tobytes()
        # 2) 降级到 V4L2 本地摄像头
        if self._camera is None:
            for i in range(6):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    self._camera = cap
                    print(f"  ✓ 本地相机 {i} 已打开")
                    break
        if self._camera:
            ret, frame = self._camera.read()
            if ret:
                _, buf = cv2.imencode('.jpg', frame)
                return buf.tobytes()
        return None

    def shutdown(self):
        self._running = False
        if self._spin_timer:
            self._spin_timer.cancel()
        if self._camera:
            self._camera.release()
        if self._node:
            try:
                self._node.destroy_node()
            except:
                pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except:
            pass


# ========== Web 控制面板 (v7) ==========
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>🦾 Go2 机器狗控制面板</title>
<style>
:root{--bg:#0f1117;--surface:#1a1d28;--border:#2a2e3a;--text:#e4e6ed;--text-dim:#6b7280;--accent:#3b82f6;--green:#34d399;--red:#ef4444;--yellow:#fbbf24;--orange:#fb923c}
@media(prefers-color-scheme:light){
:root{--bg:#f3f4f6;--surface:#fff;--border:#d1d5db;--text:#1f2937;--text-dim:#6b7280;--accent:#2563eb;--green:#059669;--red:#dc2626;--yellow:#d97706;--orange:#ea580c}
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);padding:8px;min-height:100dvh;font-size:13px}
h1{font-size:17px;font-weight:700;display:flex;align-items:center;gap:6px;margin-bottom:1px}
h1 small{font-size:11px;color:var(--text-dim);font-weight:400}
.conn-badge{display:inline-block;padding:1px 7px;border-radius:20px;font-size:10px;font-weight:600}
.online{background:rgba(52,211,153,.15);color:var(--green)}
.offline{background:rgba(239,68,68,.15);color:var(--red)}
.section-title{font-size:12px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:.4px;margin:5px 0 3px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(85px,1fr));gap:3px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:6px 8px;margin:3px 0 6px}
.stat{text-align:center}.stat-label{font-size:10px;color:var(--text-dim)}.stat-value{font-size:15px;font-weight:700}
.stat-value.good{color:var(--green)}.stat-value.warn{color:var(--yellow)}.stat-value.bad{color:var(--red)}
.battery-bar{height:3px;background:var(--border);border-radius:2px;margin:2px auto 0;max-width:45px;overflow:hidden}
.battery-fill{height:100%;border-radius:2px;transition:width .5s}
.sensor-grid{display:flex;flex-wrap:wrap;gap:2px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:5px 7px;margin:3px 0 6px}
.sensor-item{flex:1;min-width:65px;text-align:center;font-size:10px;padding:1px 0}
.sensor-item .label{color:var(--text-dim)}.sensor-item .val{font-size:12px;font-weight:600}
.btn-grid{display:flex;flex-wrap:wrap;gap:3px;margin:3px 0 6px}
.btn{display:inline-flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:5px 8px;font-size:11px;font-weight:500;cursor:pointer;transition:all .1s;user-select:none;color:var(--text);gap:3px}
.btn:hover{background:var(--accent);border-color:var(--accent);color:#fff}
.btn:active{transform:scale(.93)}
.btn.primary{border-color:var(--accent);color:var(--accent);background:rgba(59,130,246,.1)}
.btn.primary:hover{background:var(--accent);color:#fff}
.btn.danger{border-color:var(--red);color:var(--red);background:rgba(239,68,68,.08)}
.btn.danger:hover{background:var(--red);color:#fff}
.btn.emergency{border-color:var(--red);color:#fff;background:var(--red);font-weight:700}
.btn.emergency:hover{background:#dc2626}
.btn.green{background:rgba(52,211,153,.1);color:var(--green);border-color:var(--green)}
.btn.green:hover{background:var(--green);color:var(--bg)}
.btn.orange{background:rgba(251,146,60,.1);color:var(--orange);border-color:var(--orange)}
.btn.orange:hover{background:var(--orange);color:var(--bg)}
.move-pad{display:grid;grid-template-columns:repeat(3,1fr);gap:3px;max-width:150px;margin:3px auto 6px}
.move-pad .btn{font-size:18px;padding:10px;border-radius:7px;height:42px}
.row{display:flex;gap:3px;flex-wrap:wrap;margin:2px 0 5px;align-items:center}
.raw-data{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:5px 8px;font-family:ui-monospace,'Cascadia Code',monospace;font-size:10px;white-space:pre-wrap;word-break:break-all;max-height:160px;overflow-y:auto;margin:3px 0 6px}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:5px 12px;font-size:11px;box-shadow:0 4px 16px rgba(0,0,0,.5);opacity:0;transition:opacity .3s;z-index:99;pointer-events:none}
.toast.show{opacity:1}
#detection-panel{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:5px 8px;margin:3px 0 6px;max-height:180px;overflow-y:auto}
.det-list{display:flex;flex-direction:column;gap:2px}
.det-empty{color:var(--text-dim);text-align:center;padding:6px;font-size:11px}
.det-item{display:flex;align-items:center;justify-content:space-between;padding:2px 5px;background:rgba(59,130,246,.08);border-radius:4px;font-size:11px;border-left:3px solid var(--accent)}
.det-label{font-weight:600}.det-conf{color:var(--green);font-size:10px}
.det-dist{color:var(--yellow);font-size:10px}.det-pos{color:var(--text-dim);font-size:9px}
#trajCanvas{border:1px solid var(--border);border-radius:7px;width:100%;height:140px;background:var(--surface);margin:2px 0 5px}
.slider-row{display:flex;align-items:center;gap:4px;margin:2px 0;font-size:11px}
.slider-row input[type=range]{flex:1;height:4px;accent-color:var(--accent)}
.slider-row .val{min-width:35px;text-align:right;font-weight:600;font-size:12px}
#cmd-log{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:4px 8px;font-family:ui-monospace,monospace;font-size:10px;max-height:100px;overflow-y:auto;margin:3px 0 6px}
.cmd-entry{margin:1px 0}.cmd-time{color:var(--text-dim);margin-right:4px}
.cmd-name{color:var(--accent);font-weight:600}.cmd-ok{color:var(--green)}.cmd-fail{color:var(--red)}
.tabs{display:flex;gap:2px;margin:4px 0 1px;border-bottom:1px solid var(--border);padding-bottom:3px;overflow-x:auto}
.tab{padding:3px 8px;font-size:10px;font-weight:500;cursor:pointer;border-radius:5px 5px 0 0;color:var(--text-dim);white-space:nowrap}
.tab.active{background:var(--surface);color:var(--text);border:1px solid var(--border);border-bottom-color:var(--surface)}
.tab:hover{color:var(--text)}
.tab-content{display:none}.tab-content.active{display:block}
.adv-card{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:6px 8px;margin:3px 0 6px}
.adv-card label{font-size:10px;color:var(--text-dim);display:block;margin-bottom:1px}
.adv-card input[type=text],.adv-card input[type=number]{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:3px 6px;color:var(--text);font-size:11px;width:100%;margin-bottom:3px}
.adv-card input:focus{outline:1px solid var(--accent)}
.photo-img{max-width:100%;border-radius:6px;border:1px solid var(--border);margin:3px 0}
</style>
</head>
<body>

<h1>🦾 Go2 机器狗 <small id="title-info"></small></h1>
<div style="margin:2px 0 4px"><span class="conn-badge offline" id="conn-badge">检查连接...</span></div>

<!-- ──────────────── Status ──────────────── -->
<div class="section-title">📊 状态</div>
<div class="grid" id="status-grid">
  <div class="stat"><div class="stat-label">模式</div><div class="stat-value" id="s-mode">--</div></div>
  <div class="stat"><div class="stat-label">电量</div><div class="stat-value" id="s-battery">--%</div><div class="battery-bar"><div class="battery-fill" id="battery-fill" style="width:0%"></div></div></div>
  <div class="stat"><div class="stat-label">连接</div><div id="s-ros"><span class="conn-badge offline">离线</span></div></div>
  <div class="stat"><div class="stat-label">运行</div><div class="stat-value" id="s-uptime">--</div></div>
</div>

<!-- ──────────────── Locomotion ──────────────── -->
<div class="section-title">📍 定位</div>
<div class="sensor-grid" id="locGrid">
  <div class="sensor-item"><span class="label">X</span><br><span class="val" id="loc-x">--</span></div>
  <div class="sensor-item"><span class="label">Y</span><br><span class="val" id="loc-y">--</span></div>
  <div class="sensor-item"><span class="label">Z</span><br><span class="val" id="loc-z">--</span></div>
  <div class="sensor-item"><span class="label">速度</span><br><span class="val" id="loc-v">--</span></div>
  <div class="sensor-item"><span class="label">偏航</span><br><span class="val" id="loc-yaw">--</span></div>
  <div class="sensor-item"><span class="label">轨迹</span><br><span class="val" id="traj-count">0</span></div>
</div>
<canvas id="trajCanvas"></canvas>

<!-- ──────────────── Tabs ──────────────── -->
<div class="tabs">
  <div class="tab active" onclick="switchTab('basic')">基本控制</div>
  <div class="tab" onclick="switchTab('move')">移动</div>
  <div class="tab" onclick="switchTab('adv')">高级</div>
  <div class="tab" onclick="switchTab('map')">🗺️ 地图</div>
  <div class="tab" onclick="switchTab('detect')">检测</div>
  <div class="tab" onclick="switchTab('photo')">拍照</div>
  <div class="tab" onclick="switchTab('log')">日志</div>
</div>

<div id="tab-basic" class="tab-content active">
  <div class="section-title">🤖 姿态</div>
  <div class="btn-grid">
    <div class="btn primary" onclick="cmd('stand')">⬆ 站立</div>
    <div class="btn" onclick="cmd('sit')">💺 坐下</div>
    <div class="btn" onclick="cmd('lie')">🛌 趴下</div>
    <div class="btn" onclick="cmd('damping')">🛋 阻尼</div>
    <div class="btn" onclick="cmd('switch_avoid')">🚧 避障</div>
    <div class="btn green" onclick="cmd('balance_stand')">⚖️ 平衡站</div>
    <div class="btn orange" onclick="cmd('recovery_stand')">🔁 恢复站</div>
    <div class="btn emergency" onclick="cmd('emergency_stop')">🛑 急停</div>
  </div>

  <div class="section-title">💃 动作</div>
  <div class="btn-grid">
    <div class="btn" onclick="cmd('hello')">👋 你好</div>
    <div class="btn" onclick="cmd('dance')">🕺 跳舞</div>
    <div class="btn" onclick="cmd('stretch')">🤸 伸腰</div>
    <div class="btn" onclick="cmd('heart')">❤️ 比心</div>
    <div class="btn" onclick="cmd('scrape')">🦵 蹭腿</div>
    <div class="btn" onclick="cmd('jump')">🦘 跳跃</div>
    <div class="btn" onclick="cmd('front_flip')">🤸 前空翻</div>
  </div>
</div>

<div id="tab-move" class="tab-content">
  <div class="section-title">🚶 移动 <small>W/A/S/D 空格停</small></div>
  <div class="move-pad">
    <div></div>
    <div class="btn" onmousedown="cmd('forward')">⬆</div>
    <div></div>
    <div class="btn" onmousedown="cmd('turn_left')">↩</div>
    <div class="btn danger" onmousedown="cmd('stop')">⏹</div>
    <div class="btn" onmousedown="cmd('turn_right')">↪</div>
    <div></div>
    <div class="btn" onmousedown="cmd('back')">⬇</div>
    <div></div>
  </div>

  <div class="section-title">🎛️ 速度控制</div>
  <div class="adv-card">
    <div class="slider-row"><span>前速 vx:</span><input type="range" min="-1" max="1" step="0.05" value="0.3" id="sl-vx"><span class="val" id="val-vx">0.30</span></div>
    <div class="slider-row"><span>侧速 vy:</span><input type="range" min="-1" max="1" step="0.05" value="0" id="sl-vy"><span class="val" id="val-vy">0.00</span></div>
    <div class="slider-row"><span>转向 vyaw:</span><input type="range" min="-1" max="1" step="0.05" value="0" id="sl-vyaw"><span class="val" id="val-vyaw">0.00</span></div>
    <div class="btn primary" onclick="walkP()" style="margin-top:4px">▶ 执行行走</div>
  </div>
</div>

<div id="tab-adv" class="tab-content">
  <div class="section-title">🧠 高级功能</div>

  <div class="adv-card">
    <label>🎯 跟随目标 (待实现)</label>
    <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">基于物体识别 + 深度信息追踪目标</div>
    <div class="btn primary" onclick="logCmd('follow_person','启动跟随模式')">🔴 跟随人物</div>
    <div class="btn danger" onclick="cmd('stop')">⏹ 停止跟随</div>
  </div>

  <div class="adv-card">
    <label>🗺️ 定位巡航 (测试)</label>
    <div class="row">
      <input type="number" id="nav-x" placeholder="目标 X" step="0.1" style="width:70px;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:3px 5px;color:var(--text);font-size:11px">
      <input type="number" id="nav-y" placeholder="目标 Y" step="0.1" style="width:70px;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:3px 5px;color:var(--text);font-size:11px">
      <div class="btn primary" onclick="navigateTo()">🚀 前往</div>
    </div>
  </div>

  <div class="adv-card">
    <label>📦 自定义命令</label>
    <div class="row">
      <input type="text" id="custom-cmd" placeholder="命令名称" style="flex:1;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:3px 5px;color:var(--text);font-size:11px">
      <div class="btn primary" onclick="customCmd()">发送</div>
    </div>
  </div>
</div>

<div id="tab-map" class="tab-content">
  <div class="section-title">🗺️ 实时建图 (slam_toolbox)</div>
  <div style="position:relative;background:#000;border-radius:8px;overflow:hidden;border:1px solid var(--border);max-height:320px">
    <img id="map-img" src="" style="width:100%;display:block;object-fit:contain;max-height:320px" />
    <canvas id="map-canvas" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none"></canvas>
  </div>
  <div style="font-size:10px;color:var(--text-dim);margin:3px 0">
    <span id="map-info">等待地图数据...</span>
  </div>
</div>

<div id="tab-detect" class="tab-content">
  <div class="section-title">🔍 物体检测</div>
  <div id="detection-panel"><div class="det-list" id="det-list"><div class="det-empty">等待检测数据...</div></div></div>
</div>

<div id="tab-photo" class="tab-content">
  <div class="section-title">📸 实时视频</div>
  <img src="/video_stream" id="video-stream" style="max-width:100%;border-radius:8px;border:1px solid var(--border);background:#000" />
  <div style="font-size:11px;color:var(--text-dim);margin:3px 0">RealSense D435i 实时画面</div>
  <div class="section-title">📷 单张拍照</div>
  <div class="btn primary" onclick="takePhoto()">📷 拍照</div>
  <div id="photo-result" style="margin-top:4px"></div>
</div>

<div id="tab-log" class="tab-content">
  <div class="section-title">📋 命令日志</div>
  <div id="cmd-log"><div class="cmd-entry" style="color:var(--text-dim)">等待命令...</div></div>
</div>

<div id="toast"></div>

<script>
const API_BASE = '';
let lastState = {};
let trajData = [];
let cmdLog = [];

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector('.tab[onclick*="'+name+'"]').classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}

function toast(m) {
  const t=document.getElementById('toast');
  t.textContent=m; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2000);
}

function logCmd(name, result) {
  cmdLog.unshift({name, result, time:new Date()});
  if(cmdLog.length>50) cmdLog.pop();
  renderLog();
}

function renderLog() {
  const el=document.getElementById('cmd-log');
  el.innerHTML = cmdLog.map(e => {
    const cls = e.result && e.result.ok ? 'cmd-ok' : 'cmd-fail';
    const txt = e.result ? (e.result.ok ? '✅' : '❌') : '⏳';
    return '<div class="cmd-entry"><span class="cmd-time">'+e.time.toLocaleTimeString()+'</span><span class="cmd-name">'+e.name+'</span> <span class="'+cls+'">'+txt+'</span></div>';
  }).join('');
}

// ────────────── SSE ──────────────
let evtSource;
function connectSSE(){
  if(evtSource) evtSource.close();
  evtSource=new EventSource(API_BASE+'/events');
  evtSource.onmessage=e=>{
    try{const d=JSON.parse(e.data);lastState=d;updateUI(d)}catch(_){}
  };
  evtSource.onerror=()=>{
    document.getElementById('conn-badge').textContent='离线';
    document.getElementById('conn-badge').className='conn-badge offline';
    document.getElementById('s-ros').innerHTML='<span class="conn-badge offline">离线</span>';
  };
}

function updateUI(d){
  const badge=document.getElementById('conn-badge');
  if(d.ros_connected){badge.textContent='🟢 在线';badge.className='conn-badge online'}
  else{badge.textContent='🔴 离线';badge.className='conn-badge offline'}
  const rbadge=document.querySelector('#s-ros .conn-badge');
  if(d.ros_connected){rbadge.textContent='在线';rbadge.className='conn-badge online'}
  else{rbadge.textContent='离线';rbadge.className='conn-badge offline'}

  // Mode
  const mode=d.mode||'--';
  document.getElementById('s-mode').textContent=mode;
  document.getElementById('s-mode').className='stat-value '+(mode==='idle'?'neutral':mode==='locomotion'?'good':'');

  // Battery
  if(d.battery!==undefined){
    const p=d.battery;
    document.getElementById('s-battery').textContent=p+'%';
    const f=document.getElementById('battery-fill');
    f.style.width=p+'%';
    f.style.background=p<15?'var(--red)':p<30?'var(--yellow)':'var(--green)';
    document.getElementById('s-battery').className='stat-value'+(p<15?' bad':p<30?' warn':' good');
  }

  // Uptime
  if(d.uptime){const m=Math.floor(d.uptime/60),s=Math.floor(d.uptime%60);document.getElementById('s-uptime').textContent=m+'m '+s+'s'}

  // Position
  const odom=d.odometry||{};
  if(odom.position){
    document.getElementById('loc-x').textContent=odom.position.x.toFixed(2);
    document.getElementById('loc-y').textContent=odom.position.y.toFixed(2);
    document.getElementById('loc-z').textContent=odom.position.z.toFixed(2);
    if(odom.linear_velocity){
      const v=Math.sqrt(odom.linear_velocity.x**2+odom.linear_velocity.y**2);
      document.getElementById('loc-v').textContent=v.toFixed(2)+' m/s';
    }
    if(odom.orientation){
      const q=odom.orientation;
      const yaw=Math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))*180/Math.PI;
      document.getElementById('loc-yaw').textContent=yaw.toFixed(1)+'°';
    }
  }else if(d.position){
    document.getElementById('loc-x').textContent=d.position.x.toFixed(2);
    document.getElementById('loc-y').textContent=d.position.y.toFixed(2);
    document.getElementById('loc-z').textContent=d.position.z.toFixed(2);
  }

  document.getElementById('traj-count').textContent=d.trajectory_points||0;
  document.getElementById('title-info').textContent=new Date(d.timestamp*1000).toLocaleTimeString();

  // Update map overlay position
  let rp=d.robot_pose||(d.odometry||{}).pose||d.position;
  if(rp&&rp.x!==undefined){
    robotX=rp.x||0; robotY=rp.y||0;
    let rq=d.robot_pose?d.robot_pose.orientation:(d.odometry||{}).orientation;
    if(rq){robotYaw=Math.atan2(2*(rq.w*rq.z+rq.x*rq.y),1-2*(rq.y*rq.y+rq.z*rq.z))}
  }
}

// ────────────── Commands ──────────────
const epMap={
  stand:'/stand', sit:'/sit', lie:'/lie', stop:'/stop',
  forward:'/forward', back:'/back', turn_left:'/turn', turn_right:'/turn',
  jump:'/jump', emergency_stop:'/emergency_stop', damping:'/damping',
  switch_avoid:'/avoid',
  balance_stand:'/balance', recovery_stand:'/recovery',
  hello:'/action', dance:'/action', stretch:'/action', heart:'/action', scrape:'/action',
  front_flip:'/cmd'
};
const bodyMap={
  stand:{}, sit:{}, lie:{}, stop:{},
  forward:{vx:0.3}, back:{vx:-0.2},
  turn_left:{vyaw:-0.5}, turn_right:{vyaw:0.5},
  jump:{}, emergency_stop:{}, damping:{}, switch_avoid:{}, balance_stand:{}, recovery_stand:{},
  hello:{name:'hello'}, dance:{name:'dance'}, stretch:{name:'stretch'},
  heart:{name:'heart'}, scrape:{name:'scrape'}, front_flip:{name:'front_flip',params:{}}
};

async function cmd(name){
  const ep=epMap[name];
  if(!ep) return;
  let body=bodyMap[name]||{};
  // Apply speed sliders for movement (only forward/back, NOT turn)
  if(name==='forward') body.vx=parseFloat(document.getElementById('sl-vx').value);
  if(name==='back') body.vx=-parseFloat(document.getElementById('sl-vx').value);
  try{
    const r=await fetch(API_BASE+ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    logCmd(name, j);
    if(j.ok) toast('✅ '+name);
    else toast('❌ '+name+': '+(j.error||''));
  }catch(e){ toast('❌ 连接失败'); }
}

function walkP(){
  const vx=parseFloat(document.getElementById('sl-vx').value);
  const vy=parseFloat(document.getElementById('sl-vy').value);
  const vyaw=parseFloat(document.getElementById('sl-vyaw').value);
  fetch(API_BASE+'/walk/params',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vx,vy,vyaw})})
  .then(r=>r.json()).then(j=>{logCmd('walk('+vx+','+vy+','+vyaw+')',j);if(j.ok)toast('🚶 行走');else toast('❌ '+(j.error||''));})
  .catch(()=>toast('❌ 连接失败'));
}

// ────────────── Sliders ──────────────
document.getElementById('sl-vx').addEventListener('input',function(){document.getElementById('val-vx').textContent=this.value});
document.getElementById('sl-vy').addEventListener('input',function(){document.getElementById('val-vy').textContent=this.value});
document.getElementById('sl-vyaw').addEventListener('input',function(){document.getElementById('val-vyaw').textContent=this.value});

// ────────────── Keyboard ──────────────
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT') return;
  const k=e.key.toLowerCase();
  if(k==='w') cmd('forward');
  else if(k==='s') cmd('back');
  else if(k==='a') cmd('turn_left');
  else if(k==='d') cmd('turn_right');
  else if(k===' ') {e.preventDefault();cmd('stop');}
  else if(k==='e') cmd('stand');
  else if(k==='q') cmd('sit');
});

// ────────────── Custom command ──────────────
async function customCmd(){
  const name=document.getElementById('custom-cmd').value.trim();
  if(!name) return;
  try{
    const r=await fetch(API_BASE+'/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    const j=await r.json();
    logCmd(name,j);
    if(j.ok) toast('✅ '+name);
    else toast('❌ '+(j.error||''));
  }catch(e){toast('❌ 连接失败');}
}

// ────────────── Detection ──────────────
async function pollDetections(){
  try{
    const r=await fetch(API_BASE+'/detections');
    const d=await r.json();
    const list=document.getElementById('det-list');
    if(d.detections&&d.detections.length>0){
      list.innerHTML=d.detections.map(item=>{
        const distStr=item.distance!==null?item.distance.toFixed(2)+'m':'∞';
        const boxStr=item.x1!=null?'['+item.x1+','+item.y1+','+item.x2+','+item.y2+']':'';
        return '<div class="det-item"><div><span class="det-label">'+item.label+'</span> <span class="det-conf">'+(item.confidence*100).toFixed(0)+'%</span></div><div><span class="det-dist">🗲 '+distStr+'</span> <span class="det-pos">('+item.x+','+item.y+')</span>'+'<br><span style="font-size:9px;color:var(--text-dim)">bbox '+boxStr+'</span></div></div>';
      }).join('');
    }else{
      list.innerHTML='<div class="det-empty">暂无检测（需运行 detect_object.py）</div>';
    }
  }catch(e){
    document.getElementById('det-list').innerHTML='<div class="det-empty">❌ 加载失败</div>';
  }
}

// ────────────── Photo ──────────────
async function takePhoto(){
  const el=document.getElementById('photo-result');
  el.innerHTML='<span style="color:var(--text-dim)">📷 拍照中...</span>';
  try{
    const r=await fetch(API_BASE+'/photo');
    const blob=await r.blob();
    if(blob.type==='application/json'){
      const j=await blob.text();
      const err=JSON.parse(j);
      el.innerHTML='<span style="color:var(--red)">❌ '+(err.error||'拍照失败')+'</span>';
      return;
    }
    const url=URL.createObjectURL(blob);
    el.innerHTML='<img src="'+url+'" class="photo-img" />';
    toast('📸 拍照成功');
    logCmd('photo',{ok:true});
  }catch(e){
    el.innerHTML='<span style="color:var(--red)">❌ 连接失败</span>';
  }
}

// ────────────── Navigation ──────────────
async function navigateTo(){
  const x=parseFloat(document.getElementById('nav-x').value);
  const y=parseFloat(document.getElementById('nav-y').value);
  if(isNaN(x)||isNaN(y)){toast('❌ 请输入有效坐标');return;}
  toast('🚀 前往 ('+x+','+y+')');
  logCmd('navigate',{ok:true,msg:'前往('+x+','+y+')'});
}

// ────────────── Map ──────────────
let mapLoaded=false,mapW=0,mapH=0,mapRes=0.05,mapOx=0,mapOy=0;
function refreshMap(){
  let img=document.getElementById('map-img');
  img.src='/map_data?'+Date.now();
  img.onload=function(){
    if(!mapLoaded&&img.naturalWidth>10){
      mapW=img.naturalWidth; mapH=img.naturalHeight; mapLoaded=true;
    }
    document.getElementById('map-info').textContent='🟢 '+mapW+'x'+mapH+' @ '+mapRes+'m/px | '+new Date().toLocaleTimeString();
    overlayRobot();
  };
  img.onerror=function(){document.getElementById('map-info').textContent='⏳ 等待SLAM地图...'}
}
function overlayRobot(){
  let c=document.getElementById('map-canvas'),img=document.getElementById('map-img');
  if(!mapLoaded)return;
  c.width=img.clientWidth; c.height=img.clientHeight;
  let g=c.getContext('2d'); g.clearRect(0,0,c.width,c.height);
  if(typeof robotX==='undefined')return;
  let rx=robotX||0, ry=robotY||0, ryaw=robotYaw||0;
  let px=(rx-mapOx)/mapRes, py=(ry-mapOy)/mapRes;
  px=px/mapW*c.width; py=c.height-py/mapH*c.height;
  g.save(); g.translate(px,py); g.rotate(-ryaw+Math.PI/2);
  g.fillStyle='#4ecca3'; g.beginPath(); g.moveTo(0,-10);g.lineTo(-5,7);g.lineTo(5,7);g.closePath();g.fill();
  g.strokeStyle='#fff'; g.lineWidth=1.5; g.stroke(); g.restore();
  g.fillStyle='#4ecca3'; g.beginPath(); g.arc(px,py,4,0,Math.PI*2);g.fill();
}
refreshMap();
setInterval(refreshMap,2000);
// ────────────── Init ──────────────
connectSSE();
setInterval(pollDetections,2000);
</script>

</body>
</html>"""


# ========== Flask 应用 ==========
def create_app(ctrl):
    app = Flask(__name__)
    if HAS_CORS:
        CORS(app)

    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.route("/")
    def index():
        return INDEX_HTML

    @app.route("/health")
    def health():
        s = ctrl.status.get()
        return jsonify({
            "ok": s["ros_connected"],
            "uptime": s["uptime"],
            "ros_connected": s["ros_connected"],
            "timestamp": s["timestamp"],
        })

    @app.route("/status")
    def status():
        return jsonify(ctrl.status.get())

    @app.route("/events")
    def events():
        def gen():
            while True:
                d = ctrl.status.get()
                yield f"data: {json.dumps(d)}\n\n"
                time.sleep(0.3)
        return Response(gen(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive',
                                 'X-Accel-Buffering': 'no'})

    # ==== 姿态 ====
    @app.route("/detections", methods=["GET"])
    def api_detections():
        try:
            with open('/tmp/go2_detections.json', 'r') as f:
                data = json.load(f)
            return jsonify(data)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({'timestamp': time.time(), 'detections': []})

    @app.route("/map_data")
    def map_data():
        png = ctrl.status.get_map_png()
        if png:
            return Response(png, mimetype='image/png')
        return Response(status=204)

    @app.route("/damping", methods=["POST"])
    def api_damping():
        return jsonify(ctrl.cmd("damping"))

    @app.route("/avoid", methods=["POST"])
    def api_avoid():
        return jsonify(ctrl.cmd("switch_avoid"))

    @app.route("/recovery", methods=["POST"])
    def api_recovery():
        return jsonify(ctrl.cmd("recovery_stand"))

    @app.route("/balance", methods=["POST"])
    def api_balance():
        return jsonify(ctrl.cmd("balance_stand"))

    @app.route("/walk/params", methods=["POST"])
    def api_walk_params():
        d = request.get_json(silent=True) or {}
        vx = float(d.get("vx", 0.3))
        vy = float(d.get("vy", 0.0))
        vyaw = float(d.get("vyaw", 0.0))
        return jsonify(ctrl.cmd("walk", vx=vx, vy=vy, vyaw=vyaw))

    @app.route("/stand", methods=["POST"])
    def api_stand():
        return jsonify(ctrl.cmd("stand"))

    @app.route("/sit", methods=["POST"])
    def api_sit():
        return jsonify(ctrl.cmd("sit"))

    @app.route("/lie", methods=["POST"])
    def api_lie():
        return jsonify(ctrl.cmd("lie"))

    @app.route("/stop", methods=["POST"])
    def api_stop():
        return jsonify(ctrl.cmd("stop"))

    @app.route("/balance_stand", methods=["POST"])
    def api_balance_stand():
        return jsonify(ctrl.cmd("balance_stand"))

    # ==== 移动 ====
    @app.route("/forward", methods=["POST"])
    def api_forward():
        d = request.get_json(silent=True) or {}
        return jsonify(ctrl.cmd("forward", vx=float(d.get("vx", 0.3))))

    @app.route("/back", methods=["POST"])
    def api_back():
        d = request.get_json(silent=True) or {}
        return jsonify(ctrl.cmd("back", vx=float(d.get("vx", -0.2))))

    @app.route("/walk", methods=["POST"])
    def api_walk():
        d = request.get_json(silent=True) or {}
        return jsonify(ctrl.cmd("walk",
            vx=float(d.get("vx", 0.3)),
            vy=float(d.get("vy", 0.0)),
            vyaw=float(d.get("vyaw", 0.0))))

    @app.route("/turn", methods=["POST"])
    def api_turn():
        d = request.get_json(silent=True) or {}
        return jsonify(ctrl.cmd("turn", vyaw=float(d.get("vyaw", 0.5))))

    @app.route("/walk/distance", methods=["POST"])
    def api_walk_distance():
        d = request.get_json(silent=True) or {}
        return jsonify(ctrl.cmd("walk_distance",
            meters=float(d.get("meters", 1.0)),
            vx=float(d.get("vx", 0.3)),
            vy=float(d.get("vy", 0.0)),
            vyaw=float(d.get("vyaw", 0.0)),
            timeout=float(d.get("timeout", 30.0))))

    # ==== 动作 ====
    @app.route("/action", methods=["POST"])
    def api_action():
        d = request.get_json(silent=True) or {}
        name = d.get("name", "")
        return jsonify(ctrl.action(name))

    @app.route("/jump", methods=["POST"])
    def api_jump():
        return jsonify(ctrl.cmd("jump"))

    # ==== 特殊 ====
    @app.route("/emergency_stop", methods=["POST"])
    def api_emergency():
        return jsonify(ctrl.cmd("emergency_stop"))

    # ==== 定位 API (新) ====
    @app.route("/position", methods=["GET", "POST"])
    def api_position():
        return jsonify(ctrl.get_position())

    @app.route("/trajectory", methods=["GET"])
    def api_trajectory():
        return jsonify(ctrl.get_trajectory())

    @app.route("/trajectory/clear", methods=["POST"])
    def api_trajectory_clear():
        return jsonify(ctrl.clear_trajectory())

    # ==== 拍照 ====
    @app.route("/photo", methods=["GET", "POST"])
    def api_photo():
        if request.method == "POST":
            img = ctrl.capture_photo()
            if img:
                return jsonify({"ok": True, "image": base64.b64encode(img).decode(), "size": len(img)})
            return jsonify({"ok": False, "error": "camera_unavailable"}), 503
        img = ctrl.capture_photo()
        if img:
            return Response(img, mimetype='image/jpeg')
        return jsonify({"ok": False, "error": "camera_unavailable"}), 503

    # ==== MJPEG 视频流（带检测标注）====
    @app.route("/video_stream")
    def api_video_stream():
        import cv2, json
        
        def draw_detections(frame):
            """在帧上绘制 YOLO 检测标注（bbox + 标签 + 距离）"""
            try:
                with open('/tmp/go2_detections.json', 'r') as f:
                    data = json.load(f)
                dets = data.get('detections', [])
                if dets:
                    print(f"[video_stream] drawing {len(dets)} detections on {frame.shape[1]}x{frame.shape[0]}")
                for det in dets:
                    label = det.get('label', '?')
                    conf = det.get('confidence', 0)
                    cx, cy = det.get('x', 0), det.get('y', 0)
                    x1 = det.get('x1', max(0, cx - 40))
                    y1 = det.get('y1', max(0, cy - 225))
                    x2 = det.get('x2', min(frame.shape[1], cx + 40))
                    y2 = det.get('y2', min(frame.shape[0], cy + 150))
                    dist = det.get('distance')
                    heading = det.get('heading_angle_deg')
                    pos3d = det.get('position_3d', {})
                    
                    # 宽大显眼的框
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 3)
                    
                    dist_str = f'{dist:.2f}m' if dist is not None else '?'
                    text = f'{label} {conf:.0%} {dist_str}'
                    cv2.putText(frame, text, (x1-5, y1-8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                    
                    # 方向角和三维坐标
                    if heading is not None:
                        cv2.putText(frame, f'h:{heading:.1f}', (x1-5, y2+22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 1)
                    if pos3d and pos3d.get('x') is not None:
                        cv2.putText(frame, f'x:{pos3d["x"]:.2f}y:{pos3d.get("y",0):.2f}z:{pos3d.get("z",0):.2f}',
                                    (x1-5, y2+44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 1)
                    
                    # 绿色十字
                    cv2.line(frame, (cx - 15, cy), (cx + 15, cy), (0, 255, 0), 2)
                    cv2.line(frame, (cx, cy - 15), (cx, cy + 15), (0, 255, 0), 2)
                    cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)
            except Exception as e:
                print(f"[video_stream] draw error: {e}")
            return frame
        
        def gen():
            import numpy as np
            frame_no = 0
            while True:
                frame_no += 1
                raw = ctrl.status.get_camera_frame()
                if raw is not None:
                    if frame_no % 10 == 0:
                        print(f"[vstream] frame {frame_no}: from get_camera_frame")
                    annotated = draw_detections(raw.copy())
                    _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                else:
                    raw_jpg = ctrl.capture_photo()
                    if raw_jpg is not None and len(raw_jpg) > 100:
                        if frame_no % 10 == 0:
                            print(f"[vstream] frame {frame_no}: from capture_photo ({len(raw_jpg)}B)")
                        np_arr = np.frombuffer(raw_jpg, dtype=np.uint8)
                        raw_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        if raw_bgr is not None:
                            annotated = draw_detections(raw_bgr)
                            _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                        else:
                            if frame_no % 10 == 0:
                                print("[vstream] imdecode failed!")
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + raw_jpg + b'\r\n')
                    else:
                        if frame_no % 10 == 0:
                            print(f"[vstream] frame {frame_no}: NO DATA")
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' +
                               b'/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AKwA=' +
                               b'\r\n')
                time.sleep(0.05)
        return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame',
                        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive',
                                 'X-Accel-Buffering': 'no'})

    # ==== 通用命令 ====
    @app.route("/cmd", methods=["POST"])
    def api_cmd():
        d = request.get_json(silent=True) or {}
        name = d.get("name", "")
        params = d.get("params", {})
        return jsonify(ctrl.cmd(name, **params))

    return app


# ========== 入口 ==========
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Go2 增强型 HTTP 控制接口 v7")
    parser.add_argument("--port", type=int, default=8001, help="HTTP 端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    args = parser.parse_args()

    print("╔══════════════════════════════════╗")
    print("║   🦾 Go2 机器狗控制服务 (v7)     ║")
    print("║   多话题订阅 + 定位功能            ║")
    print("╚══════════════════════════════════╝")
    print(f"  端口: {args.port}")
    print(f"  地址: http://{args.host}:{args.port}")
    print("  初始化中...")

    ctrl = Go2Controller()
    ctrl.start()

    app = create_app(ctrl)

    def cleanup(*args):
        print("\n  正在关闭...")
        ctrl.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"  ✓ 控制面板: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
