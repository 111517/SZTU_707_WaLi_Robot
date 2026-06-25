"""
OpenClaw-TurtleBot4 Direct ROS 2 Bridge
直接调用 Nav2 和 SLAM Toolbox 的高性能方案
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
import logging
import json
import time
import subprocess
import signal
import os
import threading

# ROS 2 导入
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import QoSProfile, ReliabilityPolicy, QoSDurabilityPolicy
from rclpy.duration import Duration
from rclpy.time import Time

# ROS 2 消息类型
from geometry_msgs.msg import PoseStamped, Twist, PoseWithCovarianceStamped, TransformStamped
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import BatteryState, Image
from vision_msgs.msg import Detection2DArray
from std_srvs.srv import Empty
from nav2_msgs.action import NavigateToPose
from slam_toolbox.srv import SaveMap
from irobot_create_msgs.action import Dock, Undock
from irobot_create_msgs.msg import DockStatus
from cv_bridge import CvBridge
import base64

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== OAK-D YOLOv8nano 检测 ====================
# 常用中文 → 英文 COCO 类名映射
CN2EN_CLASS = {
    "人": "person", "行人": "person",
    "椅子": "chair", "桌子": "dining table", "餐桌": "dining table",
    "杯子": "cup", "瓶": "bottle", "水瓶": "bottle", "酒瓶": "bottle",
    "手机": "cell phone", "笔记本": "laptop", "电脑": "laptop",
    "猫": "cat", "狗": "dog", "鸟": "bird", "马": "horse",
    "车": "car", "汽车": "car", "自行车": "bicycle", "摩托车": "motorcycle",
    "包": "backpack", "背包": "backpack", "手提包": "handbag",
    "书": "book", "遥控器": "remote", "钥匙": "keyboard",
    "门": "door", "冰箱": "refrigerator", "沙发": "couch",
    "盆栽": "potted plant", "花": "potted plant",
    "电视": "tv", "显示器": "tv", "微波炉": "microwave",
}
# COCO class name → 数字 ID (OAK-D YOLOv8nano 输出)
COCO_CLASS_TO_ID = {
    "person": 0, "bicycle": 1, "car": 2, "motorcycle": 3, "airplane": 4,
    "bus": 5, "train": 6, "truck": 7, "boat": 8, "traffic light": 9,
    "fire hydrant": 10, "stop sign": 11, "parking meter": 12, "bench": 13,
    "bird": 14, "cat": 15, "dog": 16, "horse": 17, "sheep": 18, "cow": 19,
    "elephant": 20, "bear": 21, "zebra": 22, "giraffe": 23, "backpack": 24,
    "umbrella": 25, "handbag": 26, "tie": 27, "suitcase": 28, "frisbee": 29,
    "skis": 30, "snowboard": 31, "sports ball": 32, "kite": 33,
    "baseball bat": 34, "baseball glove": 35, "skateboard": 36,
    "surfboard": 37, "tennis racket": 38, "bottle": 39, "wine glass": 40,
    "cup": 41, "fork": 42, "knife": 43, "spoon": 44, "bowl": 45,
    "banana": 46, "apple": 47, "sandwich": 48, "orange": 49,
    "broccoli": 50, "carrot": 51, "hot dog": 52, "pizza": 53,
    "donut": 54, "cake": 55, "chair": 56, "couch": 57,
    "potted plant": 58, "bed": 59, "dining table": 60, "toilet": 61,
    "tv": 62, "laptop": 63, "mouse": 64, "remote": 65, "keyboard": 66,
    "cell phone": 67, "microwave": 68, "oven": 69, "toaster": 70,
    "sink": 71, "refrigerator": 72, "book": 73, "clock": 74,
    "vase": 75, "scissors": 76, "teddy bear": 77, "hair drier": 78,
    "toothbrush": 79,
}
NN_FRAME_SIZE = 416  # OAK-D YOLO 输入分辨率

# ==================== 默认初始位姿（在此修改） ====================
DEFAULT_INITIAL_POSE = {
    "x": -3.25,
    "y": 3.1,
    "theta": 90,         # 朝向角度（度），0=正前方
    "repeat": 5,
    "interval_sec": 1.0,
}

# ==================== 充电桩配置 ====================
DOCK_POSITION = {
    "x": -3.25,
    "y": 2.95,
    "theta": 90,         # 充电桩朝向（度），机器人会从前方接近
}
DOCK_APPROACH_DISTANCE = 0.8   # 先导航到充电桩前方多少米
UNDOCK_BACKUP_DISTANCE = 1.0   # 离开时后退多少米


# ==================== FastAPI应用 ====================
app = FastAPI(
    title="OpenClaw TurtleBot4 Direct ROS Bridge",
    description="直接调用Nav2和SLAM的高性能方案",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 数据模型 ====================
class NavigationGoal(BaseModel):
    x: float
    y: float
    theta: float = 0.0
    frame_id: str = "map"
    wait: bool = False  # true=阻塞等待导航完成再返回

class MoveCommand(BaseModel):
    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0
    duration: Optional[float] = None

class DetectionRequest(BaseModel):
    object: str  # 目标物体名称，中英文均可（如 "person"、"人"、"椅子"）
    timeout_sec: float = 20.0  # 最多等多少秒（原地慢速旋转扫描）
    confidence: float = 0.4  # 最小置信度

class CenterRequest(BaseModel):
    object: str  # 目标物体名称，中英文均可
    timeout_sec: float = 30.0  # 总超时
    confidence: float = 0.4  # 最小置信度
    center_tolerance_pct: float = 0.08  # 居中容忍范围（画面宽度比例）
    max_center_iter: int = 10  # 居中对准最大迭代次数
    hfov_deg: float = 42.0  # OAK-D NN 中心裁剪后的有效水平视场角
    scan_angular: float = 0.4  # Phase 1 扫描旋转速度 rad/s
    align_angular: float = 0.3  # Phase 2 对准最大旋转速度 rad/s


class MapName(BaseModel):
    name: str

class RobotStatus(BaseModel):
    x: float
    y: float
    theta: float
    battery_percentage: Optional[float] = None
    is_navigating: bool = False


class InitialPoseRequest(BaseModel):
    x: float = DEFAULT_INITIAL_POSE["x"]
    y: float = DEFAULT_INITIAL_POSE["y"]
    theta: float = DEFAULT_INITIAL_POSE["theta"]
    repeat: int = DEFAULT_INITIAL_POSE["repeat"]
    interval_sec: float = DEFAULT_INITIAL_POSE["interval_sec"]

# ==================== ROS 2 节点 ====================
class TurtleBot4Controller(Node):
    """TurtleBot4 ROS 2控制节点"""
    
    def __init__(self):
        super().__init__('openclaw_tb4_controller')
        
        # 回调组（允许并发）
        self.callback_group = ReentrantCallbackGroup()
        
        # ===== 发布器 =====
        self.cmd_vel_pub = self.create_publisher(
            Twist, '/cmd_vel', 10
        )
        self.initialpose_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/initialpose', 10
        )
        
        # ===== 订阅器 =====
        # QoS 配置，匹配 Create3 的 BEST_EFFORT 发布模式
        qos_best_effort = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT
        )
        # 订阅机器人位姿（从 odom），对齐 Create3 直连 QoS
        qos_odom = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.odom_sub = self.create_subscription(
            Odometry, '/odom', self.odom_callback, qos_odom
        )
        
        # 订阅电池状态
        self.battery_sub = self.create_subscription(
            BatteryState, '/battery_state', self.battery_callback, qos_best_effort
        )

        # 充电桩状态
        self.dock_status_sub = self.create_subscription(
            DockStatus, '/dock_status', self.dock_status_callback, qos_best_effort
        )

        # OAK-D 相机（传感器 QoS）
        qos_sensor = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.camera_sub = self.create_subscription(
            Image, '/oakd/rgb/preview/image_raw', self.camera_callback, qos_sensor
        )
        self.camera_full_sub = None  # 全分辨率订阅器，按需创建，避免持续占用 WiFi 带宽
        self.cv_bridge = CvBridge()
        self.latest_image = None  # 最新预览帧 250×250，YOLO 检测用
        self.latest_image_time = None
        self.latest_full_image = None  # 最新全分辨率帧 1280×720，拍照用
        self.latest_full_image_time = None
        self.latest_detections = []  # OAK-D YOLOv8nano 最新检测结果
        self.latest_detections_time = None

        # 订阅 OAK-D 检测结果（替代本地 YOLO）
        self.oakd_detection_sub = self.create_subscription(
            Detection2DArray, '/oakd/nn/detections', self.oakd_detection_callback, qos_sensor
        )

        # ===== Action 客户端 =====
        # Nav2导航Action
        self.nav_client = ActionClient(
            self,
            NavigateToPose,
            '/navigate_to_pose',
            callback_group=self.callback_group
        )

        # Create3 充电桩对接
        self.dock_client = ActionClient(
            self,
            Dock,
            '/dock',
            callback_group=self.callback_group
        )
        self.undock_client = ActionClient(
            self,
            Undock,
            '/undock',
            callback_group=self.callback_group
        )
        
        # ===== 服务客户端 =====
        # SLAM建图服务
        self.save_map_client = self.create_client(
            SaveMap, '/slam_toolbox/save_map'
        )
        
        # ===== 状态变量 =====
        self.current_pose = None
        self.battery_percentage = None
        self.navigation_goal_handle = None
        self.is_navigating = False
        self.is_docked = False
        self._undock_lock = threading.Lock()
        self.last_initial_pose = {
            "x": DEFAULT_INITIAL_POSE["x"],
            "y": DEFAULT_INITIAL_POSE["y"],
            "qz": 0.0,
            "qw": 1.0,
            "cov_x": 0.01,
            "cov_y": 0.01,
            "cov_yaw": 0.001,
        }
        
        # 目标速度（用于持续发布）
        self.target_twist = Twist()

        # TF 广播：将 /odom 转为 odom→base_link
        # 使用 TRANSIENT_LOCAL 以匹配 AMCL TransformListener 对 /tf_static 的订阅
        tf_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.tf_pub = self.create_publisher(TFMessage, '/tf', tf_qos)
        logger.info("  ✓ odom→TF 桥接就绪 (TRANSIENT_LOCAL)")

        # 定时发布速度命令（应对 ROS 2 Watchdog）
        self.cmd_vel_timer = self.create_timer(
            0.1,  # 10Hz
            self.timer_callback,
            callback_group=self.callback_group
        )
        
        logger.info("✅ TurtleBot4Controller节点已初始化")
    
    # ========== 回调函数 ==========
    def timer_callback(self):
        """定时发布速度命令"""
        self.cmd_vel_pub.publish(self.target_twist)
    
    def odom_callback(self, msg: Odometry):
        """里程计回调，更新机器人位姿并广播 odom→base_link TF"""
        try:
            self.current_pose = msg.pose.pose

            t = TransformStamped()
            t.header.stamp = self.get_clock().now().to_msg()
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_link'
            t.transform.translation.x = msg.pose.pose.position.x
            t.transform.translation.y = msg.pose.pose.position.y
            t.transform.translation.z = msg.pose.pose.position.z
            t.transform.rotation = msg.pose.pose.orientation

            tf_msg = TFMessage()
            tf_msg.transforms = [t]
            self.tf_pub.publish(tf_msg)
        except Exception:
            logger.exception("odom_callback 异常")
    
    def battery_callback(self, msg: BatteryState):
        """电池状态回调"""
        self.battery_percentage = msg.percentage * 100

    def dock_status_callback(self, msg: DockStatus):
        """充电桩状态回调"""
        self.is_docked = bool(msg.is_docked)

    def camera_callback(self, msg: Image):
        """OAK-D 预览帧回调 250×250，YOLO 检测用"""
        try:
            self.latest_image = self.cv_bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.latest_image_time = time.time()
        except Exception:
            pass

    def camera_full_callback(self, msg: Image):
        """OAK-D 全分辨率回调 1280×720，拍照用"""
        try:
            self.latest_full_image = self.cv_bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.latest_full_image_time = time.time()
        except Exception:
            pass

    def camera_full_subscribe(self):
        """按需订阅全分辨率图像，避免持续占用 WiFi 带宽"""
        if self.camera_full_sub is None:
            qos_sensor = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
            self.camera_full_sub = self.create_subscription(
                Image, '/oakd/rgb/image_raw', self.camera_full_callback, qos_sensor
            )
            logger.info("📷 全分辨率图像订阅已开启")

    def camera_full_unsubscribe(self):
        """取消全分辨率订阅，释放 WiFi 带宽"""
        if self.camera_full_sub is not None:
            self.destroy_subscription(self.camera_full_sub)
            self.camera_full_sub = None
            self.latest_full_image = None
            self.latest_full_image_time = None
            logger.info("📷 全分辨率图像订阅已关闭")

    def oakd_detection_callback(self, msg: Detection2DArray):
        """OAK-D YOLOv8nano 检测结果回调（替代本地 YOLO）"""
        self.latest_detections = msg.detections
        self.latest_detections_time = time.time()

    def check_oakd_detections(self, target_class: str, confidence: float = 0.4):
        """检查 OAK-D 检测结果中是否有目标物体。
        返回: {"found": True, "bbox": [x1, y1, x2, y2], "confidence": 0.9, "class": "..."}
              或 {"found": False}"""
        if not self.latest_detections:
            return {"found": False}

        target_id = COCO_CLASS_TO_ID.get(target_class.lower())
        if target_id is None:
            logger.warning(f"未知类别: {target_class}")
            return {"found": False}

        for det in self.latest_detections:
            if not det.results:
                continue
            cls_id = int(det.results[0].hypothesis.class_id)
            cls_score = det.results[0].hypothesis.score
            if cls_id == target_id and cls_score >= confidence:
                cx = det.bbox.center.position.x
                cy = det.bbox.center.position.y
                sw = det.bbox.size_x
                sh = det.bbox.size_y
                x1 = cx - sw / 2.0
                y1 = cy - sh / 2.0
                x2 = cx + sw / 2.0
                y2 = cy + sh / 2.0
                return {
                    "found": True,
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(float(cls_score), 3),
                    "class": target_class,
                }
        return {"found": False}

    # ========== 基础移动控制 ==========
    def publish_velocity(self, linear_x: float, linear_y: float, angular_z: float):
        """更新目标速度，由定时器负责发布"""
        self.target_twist.linear.x = float(linear_x)
        self.target_twist.linear.y = float(linear_y)
        self.target_twist.angular.z = float(angular_z)
        logger.info(f"📤 更新目标速度: linear_x={linear_x}, angular_z={angular_z}")
    
    def stop_robot(self):
        """停止机器人"""
        self.publish_velocity(0.0, 0.0, 0.0)
        logger.info("🛑 机器人已停止目标速度")

    # ========== 初始位姿 ==========
    def _build_initial_pose_msg(
        self,
        x: float,
        y: float,
        qz: float,
        qw: float,
    ) -> PoseWithCovarianceStamped:
        """构造 AMCL 初始位姿消息"""
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        # stamp=0 → TF2 自动使用最新可用 transform，不受 Jetson/Pi 时钟偏移影响
        msg.header.stamp = Time(seconds=0, nanoseconds=0).to_msg()

        msg.pose.pose.position.x = float(x)
        msg.pose.pose.position.y = float(y)
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.x = 0.0
        msg.pose.pose.orientation.y = 0.0
        msg.pose.pose.orientation.z = float(qz)
        msg.pose.pose.orientation.w = float(qw)

        msg.pose.covariance[0] = self.last_initial_pose["cov_x"]
        msg.pose.covariance[7] = self.last_initial_pose["cov_y"]
        msg.pose.covariance[35] = self.last_initial_pose["cov_yaw"]
        return msg

    async def publish_initial_pose(
        self,
        x: float,
        y: float,
        qz: float,
        qw: float,
        repeat: int = 5,
        interval_sec: float = 1.0,
    ):
        """重复发布初始位姿，发布前等待 AMCL 订阅者就绪"""
        repeat = max(1, int(repeat))
        interval_sec = max(0.1, float(interval_sec))

        self.last_initial_pose.update({
            "x": float(x),
            "y": float(y),
            "qz": float(qz),
            "qw": float(qw),
        })

        # 等待 AMCL 订阅 /initialpose（DDS 发现需要几秒）
        for _ in range(5):  # 最多等 5 秒
            count = self.initialpose_pub.get_subscription_count()
            if count > 0:
                logger.info(f"✅ /initialpose 已有 {count} 个订阅者")
                break
            await asyncio.sleep(1.0)
        # 无论是否检测到订阅者都发布，DDS 发现可能滞后但消息不会丢

        for index in range(repeat):
            msg = self._build_initial_pose_msg(x, y, qz, qw)
            self.initialpose_pub.publish(msg)
            logger.info(
                f"📍 已发布初始位姿 {index + 1}/{repeat}: "
                f"x={x}, y={y}, qz={qz}, qw={qw}"
            )
            if index < repeat - 1:
                await asyncio.sleep(interval_sec)

        return {
            "status": "success",
            "message": "初始位姿已发布",
            "pose": {
                "x": float(x),
                "y": float(y),
                "qz": float(qz),
                "qw": float(qw),
            }
        }
    
    # ========== 辅助：等待 rclpy Future ==========
    async def _await_rclpy_future(self, future, timeout_sec: float = 120.0):
        """轮询等待 rclpy.task.Future 完成（rclpy Future 不兼容 asyncio.wrap_future）"""
        start = time.time()
        while not future.done():
            if time.time() - start > timeout_sec:
                raise Exception(f"等待ROS 2操作超时 ({timeout_sec}s)")
            await asyncio.sleep(0.05)
        # 获取结果，如果有异常会在此抛出
        return future.result()

    # ========== Nav2导航 ==========
    async def navigate_to_pose(self, x: float, y: float, theta: float = 0.0, frame_id: str = "map"):
        """导航到指定位姿"""

        # 如果在充电桩上，先自动脱离
        if self.is_docked:
            logger.info("🔌 检测到在充电桩上，先脱离...")
            undock_result = await self.undock()
            if undock_result["status"] == "success":
                logger.info("⏳ 等待 AMCL 定位收敛...")
                await asyncio.sleep(5)
            elif undock_result["status"] == "skipped":
                pass  # 另一个任务正在 undock，等它完成即可
            else:
                logger.warning(f"⚠️ undock 未成功 ({undock_result['message']})，继续尝试导航")

        # 等待Action服务器
        if not self.nav_client.wait_for_server(timeout_sec=30.0):
            raise Exception("Nav2 Action服务器不可用")

        # 构建目标消息
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = frame_id
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()

        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.position.z = 0.0

        # theta 是角度制，转为四元数（绕 Z 轴旋转）
        import math
        half = math.radians(theta) / 2
        goal_msg.pose.pose.orientation.z = math.sin(half)
        goal_msg.pose.pose.orientation.w = math.cos(half)

        logger.info(f"🎯 发送导航目标: ({x}, {y})")

        # 发送目标
        send_goal_future = self.nav_client.send_goal_async(goal_msg)

        # 等待目标被接受
        goal_handle = await self._await_rclpy_future(send_goal_future)

        if not goal_handle.accepted:
            logger.warning("⚠️ 导航目标被拒绝，等待 AMCL 收敛后重试...")
            await asyncio.sleep(5)
            send_goal_future = self.nav_client.send_goal_async(goal_msg)
            goal_handle = await self._await_rclpy_future(send_goal_future)
            if not goal_handle.accepted:
                raise Exception("导航目标被拒绝（AMCL 定位未收敛，请在 RViz 中手动设置初始位姿）")

        self.navigation_goal_handle = goal_handle
        self.is_navigating = True

        logger.info("✅ 导航目标已接受，机器人正在移动...")

        # 等待结果（异步）
        result_future = goal_handle.get_result_async()
        result = await self._await_rclpy_future(result_future)

        self.is_navigating = False

        status_names = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING",
                        4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
        status_name = status_names.get(result.status, f"CODE_{result.status}")

        if result.status == 4:  # SUCCEEDED
            logger.info("🎉 导航成功完成！")
            return {"status": "success", "message": "已到达目标位置"}
        else:
            logger.warning(f"⚠️  导航未成功，状态码: {result.status} ({status_name})")
            self.stop_robot()
            return {"status": "failed", "message": f"导航失败，状态: {result.status} ({status_name})"}
    
    def cancel_navigation(self):
        """取消当前导航"""
        if self.navigation_goal_handle and self.is_navigating:
            self.navigation_goal_handle.cancel_goal_async()
            self.is_navigating = False
            logger.info("❌ 导航已取消")
            return {"status": "success", "message": "导航已取消"}
        else:
            return {"status": "warning", "message": "当前没有进行中的导航"}

    # ========== 充电桩对接 ==========
    async def return_to_dock(self):
        """回到充电桩：先导航到前方接近点，再红外精确对接"""
        # 1. 取消当前导航
        self.cancel_navigation()

        # 2. 计算接近点（充电桩前方 DOCK_APPROACH_DISTANCE 米）
        import math
        theta_rad = math.radians(DOCK_POSITION["theta"])
        approach_x = DOCK_POSITION["x"] - DOCK_APPROACH_DISTANCE * math.cos(theta_rad)
        approach_y = DOCK_POSITION["y"] - DOCK_APPROACH_DISTANCE * math.sin(theta_rad)

        logger.info(f"🔌 第1步：导航到充电桩前方 ({approach_x:.2f}, {approach_y:.2f})")
        nav_result = await self.navigate_to_pose(approach_x, approach_y, DOCK_POSITION["theta"])
        if nav_result["status"] != "success":
            return {"status": "failed", "message": f"接近充电桩失败: {nav_result['message']}"}

        # 3. 等待 dock action server
        if not self.dock_client.wait_for_server(timeout_sec=5.0):
            return {"status": "failed", "message": "Dock action server 不可用"}

        # 4. 红外精确对接
        logger.info("🔌 第2步：红外精确对接...")
        dock_goal = Dock.Goal()
        send_future = self.dock_client.send_goal_async(dock_goal)
        goal_handle = await self._await_rclpy_future(send_future, timeout_sec=30.0)

        if not goal_handle.accepted:
            return {"status": "failed", "message": "Dock 请求被拒绝"}

        result_future = goal_handle.get_result_async()
        result = await self._await_rclpy_future(result_future, timeout_sec=60.0)

        if result.result.is_docked:
            logger.info("✅ 已精确对接充电桩")
            return {"status": "success", "message": "已精确回到充电桩", "is_docked": True}
        else:
            return {"status": "failed", "message": "对接未完成，可能未检测到红外信号"}

    async def undock(self):
        """脱离充电桩（并发安全：同一时间只允许一个 undock）"""
        if not self._undock_lock.acquire(blocking=False):
            logger.warning("⚠️ undock 已在执行中，跳过重复调用")
            return {"status": "skipped", "message": "undock 已在执行中"}
        try:
            if not self.is_docked:
                logger.info("ℹ️ 已在充电桩外，跳过 undock")
                return {"status": "success", "message": "已在充电桩外"}

            if not self.undock_client.wait_for_server(timeout_sec=5.0):
                return {"status": "failed", "message": "Undock action server 不可用"}

            logger.info("🔌 脱离充电桩...")
            undock_goal = Undock.Goal()
            send_future = self.undock_client.send_goal_async(undock_goal)
            goal_handle = await self._await_rclpy_future(send_future, timeout_sec=30.0)

            if not goal_handle.accepted:
                self.is_docked = False  # 被拒绝说明可能已经不在桩上
                return {"status": "failed", "message": "Undock 请求被拒绝"}

            result_future = goal_handle.get_result_async()
            result = await self._await_rclpy_future(result_future, timeout_sec=30.0)

            self.is_docked = bool(result.result.is_docked)
            if not self.is_docked:
                logger.info("✅ 已脱离充电桩")
            return {"status": "success", "message": "已脱离充电桩"}
        finally:
            self._undock_lock.release()

    async def undock_and_backup(self):
        """离开充电桩"""
        return await self.undock()

    # ========== SLAM建图 ==========
    async def save_map(self, map_name: str):
        """保存当前地图"""
        
        if not self.save_map_client.wait_for_service(timeout_sec=5.0):
            raise Exception("SLAM Toolbox保存地图服务不可用")
        
        request = SaveMap.Request()
        request.name.data = map_name
        
        logger.info(f"💾 保存地图: {map_name}")
        
        future = self.save_map_client.call_async(request)
        response = await self._await_rclpy_future(future)
        
        if response.result:
            logger.info(f"✅ 地图已保存: {map_name}")
            return {"status": "success", "message": f"地图 '{map_name}' 已保存"}
        else:
            raise Exception("地图保存失败")
    
    # ========== 状态查询 ==========
    def get_robot_status(self) -> RobotStatus:
        """获取机器人状态"""
        if self.current_pose:
            return RobotStatus(
                x=self.current_pose.position.x,
                y=self.current_pose.position.y,
                theta=round(
                    __import__("math").degrees(2 * __import__("math").atan2(
                        self.current_pose.orientation.z,
                        self.current_pose.orientation.w
                    )), 2
                ),  # Bug 3 修复：从四元数计算实际朝向角（度）
                battery_percentage=self.battery_percentage,
                is_navigating=self.is_navigating
            )
        else:
            return RobotStatus(
                x=0.0, y=0.0, theta=0.0,
                battery_percentage=self.battery_percentage,
                is_navigating=self.is_navigating
            )

# ==================== 全局ROS节点实例 ====================
ros_node: Optional[TurtleBot4Controller] = None
ros_executor = None

def init_ros():
    """初始化ROS节点"""
    global ros_node, ros_executor
    
    if not rclpy.ok():
        rclpy.init()
    
    ros_node = TurtleBot4Controller()
    
    # 在后台线程中spin
    from rclpy.executors import MultiThreadedExecutor
    ros_executor = MultiThreadedExecutor()
    ros_executor.add_node(ros_node)
    
    import threading
    spin_thread = threading.Thread(target=ros_executor.spin, daemon=True)
    spin_thread.start()
    
    logger.info("🚀 ROS 2节点已启动并在后台运行")

# ==================== FastAPI启动/关闭事件 ====================

async def _wait_for_nav2():
    """后台：等待 Nav2 controller_server 就绪（阻塞直到成功，超5分钟报警）"""
    WARN_SEC = 300
    start = time.time()
    last_warn = 0
    i = 0
    while True:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            "source /opt/ros/humble/setup.bash && ros2 node list 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if "controller_server" in stdout.decode():
            # 再确认 action server 也已就绪
            proc2 = await asyncio.create_subprocess_exec(
                "bash", "-c",
                "source /opt/ros/humble/setup.bash && ros2 action list 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout2, _ = await proc2.communicate()
            if "/navigate_to_pose" in stdout2.decode():
                logger.info("✅ Nav2 已就绪（controller_server + navigate_to_pose）")
                return True
        i += 1
        elapsed = time.time() - start
        if elapsed > WARN_SEC and elapsed - last_warn > 60:
            logger.warning(f"⚠️ 等待 Nav2 已超过 {elapsed:.0f}s，请检查树莓派是否正常")
            last_warn = elapsed
        else:
            logger.info(f"⏳ 等待 Nav2 就绪 (第{i}次，30s 后重试)...")
        await asyncio.sleep(30)


async def _wait_for_sensors():
    """后台：等待 /scan 和 /odom 话题就绪（阻塞直到成功，超5分钟报警）"""
    WARN_SEC = 300
    start = time.time()
    last_warn = 0
    i = 0
    while True:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            "source /opt/ros/humble/setup.bash && ros2 topic list 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        topics = stdout.decode()
        if "/scan" in topics and "/odom" in topics:
            logger.info("✅ 传感器话题已就绪")
            return True
        i += 1
        elapsed = time.time() - start
        if elapsed > WARN_SEC and elapsed - last_warn > 60:
            logger.warning(f"⚠️ 等待传感器话题已超过 {elapsed:.0f}s，请检查树莓派是否正常")
            last_warn = elapsed
        else:
            logger.info(f"⏳ 等待传感器话题 (第{i}次，10s 后重试)...")
        await asyncio.sleep(10)


async def _wait_for_odom_data():
    """后台：等待 bridge 自身收到 /odom 数据（阻塞直到成功，超5分钟报警）"""
    WARN_SEC = 300
    start = time.time()
    last_warn = 0
    i = 0
    while True:
        if ros_node.current_pose is not None:
            logger.info("✅ /odom 里程计数据已就绪")
            return True
        i += 1
        elapsed = time.time() - start
        if elapsed > WARN_SEC and elapsed - last_warn > 60:
            logger.warning(f"⚠️ 等待 /odom 数据已超过 {elapsed:.0f}s，请检查树莓派是否正常")
            last_warn = elapsed
        else:
            logger.info(f"⏳ 等待 /odom 数据 (第{i}次，10s 后重试)...")
        await asyncio.sleep(10)


async def _publish_initial_pose_and_wait_amcl():
    """后台：发布初始位姿并等待 AMCL 收敛（阻塞直到成功，超5分钟报警）"""
    import math
    WARN_SEC = 300
    half = math.radians(DEFAULT_INITIAL_POSE["theta"]) / 2
    qz = math.sin(half)
    qw = math.cos(half)

    # 等待 AMCL 节点出现
    start = time.time()
    last_warn = 0
    i = 0
    while True:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            "source /opt/ros/humble/setup.bash && ros2 node list 2>/dev/null | grep /amcl",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if "/amcl" in stdout.decode():
            logger.info("✅ AMCL 节点已出现，发布初始位姿...")
            break
        i += 1
        elapsed = time.time() - start
        if elapsed > WARN_SEC and elapsed - last_warn > 60:
            logger.warning(f"⚠️ 等待 AMCL 节点已超过 {elapsed:.0f}s，请检查树莓派是否正常")
            last_warn = elapsed
        else:
            logger.info(f"⏳ 等待 AMCL 节点 (第{i}次，10s 后重试)...")
        await asyncio.sleep(10)

    await ros_node.publish_initial_pose(
        x=DEFAULT_INITIAL_POSE["x"],
        y=DEFAULT_INITIAL_POSE["y"],
        qz=qz,
        qw=qw,
        repeat=DEFAULT_INITIAL_POSE["repeat"],
        interval_sec=DEFAULT_INITIAL_POSE["interval_sec"],
    )
    logger.info("✅ 已自动发布默认初始位姿")

    # ros2 topic echo --once 在 DDS 发现层不可靠，改用固定等待
    # AMCL 收到初始位姿后需要约 10-20 个激光帧（/scan 7.7Hz → ~2-3s）来收敛粒子滤波
    # 留 15s 余量，等足后继续（Nav2 就绪检查会二次验证）
    CONVERGE_SEC = 15
    logger.info(f"⏳ 等待 AMCL 粒子滤波收敛（{CONVERGE_SEC}s）...")
    await asyncio.sleep(CONVERGE_SEC)
    logger.info("✅ AMCL 定位收敛等待完成")


async def _background_init():
    """后台初始化：先发初始位姿解锁 AMCL，再等 Nav2 等其他组件"""
    await _wait_for_sensors()
    await _wait_for_odom_data()
    await _publish_initial_pose_and_wait_amcl()  # 先发初始位姿，解锁 AMCL
    await _wait_for_nav2()  # AMCL 就绪后 Nav2 才能启动


@app.on_event("startup")
async def startup_event():
    """bridge 启动 — 立即初始化 ROS 节点，后台等待 Nav2/AMCL"""
    init_ros()
    logger.info("✅ OpenClaw-TurtleBot4 Direct Bridge 已启动")
    # 后台执行阻塞的初始化流程，不阻塞 HTTP 服务启动
    asyncio.create_task(_background_init())


@app.on_event("shutdown")
async def shutdown_event():
    """bridge 关闭 — 仅清理自身 ROS 节点，不影响 Nav2"""
    global ros_node, ros_executor

    if ros_executor:
        ros_executor.shutdown()
    if ros_node:
        ros_node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()

    logger.info("👋 OpenClaw-TurtleBot4 Direct Bridge 已关闭")

# ==================== API端点 ====================

@app.get("/")
async def root():
    """健康检查"""
    status = ros_node.get_robot_status() if ros_node else None
    return {
        "status": "running",
        "service": "OpenClaw TurtleBot4 Direct ROS Bridge",
        "ros_connected": ros_node is not None,
        "robot_status": status.dict() if status else None
    }

# ========== 移动控制 ==========
@app.post("/control/move")
async def control_move(cmd: MoveCommand, background_tasks: BackgroundTasks):
    """
    控制机器人移动
    
    示例：
    - 前进2秒: {"linear_x": 0.2, "angular_z": 0, "duration": 2}
    - 左转1秒: {"linear_x": 0, "angular_z": 0.5, "duration": 1}
    - 持续前进: {"linear_x": 0.2, "angular_z": 0} (不设置duration)
    """
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    try:
        # 立即发送速度命令
        ros_node.publish_velocity(cmd.linear_x, cmd.linear_y, cmd.angular_z)
        
        if cmd.duration and cmd.duration > 0:
            # 在后台任务中延迟停止
            def delayed_stop():
                import time
                time.sleep(cmd.duration)
                ros_node.stop_robot()
            
            background_tasks.add_task(delayed_stop)
            return {
                "status": "success", 
                "message": f"移动命令已发送，将在 {cmd.duration} 秒后自动停止"
            }
        
        return {
            "status": "success", 
            "message": "持续移动命令已发送（需手动停止）"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/control/stop")
async def control_stop():
    """紧急停止"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    ros_node.stop_robot()
    return {"status": "success", "message": "机器人已停止"}

@app.post("/control/continuous_move")
async def continuous_move(linear_x: float = 0.0, angular_z: float = 0.0):
    """
    持续移动控制（不会自动停止，需要手动调用stop）
    
    适合：
    - 遥控模式
    - 持续移动
    - 实时控制
    
    示例：
    - 持续前进: linear_x=0.2, angular_z=0
    - 持续转弯: linear_x=0, angular_z=0.5
    - 前进+转弯: linear_x=0.2, angular_z=0.3
    """
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    try:
        ros_node.publish_velocity(linear_x, 0.0, angular_z)
        return {
            "status": "success",
            "message": f"持续移动: linear_x={linear_x}, angular_z={angular_z}",
            "tip": "调用 /control/stop 停止移动"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== Nav2导航 ==========
@app.post("/navigation/goto")
async def navigate_to_goal(goal: NavigationGoal, background_tasks: BackgroundTasks):
    """
    使用Nav2导航到指定位置

    示例(异步): {"x": 1.0, "y": 0.5, "theta": 0.0}
    示例(同步): {"x": 1.0, "y": 0.5, "theta": 0.0, "wait": true}
    """
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    async def nav_task():
        try:
            result = await ros_node.navigate_to_pose(goal.x, goal.y, goal.theta, goal.frame_id)
            logger.info(f"导航结果: {result}")
            return result
        except Exception as e:
            logger.error(f"导航任务异常: {e}")
            return None

    try:
        if goal.wait:
            # 阻塞模式：等导航结束才返回，OpenClaw 可据此继续下一步
            result = await nav_task()
            return result
        else:
            # 异步模式：立即返回，导航在后台执行
            background_tasks.add_task(nav_task)
            return {
                "status": "success",
                "message": f"导航已启动，目标: ({goal.x}, {goal.y})"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/localization/initialize")
async def initialize_localization(pose: InitialPoseRequest):
    """发布 /initialpose，不传参数则使用 DEFAULT_INITIAL_POSE"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    import math
    half = math.radians(pose.theta) / 2
    qz = math.sin(half)
    qw = math.cos(half)

    try:
        result = await ros_node.publish_initial_pose(
            x=pose.x,
            y=pose.y,
            qz=qz,
            qw=qw,
            repeat=pose.repeat,
            interval_sec=pose.interval_sec,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/navigation/cancel")
async def cancel_navigation():
    """取消当前导航"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    return ros_node.cancel_navigation()


@app.post("/navigation/dock")
async def return_to_dock():
    """回到充电桩精确对接 — Nav2导航到前方 + 红外对准（同步等待完成再返回）"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    try:
        # Bug 2 修复：改为同步等待，确保 dock 真正完成后才返回
        # 原来是 background_tasks fire-and-forget，OpenClaw 拿到 success 后
        # 立即执行 stop_bridge.sh，导致 dock 动作被中途杀死
        result = await ros_node.return_to_dock()
        logger.info(f"Dock结果: {result}")
        return result
    except Exception as e:
        logger.error(f"充电桩对接任务异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/navigation/undock")
async def undock_with_backup(background_tasks: BackgroundTasks):
    """脱离充电桩并后退指定距离，避免转向时卡到充电桩"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    async def undock_task():
        try:
            result = await ros_node.undock_and_backup()
            logger.info(f"Undock结果: {result}")
        except Exception as e:
            logger.error(f"脱离充电桩任务异常: {e}")

    background_tasks.add_task(undock_task)
    return {
        "status": "success",
        "message": "正在脱离充电桩"
    }


# ========== 相机 ==========
@app.get("/camera/capture")
async def capture_image(max_wait_sec: float = 3.0, full_size: bool = False):
    """
    抓取 OAK-D 相机最新一帧，返回 base64 JPEG
    相机按需启动，用完即关，避免长期占用 DDS 带宽。

    参数: max_wait_sec - 最大等待时间（秒），默认 3s
          full_size    - 是否全尺寸 (1280x720)，默认 false 用预览流缩放到 640x360
    返回: {"status": "success", "image_base64": "...", "width": ..., "height": ...}
    """
    import cv2
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    await _camera_on(ros_node)
    try:
        if full_size:
            # 等待全分辨率帧
            ros_node.latest_full_image_time = None
            waited = 0.0
            while ros_node.latest_full_image is None or \
                  time.time() - (ros_node.latest_full_image_time or 0) > 0.5:
                if waited >= max_wait_sec:
                    if ros_node.latest_full_image is not None:
                        break
                    raise HTTPException(status_code=503, detail="全分辨率图像无数据，请确认 OAK-D 驱动已启动")
                await asyncio.sleep(0.2)
                waited += 0.2
            img = ros_node.latest_full_image.copy()
        else:
            # 等待预览帧
            ros_node.latest_image_time = None
            waited = 0.0
            while ros_node.latest_image is None or \
                  time.time() - (ros_node.latest_image_time or 0) > 0.5:
                if waited >= max_wait_sec:
                    if ros_node.latest_image is not None:
                        break
                    raise HTTPException(status_code=503, detail="相机无数据，请确认 OAK-D 驱动已启动")
                await asyncio.sleep(0.2)
                waited += 0.2
            img = ros_node.latest_image.copy()
            img = cv2.resize(img, (640, 360), interpolation=cv2.INTER_AREA)

        success, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not success:
            raise HTTPException(status_code=500, detail="图片编码失败")

        file_path = "/tmp/openclaw_capture.jpg"
        with open(file_path, "wb") as f:
            f.write(jpg.tobytes())

        return {
            "status": "success",
            "file_path": file_path,
            "image_base64": base64.b64encode(jpg.tobytes()).decode(),
            "width": img.shape[1],
            "height": img.shape[0],
        }
    finally:
        await _camera_off(ros_node)


@app.get("/camera/detect")
async def detect_object(req: DetectionRequest = Depends()):
    """
    OAK-D YOLOv8nano 扫描检测（无需启停相机，NN 始终运行）。
    """
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    target = req.object.strip()
    target_en = CN2EN_CLASS.get(target, target)

    logger.info(f"🔍 OAK-D YOLO 扫描检测: '{target}' → class='{target_en}', timeout={req.timeout_sec}s")

    # 确保相机在运行（OAK-D NN 始终在跑，这里只是保底）
    await _camera_on(ros_node)

    SCAN_ANGULAR = 0.4
    ros_node.publish_velocity(0.0, 0.0, SCAN_ANGULAR)

    start_time = time.time()
    try:
        while time.time() - start_time < req.timeout_sec:
            result = ros_node.check_oakd_detections(target_en, req.confidence)
            if result["found"]:
                ros_node.stop_robot()
                logger.info(f"✅ 检测到 {target_en} (置信度: {result['confidence']})")
                return {"status": "found", **result}

            await asyncio.sleep(0.15)  # OAK-D YOLO 15FPS，比本地快

    finally:
        ros_node.stop_robot()

    elapsed = time.time() - start_time
    logger.info(f"❌ 扫描完成，未检测到 {target_en}，已旋转 {elapsed:.1f}s")
    return {
        "status": "not_found",
        "message": f"未检测到 {target}，已旋转扫描 {elapsed:.1f}s",
    }


@app.get("/camera/detect-and-center")
async def detect_and_center(req: CenterRequest = Depends()):
    """
    OAK-D YOLOv8nano 检测 + 闭环居中 + 拍照（NN 始终运行，无需启停相机）。
    """
    import math

    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")

    target = req.object.strip()
    target_en = CN2EN_CLASS.get(target, target)
    tolerance_pct = max(0.02, min(0.25, req.center_tolerance_pct))
    hfov_rad = math.radians(max(1.0, min(180.0, req.hfov_deg)))
    max_iter = max(3, min(30, req.max_center_iter))
    scan_angular = max(0.1, min(1.0, req.scan_angular))
    align_angular_max = max(0.05, min(0.5, req.align_angular))

    logger.info(f"🔍 检测+居中(ONNX): '{target}' → en='{target_en}', timeout={req.timeout_sec}s")

    await _camera_on(ros_node)  # 保底确保相机在运行

    # ==================== Phase 1: 旋转扫描 ====================
    ros_node.publish_velocity(0.0, 0.0, scan_angular)
    phase1_start = time.time()

    while time.time() - phase1_start < req.timeout_sec:
        result = ros_node.check_oakd_detections(target_en, req.confidence)
        if result["found"]:
            ros_node.stop_robot()
            last_detection = result
            logger.info(f"✅ Phase 1 检测到 {target_en} (置信度: {result['confidence']})")
            break
        await asyncio.sleep(0.15)
    else:
        elapsed = time.time() - phase1_start
        return {
            "status": "not_found",
            "message": f"未检测到 {target}，已旋转扫描 {elapsed:.1f}s",
        }

    # ==================== Phase 2: 闭环居中 ====================
    # OAK-D bbox 在 416×416 NN 帧坐标系中
    image_center_x = NN_FRAME_SIZE / 2.0
    tolerance_px = NN_FRAME_SIZE * tolerance_pct
    final_offset_px = float("inf")
    last_direction = 0
    phase2_deadline = time.time() + 10.0
    iteration = 0

    while iteration < max_iter and time.time() < phase2_deadline:
        iteration += 1

        result = ros_node.check_oakd_detections(target_en, req.confidence)

        if not result["found"]:
            logger.warning("Phase 2 丢失目标，尝试反向回找...")
            result = await _reverse_scan_recover(
                ros_node, target_en, req.confidence, last_direction, timeout_sec=3.0
            )
            if not result["found"]:
                ros_node.stop_robot()
                await _camera_full_on(ros_node)
                await _capture_and_save()
                ros_node.camera_full_unsubscribe()
                return {
                    "status": "found_lost",
                    "class": target_en,
                    "centered": False,
                    "message": "Phase 1 检测到目标，居中过程中丢失，已对最后方向拍照",
                    "file_path": "/tmp/openclaw_capture.jpg",
                }
            logger.info("✅ 反向回找成功，继续居中")

        bbox_center_x = (result["bbox"][0] + result["bbox"][2]) / 2.0
        offset_px = bbox_center_x - image_center_x
        final_offset_px = offset_px

        if abs(offset_px) < tolerance_px:
            logger.info(f"✅ 已居中: offset={offset_px:.0f}px (迭代{iteration}次)")
            break

        current_direction = 1 if offset_px > 0 else -1
        if last_direction != 0 and current_direction != last_direction and abs(offset_px) < tolerance_px * 1.5:
            logger.info(f"检测到震荡，停止对准 (offset={offset_px:.0f}px, 迭代{iteration}次)")
            break
        last_direction = current_direction

        fraction = abs(offset_px) / (NN_FRAME_SIZE / 2.0)
        angular_err = fraction * (hfov_rad / 2.0)
        angular_vel = math.copysign(min(angular_err, align_angular_max), offset_px)
        angular_vel = max(-align_angular_max, min(align_angular_max, angular_vel))

        logger.info(f"  ↻ 脉冲 {iteration}: offset={offset_px:.0f}px, angular={angular_vel:.3f}rad/s")
        ros_node.publish_velocity(0.0, 0.0, angular_vel)
        await asyncio.sleep(0.4)
        ros_node.stop_robot()
        await asyncio.sleep(0.3)  # 等 OAK-D NN 管道刷新 (~150ms 延迟)
    else:
        logger.warning(f"Phase 2 超时 (10s)，以当前 offset={final_offset_px:.0f}px 拍照")

    # ==================== Phase 3: 拍照 ====================
    ros_node.stop_robot()
    await asyncio.sleep(0.2)
    await _camera_full_on(ros_node)
    await _capture_and_save()
    ros_node.camera_full_unsubscribe()

    return {
        "status": "found_centered",
        "class": target_en,
        "confidence": last_detection["confidence"] if last_detection else 0.0,
        "centered": abs(final_offset_px) < tolerance_px,
        "final_offset_px": round(abs(final_offset_px)),
        "file_path": "/tmp/openclaw_capture.jpg",
    }


async def _reverse_scan_recover(ros_node, target_en: str, confidence: float,
                                last_direction: int, timeout_sec: float = 3.0):
    """目标丢失后反向旋转回找，最多 timeout_sec 秒（使用 OAK-D 检测）"""
    reverse_angular = -0.3 if last_direction > 0 else 0.3  # 反方向
    if last_direction == 0:
        reverse_angular = -0.3  # 默认向左回找

    ros_node.publish_velocity(0.0, 0.0, reverse_angular)
    start = time.time()
    try:
        while time.time() - start < timeout_sec:
            result = ros_node.check_oakd_detections(target_en, confidence)
            if result["found"]:
                return result
            await asyncio.sleep(0.15)
    finally:
        ros_node.stop_robot()

    return {"found": False}


async def _capture_and_save():
    """拍照并保存到 /tmp/openclaw_capture.jpg"""
    import cv2
    if not ros_node or ros_node.latest_full_image is None:
        return
    img = ros_node.latest_full_image.copy()
    success, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if success:
        with open("/tmp/openclaw_capture.jpg", "wb") as f:
            f.write(jpg.tobytes())


async def _camera_on(ros_node=None):
    """按需启动 OAK-D 相机（不订阅全分辨率，仅启动相机流）"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            "source /opt/ros/humble/setup.bash && ros2 service call /oakd/start_camera std_srvs/srv/Trigger 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if "success=True" in stdout.decode():
            logger.info("📷 OAK-D 相机已启动（按需）")
            return True
    except Exception:
        pass
    return False


async def _camera_full_on(ros_node):
    """按需订阅全分辨率图像（1280×720），用于拍照"""
    ros_node.camera_full_subscribe()
    # 等待第一帧到来
    ros_node.latest_full_image_time = None
    for _ in range(15):
        if ros_node.latest_full_image is not None:
            logger.info("📸 全分辨率图像就绪")
            return True
        await asyncio.sleep(0.2)
    logger.warning("⚠️ 全分辨率图像超时")
    return False


async def _camera_off(ros_node=None):
    """用完即关，避免相机流长期占用 DDS 带宽"""
    if ros_node:
        ros_node.camera_full_unsubscribe()
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            "source /opt/ros/humble/setup.bash && ros2 service call /oakd/stop_camera std_srvs/srv/Trigger 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        logger.info("📷 OAK-D 相机已关闭")
    except Exception:
        pass


# ========== SLAM建图 ==========
@app.post("/mapping/save")
async def save_map(map_data: MapName):
    """
    保存当前地图
    
    示例: {"name": "office_map"}
    """
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    try:
        result = await ros_node.save_map(map_data.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== 状态查询 ==========
@app.get("/status/robot")
async def get_robot_status():
    """获取机器人完整状态"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    status = ros_node.get_robot_status()
    return status

@app.get("/status/battery")
async def get_battery_status():
    """获取电池状态"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    return {
        "status": "success",
        "battery_percentage": ros_node.battery_percentage or 0.0
    }

@app.get("/status/pose")
async def get_robot_pose():
    """获取机器人位姿"""
    if not ros_node:
        raise HTTPException(status_code=500, detail="ROS节点未初始化")
    
    if ros_node.current_pose:
        return {
            "status": "success",
            "x": ros_node.current_pose.position.x,
            "y": ros_node.current_pose.position.y,
            "z": ros_node.current_pose.position.z
        }
    else:
        return {"status": "warning", "message": "位姿数据尚未可用"}

# ========== OpenClaw简化接口 ==========
@app.post("/openclaw/move")
async def openclaw_move(
    direction: str, 
    speed: float = 0.2, 
    duration: Optional[float] = None,
    background_tasks: BackgroundTasks = None
):
    """OpenClaw专用：简化的移动接口"""
    direction_map = {
        "forward": {"linear_x": speed, "angular_z": 0},
        "backward": {"linear_x": -speed, "angular_z": 0},
        "turn_left": {"linear_x": 0, "angular_z": speed},
        "turn_right": {"linear_x": 0, "angular_z": -speed},
        "stop": {"linear_x": 0, "angular_z": 0}
    }
    
    if direction not in direction_map:
        raise HTTPException(status_code=400, detail=f"无效的方向: {direction}")
    
    params = direction_map[direction]
    cmd = MoveCommand(
        linear_x=params["linear_x"],
        angular_z=params["angular_z"],
        duration=duration if direction != "stop" else None
    )
    
    return await control_move(cmd, background_tasks)

@app.get("/openclaw/functions")
async def get_openclaw_functions():
    """返回OpenClaw函数定义"""
    return {
        "service": "OpenClaw TurtleBot4 Direct ROS Bridge",
        "functions": [
            {
                "name": "turtlebot4_initialize_pose",
                "description": "初始化机器人在地图中的位姿，供 AMCL 自动定位使用",
                "parameters": {
                    "x": "地图中的 x 坐标",
                    "y": "地图中的 y 坐标",
                    "theta": "朝向角度（度），0=正前方，90=左，180=后方",
                    "repeat": "重复发布次数，默认 5",
                    "interval_sec": "每次发布间隔秒数，默认 1.0"
                }
            },
            {
                "name": "turtlebot4_move",
                "description": "控制TurtleBot4移动",
                "parameters": {
                    "direction": "forward/backward/turn_left/turn_right/stop",
                    "speed": "速度 (默认0.2)",
                    "duration": "持续时间秒 (默认1.0)"
                }
            },
            {
                "name": "turtlebot4_navigate",
                "description": "导航到指定坐标",
                "parameters": {
                    "x": "X坐标",
                    "y": "Y坐标",
                    "theta": "朝向角度(可选)"
                }
            },
            {
                "name": "turtlebot4_save_map",
                "description": "保存当前地图",
                "parameters": {
                    "name": "地图名称"
                }
            },
            {
                "name": "turtlebot4_stop",
                "description": "停止机器人"
            },
            {
                "name": "turtlebot4_get_status",
                "description": "获取机器人状态"
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
