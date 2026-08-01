# UAV — PX4 无人机子系统

## 项目简介

基于 PX4 + MAVROS + ROS2 Humble 的无人机控制子系统，由 NVIDIA Jetson Xavier NX 作为机载电脑，Pixhawk 4 飞行控制器，Intel RealSense T265 追踪相机提供视觉定位。

**核心功能**：
- T265 视觉定位 → EKF2 融合 → OFFBOARD 自动驾驶
- rosbridge WebSocket 实时遥测（Web 控制台接入）
- UavCommand 指令接口（TB4 地面机器人协调）
- 安全保护（超时返航、低电量迫降、遥控器接管检测）

## 硬件

| 组件 | 型号 |
|------|------|
| 机载电脑 | NVIDIA Jetson Xavier NX |
| 飞行控制器 | Pixhawk 4 (PX4 1.12.3) |
| 追踪相机 | Intel RealSense T265 |
| 深度相机 | Intel RealSense D435i（待连接） |
| 电池 | 6S LiPo |

## 通信架构

```
TB4 (ROS2) ↔ NX Docker (ROS2) ↔ Pixhawk (MAVLink)
                │
                ├── rosbridge :9090 → Web 浏览器
                └── web_video_server :8080 → T265 鱼眼视频
```

## 目录结构

```
drone/
├── README.md                          # 本文档
├── Dockerfile                         # Docker 镜像定义
├── start_drone.sh                     # NX 容器内全栈启动脚本
├── start_sim.sh                       # PX4 SITL 仿真一键启动（开发机用）
├── uav-arm-demo.sh                    # ARM 演示脚本（NX 上运行）
├── uav_controller/                    # 控制器节点 + launch
│   ├── uav_controller/
│   │   ├── uav_controller_node.py     # 主控制器（OFFBOARD+安全保护）
│   │   ├── battery_relay.py           # 电池数据中继（SysStatus→BatteryState）
│   │   └── vision_pose_relay.py       # T265 Pose → MAVROS vision_pose
│   ├── launch/
│   │   └── uav_controller.launch.py   # 主 launch（MAVROS + 控制器 + rosbridge + rosapi + video）
│   └── package.xml / setup.py
└── uav_controller_interfaces/         # UavCommand 消息定义
    ├── msg/UavCommand.msg
    └── package.xml / CMakeLists.txt
```

## 环境依赖

### NX 宿主机
- Ubuntu 18.04 + Docker 20.10
- NVIDIA JetPack 4.x（Jetson Xavier NX）

### Docker 容器（tb4-uav）
- arm64v8/ros:humble-ros-base
- ros-humble-mavros, ros-humble-mavros-extras
- ros-humble-rosbridge-server
- ros-humble-web-video-server
- ros-humble-rosapi
- librealsense 2.53.1（RSUSB 后端，支持 T265）
- pymavlink

### 开发机
- Ubuntu 22.04 (WSL2)
- PX4 SITL v1.15.4
- ROS2 Humble
- Node.js 20+（Web 前端）

## 构建与部署

### 1. 构建 Docker 镜像

```bash
cd drone/
docker build -f Dockerfile -t tb4-uav .
```

### 2. 容器运行

```bash
sudo chmod 666 /dev/ttyTHS0
docker run -d --name uav-run --net=host --privileged \
  --device=/dev/ttyTHS0 tb4-uav sleep infinity
```

> 注意：Dockerfile CMD 使用 `sleep infinity`，启动由 systemd 服务通过 `start_drone.sh` 触发。

### 3. systemd 开机自启

```ini
# /etc/systemd/system/uav-boot.service
[Unit]
Description=UAV Docker Container Startup
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/chmod 666 /dev/ttyTHS0
ExecStart=/usr/bin/docker start uav-run
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/bin/docker exec -d uav-run bash /root/ros2_ws/start_drone.sh

[Install]
WantedBy=multi-user.target
```

## 运行方法

### 仿真（开发机）

```bash
cd drone/
./start_sim.sh
```

启动 PX4 SITL + Gazebo + MAVROS + uav_controller。

### 实机演示（NX）

SSH 进 NX 后，执行：

```bash
uav-arm-demo
```

分步可控：确认 setpoint → 切 OFFBOARD → 确认 → ARM（电机怠速）→ 按回车 DISARM。

> **安全注意**：拆浆状态方可运行。启动脚本默认 `auto_arm=False`，开机不会自动解锁。

### Web 控制台

浏览器打开 Web 前端 → 连接 UAV → DronePage 显示实时遥测 + T265 鱼眼视频。

## 安全机制

| 保护项 | 触发条件 | 行为 |
|--------|---------|------|
| 超时返航 | 180s 未收到 UavCommand | 自动返回原点降落 |
| 低电量迫降 | 电量 < 20% | 立即降落 |
| 遥控器接管 | 切到 MANUAL/STABILIZED 等模式 | 自动 DISARM，关闭控制 |
| 位置边界 | 超过 10m 范围 | 指令修正到边界内 |
| auto_arm | 默认 false | 启动不自锁，需手动 ARM |

## 关键参数

飞控参数须持久化（QGC 可能重置）：

| 参数 | 值 | 说明 |
|------|-----|------|
| `EKF2_AID_MASK` | ≥ 6 | Vision position(2) + vision yaw(4) |
| `COM_RCL_EXCEPT` | 4 | 允许无遥控器 |
| `SER_TEL2_BAUD` | 921600 | TELEM2 波特率 |

## 已知问题

1. **T265 固件不持久**：NX 断电后 T265 回到 bootloader，start_drone.sh 自动上传
2. **MAVROS 间歇丢包**：921600 下偶尔 serial timeout，不影响基本功能
3. **QGC 参数重置**：飞控重启后不要开 QGC，可能覆盖 EKF2_AID_MASK
4. **视频编码**：Jetson NX 无硬件 JPEG 编码，单路 848×800 可跑，多路会卡

## UavCommand 接口

```yaml
# uav_controller_interfaces/msg/UavCommand.msg
string command  # "takeoff" / "goto" / "land"
float32 x       # 目标位置 X (ENU)
float32 y       # 目标位置 Y
float32 z       # 目标位置 Z
```

## 安全注意事项

> ⚠️ 实机操作必须严格遵守

1. **紧急停止**：遥控器切 MANUAL → DISARM，或 Ctrl+C 终止脚本
2. **拆浆验证**：OFFBOARD ARM 测试必须在拆浆状态下进行
3. **装浆后**：首次起飞高度 0.5m，确保 T265 EKF 收敛后再飞
4. **电池监控**：低于 20% 停止飞行，及时充电
5. **电机安全**：ARM 后电机怠速旋转，保持安全距离
