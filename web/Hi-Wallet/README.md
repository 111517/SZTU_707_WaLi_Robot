# Go2 Web Dashboard

自包含的 Go2 机器人 Web 可视化后端。

## 依赖

- ROS 2 Humble
- [unitree_ros2](https://github.com/unitreerobotics/unitree_ros2) SDK（提供 `unitree_go` 消息类型）
- Node.js 18+（用于构建前端）
- Go2 机器人开机并可达（通过 CycloneDDS 或 WebRTC）

## 快速开始

### 0. 配置私有环境变量

当前仓库处于私有开发阶段，根目录 `.env` 会集中保存机器人网关、摄像头地址和 OpenClaw token，并随私有仓库一起提交，便于团队成员拉取后直接联调。这只是私有阶段的临时方案，不适合作为开源仓库的长期做法。

如果本地没有 `.env`，先从示例文件复制：

```bash
cp .env.example .env
```

根据现场网络修改 `.env`：

```env
OPENCLAW_GO2_URL=http://<go2-ip>:18789
OPENCLAW_TB4_URL=http://<tb4-ip>:18789
OPENCLAW_GO2_TOKEN=<go2-token>
OPENCLAW_TB4_TOKEN=<tb4-token>
VITE_OPENCLAW_GO2_TOKEN=<go2-token>
VITE_OPENCLAW_TB4_TOKEN=<tb4-token>
VITE_TB4_CAMERA_URL=http://<camera-ip>:7654/stream?topic=/oakd/rgb/image_raw&type=mjpeg
VITE_GO2_CAMERA_URL=http://<go2-ip>:7654/stream?topic=/camera/color/image_raw&type=mjpeg
```

说明：

- `OPENCLAW_*_TOKEN` 只由本地代理读取并注入 `Authorization`，前端源码不再内置 token。
- `VITE_OPENCLAW_*_TOKEN` 会进入浏览器端运行时，用于私有开发阶段在 Web 设置页显示 token；任何能打开页面的人都能看到这些值。
- `VITE_*` 变量会进入浏览器端构建产物，只适合放私有开发阶段允许前端可见的配置。
- 开源前不能只删除 `.env`。如果真实 token 曾经进入 git 历史，需要轮换/作废旧 token，并清理 git 历史或重新初始化公开仓库；同时必须删除 `VITE_OPENCLAW_*_TOKEN`，避免公开构建产物暴露 token。

### 1. 编译 ROS 包

```bash
source /opt/ros/humble/setup.bash
source ~/unitree_ros2/setup.sh
colcon build --packages-select go2_description go2_web_bridge
```

### 2. 构建前端

```bash
cd src/ros_web_gui_app
npm install
npm run build
cd ../..
```

### 3. 一键启动

```bash
./start.sh
```

打开 http://localhost:3000

## 手动启动（调试用）

```bash
source install/setup.bash
ros2 launch go2_web_bridge dashboard.launch.py
```

然后在另一个终端：
```bash
cd src/ros_web_gui_app && npm run dev
```

## 包说明

| 包 | 作用 |
|---|---|
| `go2_web_bridge` | 桥接 unitree_go → 标准 ROS2 类型 + master launch |
| `go2_description` | Go2 URDF 模型 (root=base) + 3D mesh 文件 |
| `ros_web_gui_app` | Vite + React + Three.js Web 前端 |

## 启动的服务

- `unitree_bridge_node` — 类型桥接 + TF + JointState
- `robot_state_publisher` — 完整 TF 树（odom→base→joints）
- `rosbridge_websocket` — WebSocket 端口 9090
- `rosapi` — 话题/服务发现
- HTTP server — 端口 3000 托管前端
