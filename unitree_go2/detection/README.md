# Go2 Vision Detection

## 项目简介

基于Unitree Go2 EDU四足机器人平台的视觉识别与三维定位系统。使用YOLOv8s对相机视野内的物体进行实时检测，结合RealSense D435i深度相机获取物体距离、三维坐标和水平方向角，并通过内置Flask服务推送带检测框的实时视频流。

主要功能：
- YOLOv8s目标检测（置信度阈值0.5）
- 基于对齐深度图的距离测量（14x14采样区域，异常值过滤，10帧滑动平均）
- 三维坐标（XYZ）和水平方向角计算
- MJPEG实时视频流推送（端口8002）
- 检测结果写入/tmp/go2_detections.json供其他模块读取

## 环境依赖

- 操作系统：Ubuntu 20.04 LTS
- ROS版本：ROS2 Foxy + CycloneDDS
- Python版本：Python 3.8
- 深度相机：Intel RealSense D435i
- 检测模型：YOLOv8s TensorRT engine
- 其他依赖：rclpy、cv_bridge、ultralytics、flask、opencv-python、numpy

## 安装方法

```bash
pip install ultralytics flask opencv-python numpy
```

ROS2环境配置（每次连接机器狗后执行）：
```bash
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=~/cyclonedds_ws/cyclonedds.xml
```

## 运行方法

终端1：启动相机与检测节点
```bash
# 启动相机
bash ~/start_realsense.sh

# 启动检测
python3 ~/detect_object.py

# 如果显示等待图像数据，执行以下命令重启相机服务
systemctl --user restart realsense.service
sleep 5
systemctl --user restart detect-object.service
```

终端2：启动网页控制面板
```bash
sudo fuser -k 8001/tcp
systemctl --user restart go2-http
```

视频流访问地址：http://192.168.1.3:8002/video_stream

## 文件结构

```
detection/
├── detect_object.py    # 主检测程序
└── README.md           # 说明文档
```

## 注意事项

- 标定文件路径：/home/unitree/calib_work/camera_matrix.npy 和 dist_coeffs.npy，需提前完成相机标定
- 模型文件路径：/home/unitree/yolov8s.engine，需提前转换为TensorRT engine格式
- 黑色、透明、圆柱形物体测距误差较大，建议在有效测距范围（0.3m~3m）内使用
