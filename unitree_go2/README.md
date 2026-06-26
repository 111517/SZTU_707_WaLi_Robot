# Unitree Go2

## 项目简介

基于Unitree Go2 EDU四足机器人平台的二次开发项目，依托NVIDIA Jetson Orin Nano计算板与Intel RealSense D435i深度相机，围绕视觉识别与三维定位、网页实时可视化、AI自然语言指令控制三个方向展开开发。

## 硬件平台

- 机器人：Unitree Go2 EDU
- 计算板：NVIDIA Jetson Orin Nano
- 深度相机：Intel RealSense D435i
- 主控板IP：192.168.123.161
- Orin Nano IP：192.168.1.3

## 软件环境

- 操作系统：Ubuntu 20.04 LTS
- ROS版本：ROS2 Foxy + CycloneDDS
- Python版本：Python 3.8

## 目录结构

```
unitree_go2/
├── detection/    # 视觉识别与三维定位
└── README.md     # 本文档
```

## ROS2环境配置

每次SSH（本地终端输入ssh unitree@192.168.1.3回车，密码：123）连接机器狗后需执行以下命令：

```bash
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=~/cyclonedds_ws/cyclonedds.xml
```

建议将以上命令写入~/.bashrc避免每次手动执行。

## 功能模块说明

### 1. 网页实时可视化

通过OpenClaw内置的HTTP接口提供网页控制面板（端口8001），实时显示机器狗的电量、传感器状态等数据，支持前进、后退、左转、右转等基础动作的手动控制。同时通过detect_object.py内置的Flask服务在8002端口推送带检测框的实时视频流，网页端可直接查看识别结果。

网页访问地址：http://192.168.1.3:8001

视频流地址：http://192.168.1.3:8002/video_stream

若接口网页显示狗离线，输入：
sudo fuser -k 8001/tcp
systemctl --user restart go2-http
狗会转成在线

### 2. AI自然语言指令控制

基于OpenClaw框架接入DeepSeek大模型，通过飞书长连接实现自然语言控制机器狗。同时提供本地网页控制面板（端口8001）支持手动操作。

启动OpenClaw：
```bash
openclaw gateway run
```

新开终端：
```bash
openclaw dashboard
```

飞书绑定：
```bash
openclaw feishu bind
```

扫码授权后即可通过飞书发送指令控制机器狗。



