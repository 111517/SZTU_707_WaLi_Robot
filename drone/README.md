# UAV — PX4 无人机子系统

## 项目简介

PX4 + MAVROS + ROS2 Humble 无人机控制子系统。NVIDIA Jetson Xavier NX 机载电脑 + Pixhawk 4 飞控 + Intel RealSense T265 视觉定位，支持 OFFBOARD 自动驾驶和 Web 实时监控。

## 硬件清单

| 组件 | 型号 | 连接方式 |
|------|------|---------|
| 机载电脑 | NVIDIA Jetson Xavier NX | — |
| 飞行控制器 | Pixhawk 4 (PX4 1.12.3) | TELEM2 → NX `/dev/ttyTHS0` (921600 baud) |
| 追踪相机 | Intel RealSense T265 | USB 直连 NX |
| 电池 | 6S LiPo | 同时供电 NX 和飞控 |

## 系统架构

```
地面电脑 (浏览器)                  NX 机载电脑 (Docker)
    │                                   │
    ├─ ws://nx-ip:9090 ────────────── rosbridge (WebSocket)
    ├─ http://nx-ip:8080 ──────────── web_video_server (MJPEG)
    │                                   │
    │                          ┌────────┴────────┐
    │                          │  uav_controller │ ← /ugv/uav_command
    │                          │  vision_pose    │ ← T265 → MAVROS
    │                          │  battery_relay  │ ← SysStatus
    │                          └────────┬────────┘
    │                                   │
    │                           MAVROS (ROS2↔MAVLink)
    │                                   │
    │                            Pixhawk 4 (PX4)
```

## 前置条件

开始之前请确认：

- [ ] NX 能 SSH 登录 (`ssh nvidia@<nx-ip>`, 密码 `nvidia`)
- [ ] 飞控 TELEM2 通过 UART 连接 NX (`/dev/ttyTHS0`)
- [ ] T265 USB 插入 NX
- [ ] 飞控已校准加速度计（QGC 完成）
- [ ] 飞控已设置机型（QGC 完成）
- [ ] NX 和 Web 访问设备在同一 WiFi

---

## 部署步骤（从头开始）

### 第一步：NX 宿主机准备

```bash
# SSH 进 NX
ssh nvidia@<nx-ip>

# 确认串口存在
ls /dev/ttyTHS0

# 安装 Docker（如未安装）
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker nvidia
```

### 第二步：构建 Docker 镜像

```bash
# 将 drone/ 目录拷贝到 NX
scp -r drone/ nvidia@<nx-ip>:~/drone/

# 在 NX 上构建（约 20 分钟，首次需要下载基础镜像）
cd ~/drone
docker build -f Dockerfile -t tb4-uav .
```

构建产物：`tb4-uav:latest` (~1GB，含 ROS2 Humble + MAVROS + 控制器)

### 第三步：编译 realsense2_camera（T265 驱动）

> Intel 在 2022 年停产 T265，librealsense ≥ 2.54 移除了 T265 支持。需要用 RSUSB 后端编译 2.53.1。

```bash
# 在 NX 上（非容器），下载 librealsense 2.53.1 源码
cd /tmp
wget https://github.com/IntelRealSense/librealsense/archive/refs/tags/v2.53.1.tar.gz
tar xzf v2.53.1.tar.gz

# 将源码拷入容器编译
docker cp librealsense-2.53.1 uav-run:/tmp/
docker exec uav-run bash -c "
  cd /tmp/librealsense-2.53.1 && mkdir build && cd build && \
  cmake .. -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF \
           -DBUILD_GRAPHICAL_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release && \
  make -j\$(nproc) && make install
"

# 编译 realsense2_camera ROS2 节点
docker exec uav-run bash -c "
  source /opt/ros/humble/setup.bash && \
  cd /root/ros2_ws && \
  git clone https://github.com/IntelRealSense/realsense-ros.git src/realsense-ros && \
  cd src/realsense-ros && git checkout 4.51.1 && \
  cd /root/ros2_ws && colcon build --packages-select realsense2_camera_msgs realsense2_camera
"
```

### 第四步：配置飞控参数

连接飞控后，通过 MAVROS 写入持久化参数：

```bash
docker exec uav-run bash -c "
  source /opt/ros/humble/setup.bash
  ros2 run mavros mavparam set EKF2_AID_MASK 6    # Vision position + yaw
  ros2 run mavros mavparam set COM_RCL_EXCEPT 4    # 允许无遥控器
  ros2 run mavros mavparam set SER_TEL2_BAUD 921600
"
```

> ⚠️ 飞控重启后**不要开 QGC**，QGC 可能重置这些参数。

### 第五步：设置开机自启

```bash
sudo cp drone/uav-boot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable uav-boot
```

`uav-boot.service` 内容：

```ini
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

### 第六步：创建并启动容器

```bash
# 首次创建（只需执行一次）
sudo chmod 666 /dev/ttyTHS0
docker run -d --name uav-run --net=host --privileged \
  --device=/dev/ttyTHS0 tb4-uav sleep infinity

# 拷贝启动脚本
docker cp drone/start_drone.sh uav-run:/root/ros2_ws/start_drone.sh
docker exec uav-run chmod +x /root/ros2_ws/start_drone.sh

# 手动启动（或重启 NX 由 systemd 自动启动）
docker exec -d uav-run bash /root/ros2_ws/start_drone.sh
```

---

## 验证检查清单

启动后，逐条确认：

```bash
# 进容器
docker exec -it uav-run bash
source /opt/ros/humble/setup.bash

# 1. MAVROS 连接
ros2 topic echo /mavros/state --once | grep connected
# 期望: connected: true

# 2. EKF 收敛（需要 T265 SLAM 初始化，手持无人机走动几步）
ros2 topic echo /mavros/local_position/pose --once | grep "z:"
# 期望: 有数值，不是全 0

# 3. T265 Pose
ros2 topic hz /camera/pose/sample
# 期望: ~200 Hz

# 4. rosbridge 端口
curl -s http://localhost:9090
# 期望: 返回 HTML（rosbridge HTTP fallback）

# 5. 视频流
curl -s http://localhost:8080
# 期望: 返回 HTML（web_video_server 首页）
```

---

## 运行方法

### 仿真（开发机，不需要 NX）

```bash
cd drone/
./start_sim.sh
```

启动 PX4 SITL + Gazebo + MAVROS + uav_controller。

### 实机 ARM 演示（NX 上）

SSH 进 NX：

```bash
uav-arm-demo
```

分步可控：确认 setpoint → 切 OFFBOARD → **人工确认** → ARM（电机怠速）→ **按回车** DISARM。

> 默认 `auto_arm=False`，开机不会自动解锁。拆浆状态方可运行。

### Web 控制台（地面电脑）

1. 启动 Web 前端（开发模式）：
```bash
cd web/Hi-Wallet/src/ros_web_gui_app
npm install
npm run dev
```

2. 浏览器打开 `http://localhost:3000`
3. 连接机器人：IP `nx-ip`，端口 `9090`，类型 `uav`
4. 切换到 Drone 页面查看遥测 + 视频

---

## 目录结构

```
drone/
├── README.md
├── Dockerfile                         # Docker 镜像定义
├── start_drone.sh                     # NX 容器内全栈启动（v4）
├── start_sim.sh                       # PX4 SITL 仿真一键启动
├── uav-arm-demo.sh                    # ARM 演示脚本
├── uav_controller/
│   ├── uav_controller/
│   │   ├── uav_controller_node.py     # 主控制器（OFFBOARD + 安全保护）
│   │   ├── battery_relay.py           # SysStatus → BatteryState
│   │   └── vision_pose_relay.py       # T265 Pose → MAVROS vision_pose
│   ├── launch/
│   │   └── uav_controller.launch.py   # 主 launch（全栈 7 节点）
│   └── package.xml / setup.py
└── uav_controller_interfaces/
    ├── msg/UavCommand.msg
    └── package.xml / CMakeLists.txt
```

## launch 文件启动的节点

| 节点 | 包 | 作用 |
|------|-----|------|
| mavros_node | mavros | MAVLink ↔ ROS2 桥接 |
| uav_controller_node | uav_controller | OFFBOARD 控制 + 安全保护 |
| vision_pose_relay | uav_controller | T265 → MAVROS 视觉位姿 |
| battery_relay | uav_controller | SysStatus → BatteryState |
| rosapi_node | rosapi | 话题/服务发现（Web 端需要） |
| rosbridge_websocket | rosbridge_server | WebSocket (:9090) |
| web_video_server | web_video_server | MJPEG 视频流 (:8080) |

## 安全机制

| 保护项 | 触发条件 | 行为 |
|--------|---------|------|
| 超时返航 | 180s 未收到 UavCommand | 自动返回原点降落 |
| 低电量迫降 | 电量 < 20% | 立即降落 |
| 遥控器接管 | 切到 MANUAL/STABILIZED | 自动 DISARM |
| 位置边界 | 超过 10m 范围 | 指令修正 |
| auto_arm | 默认 false | 启动不解锁，需手动 ARM |

## UavCommand 接口

```yaml
string command  # "takeoff" / "goto" / "land"
float32 x       # ENU X (m)
float32 y       # ENU Y (m)
float32 z       # ENU Z (m)
```

---

## 已知问题

| 问题 | 影响 | 缓解措施 |
|------|------|---------|
| T265 固件不持久 | NX 断电后 T265 回到 bootloader | start_drone.sh 自动上传 |
| MAVROS 间歇丢包 | 921600 下偶尔 serial timeout | 不影响基本功能 |
| QGC 参数重置 | QGC 可能覆盖 EKF2_AID_MASK | 重启后避免连接 QGC |
| 视频软编码 | Jetson NX 无硬件 JPEG 编码器 | 单路 848×800 可跑，多路会卡 |
| vision_pose_relay CPU | Python 200Hz 转发占 ~50% 单核 | 可优化为 C++ / 降频 |

## 安全须知

> ⚠️ 实机操作前必须阅读

1. **拆浆验证**：首次 OFFBOARD ARM 必须在拆浆状态下进行
2. **装浆后**：首次起飞 ≤ 0.5m，确认 T265 EKF 收敛
3. **紧急停止**：遥控器切 MANUAL → DISARM，或 `Ctrl+C` 终止脚本
4. **电池**：低于 20% 立即降落，6S 满电 ~25.2V
5. **电机**：ARM 后怠速旋转，保持 1m 以上安全距离
