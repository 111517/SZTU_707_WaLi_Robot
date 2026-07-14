# UNITREE Go2 机器人开发项目

## 项目简介

本项目是围绕 **宇树科技 Unitree Go2 EDU** 四足机器人平台的综合二次开发工程（隶属 SZTU 707 WaLi Robot 项目），依托 NVIDIA Jetson Orin Nano 计算板与 Intel RealSense D435i 深度相机，涵盖 ROS 2 通信配置、SLAM 建图、自主导航、视觉识别与三维定位、网页实时可视化、AI 自然语言指令控制等完整功能链。

运行平台为 Go2 机载计算机（Orin Nano，Ubuntu 20.04 + ROS 2 Foxy）及外部 PC（Ubuntu 22.04 + ROS 2 Humble），通过有线以太网或 SSH 连接，使用 CycloneDDS 进行通信。

主要功能包括：

- 基于 unitree_ros2 SDK 的机器人状态读取与运动控制
- 基于 slam_toolbox / KISS-ICP 的激光 SLAM 建图
- 基于 Nav2 + AMCL 的自主路径规划与导航
- 基于 YOLOv8s + RealSense D435i 的目标检测与三维测距（含 MJPEG 实时视频流推送）
- OpenClaw 框架接入 DeepSeek 大模型，通过飞书实现自然语言指令控制
- Flask HTTP API 服务器与网页控制面板
- Python 测试套件（连接诊断、状态读取、运动控制、动作表演等）

## 环境依赖

- 操作系统：Ubuntu 20.04 LTS（机载）
- ROS 版本：ROS 2 Foxy（机载）+ CycloneDDS 
- Python 版本：Python 3.8（机载）/ Python 3.10+（PC 端）
- SDK 版本：unitree_ros2 v0.3.0（基于 unitree_sdk2，CycloneDDS 0.10.2）
- 其他依赖：
  - ROS 2 功能包：robot_localization、slam_toolbox、navigation2、nav2_bringup、nav2_map_server、xacro、teleop_twist_keyboard、rmw_cyclonedds_cpp、rosidl-generator-dds-idl
  - 系统库：libyaml-cpp-dev、cmake ≥ 3.16
  - Python 库：flask、flask-cors、requests、python-dotenv、ultralytics（YOLOv8）、opencv-python、cv_bridge、numpy
  - AI 框架：OpenClaw（网关 + 仪表盘 + 飞书绑定）
  - 硬件：Unitree Go2 EDU（含机载激光雷达）、Intel RealSense D435i 深度相机、有线网线

## 硬件平台

- 机器人：Unitree Go2 EDU
- 计算板：NVIDIA Jetson Orin Nano
- 深度相机：Intel RealSense D435i
- 主控板 IP：192.168.123.161
- Orin Nano IP：192.168.1.109（至2026.7.14时仍然有效，不保证后续不会变动）
- SSH 连接：`ssh unitree@192.168.1.109`（密码：123）

## 安装方法

### 1. 配置 unitree_ros2 SDK

```bash
cd ~
git clone https://github.com/unitreerobotics/unitree_ros2
cd unitree_ros2

# 安装依赖
sudo apt install ros-${ROS_DISTRO}-rmw-cyclonedds-cpp \
                 ros-${ROS_DISTRO}-rosidl-generator-dds-idl \
                 libyaml-cpp-dev

# Foxy 用户需手动编译 CycloneDDS 0.10.2（Humble 可跳过此步）
cd cyclonedds_ws/src
git clone https://github.com/ros2/rmw_cyclonedds -b foxy
git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x
cd ..
colcon build --packages-select cyclonedds

# 编译 unitree_go 和 unitree_api 消息包
source /opt/ros/${ROS_DISTRO}/setup.bash
colcon build
```

### 2. 配置网络连接

```bash
# 用网线连接 Go2，查看网卡名称
ifconfig
# 将对应网卡 IPv4 设为手动模式
#   地址：192.168.123.99
#   掩码：255.255.255.0

# 修改 setup.sh 中的网卡名称（如 eth0 / enp3s0）
sudo gedit ~/unitree_ros2/setup.sh
```

### 3. 编译 SLAM + 导航工作空间

```bash
# 加载环境（顺序不可颠倒）
conda deactivate 2>/dev/null || true
source ~/unitree_ros2/setup.sh

cd go2-nav2-amcl/src
colcon build
source install/setup.bash

# 验证
ros2 pkg list | grep go2_core
```

### 4. 编译 KISS-ICP（可选，用于激光里程计）

```bash
cd slam_ws/src/kiss-icp
pip install -e .
# 或通过 ROS 2 编译
cd slam_ws
colcon build --packages-select kiss_icp
```

### 5. 安装视觉检测依赖

```bash
pip3 install ultralytics flask opencv-python numpy
```

### 6. 安装分析工具依赖

```bash
cd unitree_ros2/analysis
pip3 install flask flask-cors requests python-dotenv
```

### 7. 配置 OpenClaw（AI 自然语言控制）

```bash
# 安装 OpenClaw 框架（参考官方文档）
# 配置 DeepSeek API Key
# 准备飞书自建应用 App ID 与 App Secret
```

## 运行方法

### ROS 2 环境加载（每次 SSH 连接后执行）

```bash
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=~/cyclonedds_ws/cyclonedds.xml
```

建议将以上命令写入 `~/.bashrc` 避免每次手动执行。

### 仿真 / 本地测试（未连接机器人）

```bash
source ~/unitree_ros2/setup_local.sh   # 使用 lo 回环接口
ros2 topic list                        # 验证环境
```

### SLAM 建图

```bash
# 终端 1：加载环境
conda deactivate 2>/dev/null || true
source ~/unitree_ros2/setup.sh
source ~/go2-nav2-amcl/src/install/setup.bash

# 启动建图
ros2 launch go2_core go2_start.launch.py

# 终端 2：键盘遥控建图
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 保存地图
mkdir -p ~/go2_maps
ros2 run nav2_map_server map_saver_cli -f ~/go2_maps/my_map
```

### Nav2 自主导航

```bash
# 默认使用包内示例地图
ros2 launch go2_navigation2 go2_nav2.launch.py

# 指定自定义地图
ros2 launch go2_navigation2 go2_nav2.launch.py map:=/home/unitree/go2_maps/707_1__map.yaml

# RViz 中操作：2D Pose Estimate 设初始位姿 → Nav2 Goal 下发目标点
```

### 视觉检测与实时视频流

```bash
# 终端 1：启动 RealSense 相机
bash ~/start_realsense.sh
# 若显示"等待图像数据"，重启相机服务：
systemctl --user restart realsense.service
sleep 5

# 启动检测节点（含 MJPEG 视频流，默认端口 8002）
python3 ~/detection/detect_object.py
# 自定义端口：
python3 ~/detection/detect_object.py --port 8003

# 检测结果输出至 /tmp/go2_detections.json
# 视频流访问：http://192.168.1.3:8002/video_stream
```

也可通过 systemd 服务管理：

```bash
systemctl --user restart detect-object.service
```

### 网页控制面板

```bash
# 启动 / 重启 HTTP 控制面板（端口 8001）
sudo fuser -k 8001/tcp
systemctl --user restart go2-http
```

网页访问地址：http://192.168.1.109:8001

若接口网页显示狗离线，执行上述重启命令即可恢复在线。

### AI 自然语言指令控制

基于 OpenClaw 框架接入 DeepSeek 大模型，通过飞书长连接实现自然语言控制机器狗。

```bash
# 终端 1：启动 OpenClaw 网关
openclaw gateway run

# 终端 2：打开仪表盘
openclaw dashboard

# 终端 3：绑定飞书
openclaw feishu bind
```

扫码授权后即可通过飞书发送自然语言指令（如"向前走两步""趴下""转一圈"）控制机器狗。

### HTTP API 服务器

```bash
cd unitree_ros2/analysis
source ../setup.sh
python3 go2_http_server.py
# 监听端口 8001，提供 REST API 控制

# 或安装为 systemd 服务
bash install_service.sh
```

### 飞书 Bot 远程控制（脚本版）

```bash
cd unitree_ros2/analysis
python3 go2_feishu_bot.py --port 8002 --api-url http://localhost:8001
# 在飞书群中添加自定义机器人，Webhook 指向 /feishu_webhook
# 群内发送 /stand /sit /walk /status 等指令控制机器狗
```

### 运行测试套件

```bash
cd unitree_ros2/analysis
source ../setup.sh

python3 tests/test_01_connection.py       # 连接诊断
python3 tests/test_02_high_state.py       # 高层状态读取
python3 tests/test_03_low_state.py        # 底层状态读取
python3 tests/test_04_basic_motion.py     # 基本运动（需 2m×2m 平地）
python3 tests/test_05_move_control.py     # 移动控制（需 3m×3m 平地）
python3 tests/test_06_actions.py          # 表演动作
python3 tests/test_07_joystick.py         # 遥控器状态
python3 tests/test_08_robot_config.py     # 系统配置
```

### 常用维护命令

```bash
# 重启 HTTP API 服务
sudo fuser -k 8001/tcp
systemctl --user restart go2-http

# 重启相机服务
systemctl --user restart realsense.service

# 重启检测服务
systemctl --user restart detect-object.service
```

## 文件结构

```
UNITREE/
├── README.md                  # 本文件
│
├── unitree_ros2/              # 宇树官方 ROS2 SDK（v0.3.0）
│   ├── cyclonedds_ws/         #   CycloneDDS 工作空间（unitree_go / unitree_api 消息包）
│   ├── example/               #   官方示例（运动控制、状态读取、低层控制等）
│   ├── analysis/              #   自研分析工具包
│   │   ├── go2_http_server.py #     HTTP API 服务器（Flask，端口 8001）
│   │   ├── go2_feishu_bot.py  #     飞书 Bot 控制通道
│   │   ├── tests/             #     Python 测试套件（8 个模块）
│   │   ├── docs/              #     API 参考文档
│   │   └── .env               #     统一配置文件
│   ├── setup.sh               #   环境加载脚本（需修改网卡名）
│   └── setup_local.sh         #   本地回环环境脚本
│
├── detection/                 # 视觉识别与三维定位模块
├── detect_object.py           #   YOLOv8s 检测 + Flask MJPEG 视频流（端口 8002）
├── README.md                  #   检测模块说明文档
│
├── go2-nav2-amcl/             # SLAM + Nav2 导航工作空间（二次开发）
│   ├── src/
│   │   ├── base/
│   │   │   ├── go2_core/      #     核心启动包（launch、config、RViz）
│   │   │   ├── go2_driver/    #     驱动节点（odom 发布、状态桥接）
│   │   │   └── go2_twist_bridge/  #  Twist 速度指令桥接
│   │   ├── go2_description/   #   机器人 URDF 模型与网格
│   │   ├── go2_navigation2/   #   Nav2 导航栈（launch、参数、示例地图）
│   │   ├── go2_perception/    #   感知模块（点云 → 激光扫描转换）
│   │   └── go2_slam/          #   SLAM 建图配置
│   └── docs/                  #   功能实现与测试记录文档
│
├── slam_ws/                   # KISS-ICP 激光里程计工作空间
│   ├── src/kiss-icp/          #   KISS-ICP 源码（LiDAR Odometry）
│   └── cmake-3.30.5-linux-aarch64.sh  # ARM64 CMake 安装脚本
│
├── go2_maps/                  # 已保存的栅格地图
│   ├── 707.pgm / 707.yaml     #   707 场地地图
│   ├── 707_1__map.*           #   707 场地地图（第二版）
│   ├── my_map.*               #   通用地图
│   ├── my_room.*              #   房间地图（导航默认）
│   ├── room.*                 #   房间地图（备份）
│   └── new_room.png           #   房间预览图
│
└── must_know/                 # 常用工具与备忘
    ├── detect_object.py       #   YOLOv8 目标检测节点（基础版，3D 测距）
    └── useful.txt             #   常用命令速查
```

> **检测脚本说明**：`detection/detect_object.py` 是增强版，内置 Flask MJPEG 视频流推送（线程化、支持 --port 参数）；`must_know/detect_object.py` 是基础版，仅输出检测结果到终端和 JSON 文件。

## 注意事项

**安全风险：**

- 机器狗运动测试前，务必确保周围有足够空间（建议 3m×3m 以上开阔区域）
- 表演/特技动作（test_06 --extreme）风险较高，需 5m×5m 空间并铺设缓冲垫
- 紧急情况使用遥控器急停或发送 /emergency 指令
- 低层电机控制（/lowcmd）直接驱动关节，参数错误可能损坏硬件，非必要不使用

**硬件限制：**

- Go2 EDU 需具备机载激光雷达才能进行 SLAM 建图
- RealSense D435i 深度相机需提前标定（camera_matrix.npy / dist_coeffs.npy）
- 标定文件路径：/home/unitree/calib_work/camera_matrix.npy 和 dist_coeffs.npy
- 模型文件路径：/home/unitree/yolov8s.engine，需提前将 YOLOv8s 转换为 TensorRT engine 格式
- 机载计算机算力有限，YOLOv8 推理使用 TensorRT 加速
- 有线连接网段为 192.168.123.x，PC 侧 IP 需手动设置为 192.168.123.99
- 黑色、透明、圆柱形物体测距误差较大，建议在有效测距范围（0.3m~3m）内使用

**已知问题：**

- 编译 unitree_ros2 消息包前必须 conda deactivate，否则 Conda 的 python3 缺少 empy 会导致编译失败
- Nav2 导航时 velocity_smoother 须设为 OPEN_LOOP 模式，否则机器人只动半步就停
- AMCL 在参照物稀少的环境下容易漂移，需手动重定位（2D Pose Estimate）或降低建图速度
- 建图时建议线速度 0.3 m/s，步态选经典模式更稳定
- 若接口网页显示狗离线，执行 `sudo fuser -k 8001/tcp && systemctl --user restart go2-http` 恢复
- 飞书 Bot Webhook 需公网可达，本地部署需配合内网穿透工具

**环境变量冲突：**

- 多个 ROS 发行版共存时，每次开终端须先 unset 旧环境变量再 source 新环境
- CycloneDDS 网卡名称必须与实际接狗网线接口一致，否则无法通信
- 环境加载顺序：先 source ROS 2 → 再 source cyclonedds_ws → 最后 source unitree_ros2
