#!/usr/bin/env python3
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
import threading
import logging
from flask import Flask, Response

logging.getLogger('werkzeug').setLevel(logging.WARNING)

CALIB_MTX = np.load('/home/unitree/calib_work/camera_matrix.npy')
CALIB_DIST = np.load('/home/unitree/calib_work/dist_coeffs.npy')

FX = CALIB_MTX[0, 0]
FY = CALIB_MTX[1, 1]
CX = CALIB_MTX[0, 2]
CY = CALIB_MTX[1, 2]

distance_buffer = {}

# 全局变量：存储最新带框帧，供 MJPEG 流使用
annotated_frame = None
annotated_lock = threading.Lock()
frame_version = 0  # 帧版本号，跳过重复帧

# Flask MJPEG 服务器
video_app = Flask(__name__)

@video_app.route("/video_stream")
def video_stream():
    def gen():
        last_version = -1
        black_jpeg = (b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01'
                      b'\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07'
                      b'\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d'
                      b'\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f'
                      b'\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01"\x00'
                      b'\x02\x11\x01\x03\x11\x01\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03'
                      b'\x11\x00?\x00\xfa\x00')
        while True:
            global annotated_frame, frame_version
            with annotated_lock:
                ver = frame_version
                frame = annotated_frame.copy() if annotated_frame is not None else None
            if frame is not None and ver != last_version:
                # 缩小到 640px 宽，降低网络负担
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640.0 / w
                    frame = cv2.resize(frame, (640, int(h * scale)))
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                last_version = ver
            elif frame is None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + black_jpeg + b'\r\n')
            time.sleep(0.1)  # 匹配检测帧率 10Hz
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame',
                    headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive',
                             'X-Accel-Buffering': 'no'})

def run_video_server(port):
    """在独立线程中运行 Flask MJPEG 服务"""
    video_app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)

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

        self.create_timer(0.3, self.process)
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

        # —— 在当前帧上画检测框 ——
        annotated = self.color_image.copy()
        for det in detections:
            x1, y1 = det['x1'], det['y1']
            x2, y2 = det['x2'], det['y2']
            cx, cy = det['x'], det['y']
            label = det['label']
            conf = det['confidence']
            dist = det['distance']
            heading = det['heading_angle_deg']
            pos3d = det['position_3d']

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 3)
            dist_str = f'{dist:.2f}m' if dist is not None else '?'
            cv2.putText(annotated, f'{label} {conf:.0%} {dist_str}',
                        (x1-5, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            if heading is not None:
                cv2.putText(annotated, f'h:{heading:.1f}',
                            (x1-5, y2+22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 1)
            if pos3d and pos3d.get('x') is not None:
                cv2.putText(annotated, f'x:{pos3d["x"]:.2f} y:{pos3d.get("y",0):.2f} z:{pos3d.get("z",0):.2f}',
                            (x1-5, y2+44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 1)
            cv2.line(annotated, (cx-15, cy), (cx+15, cy), (0, 255, 0), 2)
            cv2.line(annotated, (cx, cy-15), (cx, cy+15), (0, 255, 0), 2)
            cv2.circle(annotated, (cx, cy), 3, (0, 0, 255), -1)

        # 存储带框帧供 MJPEG 流使用
        global annotated_frame, frame_version
        with annotated_lock:
            annotated_frame = annotated
            frame_version += 1
        # ——

        try:
            with open('/tmp/go2_detections.json', 'w') as f:
                json.dump({'timestamp': time.time(), 'detections': detections}, f)
        except Exception as e:
            self.get_logger().error(f'写入失败: {e}')

def main():
    import argparse
    parser = argparse.ArgumentParser(description="YOLO 检测 + MJPEG 视频流")
    parser.add_argument("--port", type=int, default=8002, help="MJPEG 视频流端口 (默认 8002)")
    args = parser.parse_args()

    # 启动 MJPEG 视频流线程
    video_thread = threading.Thread(target=run_video_server, args=(args.port,), daemon=True)
    video_thread.start()
    print(f'  ✓ MJPEG 视频流: http://0.0.0.0:{args.port}/video_stream')

    rclpy.init()
    node = DetectNode()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
