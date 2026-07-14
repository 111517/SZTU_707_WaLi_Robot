#!/usr/bin/env python3
# import os
# import sys

# _gomp = '/home/unitree/.local/lib/python3.8/site-packages/torch/lib/libgomp-d22c30c5.so.1'
# if _gomp not in os.environ.get('LD_PRELOAD', ''):
#     os.environ['LD_PRELOAD'] = _gomp
#     os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge
import cv2
import numpy as np
from ultralytics import YOLO
import time
import json
import math

CALIB_MTX = np.load('/home/unitree/calib_work/camera_matrix.npy')
CALIB_DIST = np.load('/home/unitree/calib_work/dist_coeffs.npy')

FX = CALIB_MTX[0, 0]
FY = CALIB_MTX[1, 1]
CX = CALIB_MTX[0, 2]
CY = CALIB_MTX[1, 2]

distance_buffer = {}

class DetectNode(Node):
    def __init__(self):
        super().__init__('detect_node')
        self.bridge = CvBridge()
        self.model = YOLO('/home/unitree/yolov8s.engine')

        self.color_image = None
        self.depth_image = None
        self.depth_info = None

        self.create_subscription(Image, '/camera/color/image_raw', self.color_cb, 10)
        self.create_subscription(Image, '/camera/aligned_depth_to_color/image_raw', self.depth_cb, 10)
        self.create_subscription(CameraInfo, '/camera/depth/camera_info', self.depth_info_cb, 10)

        self.create_timer(0.1, self.process)
        self.get_logger().info(f'节点启动成功，使用标定内参 fx={FX:.1f} fy={FY:.1f} cx={CX:.1f} cy={CY:.1f}')

    def color_cb(self, msg):
        self.color_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

    def depth_cb(self, msg):
        self.depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')

    def depth_info_cb(self, msg):
        self.depth_info = msg

    def pixel_to_3d(self, cx, cy, distance_m):
        pts = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
        pts_undist = cv2.undistortPoints(pts, CALIB_MTX, CALIB_DIST, P=CALIB_MTX)
        cx_u = pts_undist[0, 0, 0]
        cy_u = pts_undist[0, 0, 1]
        angle_h = -math.atan2(cx_u - CX, FX)
        angle_v = math.atan2(cy_u - CY, FY)

        obj_x = round(distance_m * math.cos(angle_v) * math.cos(angle_h), 3)
        obj_y = round(-distance_m * math.cos(angle_v) * math.sin(angle_h), 3)
        obj_z = round(-distance_m * math.sin(angle_v), 3)
        heading_angle_deg = round(math.degrees(angle_h), 2)
        return obj_x, obj_y, obj_z, heading_angle_deg

    def get_smooth_distance(self, label, cx, cy, raw_distance):
        key = f'{label}_{cx//50}_{cy//50}'
        if key not in distance_buffer:
            distance_buffer[key] = []
        distance_buffer[key].append(raw_distance)
        if len(distance_buffer[key]) > 10:
            distance_buffer[key].pop(0)
        return round(float(np.mean(distance_buffer[key])), 2)

    def process(self):
        if self.color_image is None or self.depth_image is None:
            self.get_logger().info('等待图像数据...')
            return

        results = self.model(self.color_image, verbose=False)

        detections = []
        print('\n' + '='*60)
        print(f'时间: {time.strftime("%H:%M:%S")}')

        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            label = self.model.names[cls_id]
            confidence = float(box.conf[0])

            if confidence < 0.5:
                continue

            x1, y1, x2, y2 = box.xyxy[0]
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            distance_m = None
            error_m = None
            h, w = self.depth_image.shape
            if 0 <= cy < h and 0 <= cx < w:
                y_min, y_max = max(0, cy-7), min(h, cy+7)
                x_min, x_max = max(0, cx-7), min(w, cx+7)
                region = self.depth_image[y_min:y_max, x_min:x_max]
                valid = region[region > 0]
                if len(valid) > 0:
                    median = np.median(valid)
                    valid = valid[np.abs(valid - median) < 500]
                if len(valid) > 0:
                    raw_distance = float(np.median(valid)) / 1000.0
                    distance_m = self.get_smooth_distance(label, cx, cy, raw_distance)
                    error_m = round(float(np.std(valid)) / 1000.0, 3)

            obj_x, obj_y, obj_z, heading_angle_deg = None, None, None, None
            if distance_m is not None:
                obj_x, obj_y, obj_z, heading_angle_deg = self.pixel_to_3d(cx, cy, distance_m)

            print(f'  物体: {label:<12} 置信度: {confidence:.2f} | '
                  f'距离: {distance_m}m ± {error_m}m | '
                  f'方向角: {heading_angle_deg}° | '
                  f'XYZ: ({obj_x}, {obj_y}, {obj_z})')

            detections.append({
                'label': label,
                'confidence': round(confidence, 2),
                'x': cx,
                'y': cy,
                'x1': int(x1), 'y1': int(y1),
                'x2': int(x2), 'y2': int(y2),
                'distance': distance_m,
                'error': error_m,
                'heading_angle_deg': heading_angle_deg,
                'position_3d': {
                    'x': obj_x,
                    'y': obj_y,
                    'z': obj_z
                }
            })

        if not detections:
            print('  未检测到目标')

        try:
            with open('/tmp/go2_detections.json', 'w') as f:
                json.dump({'timestamp': time.time(), 'detections': detections}, f)
        except Exception as e:
            self.get_logger().error(f'写入失败: {e}')

def main():
    rclpy.init()
    node = DetectNode()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
