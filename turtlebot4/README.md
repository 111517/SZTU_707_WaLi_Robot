# TurtleBot4 Auto Control

ROS 2 + FastAPI 桥接系统，让 OpenClaw AI 智能体通过 HTTP REST API 控制 TurtleBot 4 机器人。

## 系统架构

```
OpenClaw (AI Agent)
    │
    │  HTTP REST API (FastAPI :8001)
    │
    ▼
[Jetson]  openclaw_nav2_bridge.py
    │       ROS 2 node: /openclaw_tb4_controller
    │       DDS over WiFi → Pi Discovery Server (192.168.1.5:11811)
    │
    │  publish:  /cmd_vel, /initialpose, /tf
    │  subscribe: /odom, /battery_state, /dock_status, /oakd/rgb/...
    │  actions:  /navigate_to_pose, /dock, /undock
    │  services: /slam_toolbox/save_map
    │
    ▼
[Raspberry Pi]  TurtleBot 4 板载
    ├── turtlebot4.service         Create3 底盘驱动 / 传感器 / robot_state_publisher
    ├── turtlebot4-nav2.service    Nav2 导航 + AMCL 定位 + 地图服务
    └── OAK-D Pro camera           YOLOv8n 推理 + 双目深度 (Myriad X VPU)
```

---

## 目录结构

```
turtlebot4/
├── README.md
├── src/
│   └── openclaw_nav2_bridge.py   核心桥接程序 (~1500 行)
├── skill/
│   └── SKILL.md                   OpenClaw 技能定义：任务流水线 + API 规范
├── scripts/
│   ├── start_bridge.sh            启动脚本 (等待 Pi 就绪 → 启动 bridge)
│   └── stop_bridge.sh             停止脚本
├── config/
│   ├── tb4-bridge.service         systemd 自启动 (Jetson 端)
│   └── location_707.json          命名航点 (5 个预设位置)
└── pi_side/                       Pi 端部署参考文件
    ├── nav2_bringup.sh            导航栈启动脚本
    ├── turtlebot4-nav2.service    systemd 自启动 (Pi 端)
    ├── nav2.yaml                  Nav2 参数 (含调优)
    └── chrony.conf                时钟同步配置 (Pi 作为 LAN NTP 服务器)
```

---

## 环境依赖

| 组件 | 版本/说明 |
|------|-----------|
| 操作系统 | Ubuntu 22.04 (Jetson 和 Pi 均为 22.04) |
| ROS 2 | Humble Hawksbill |
| Python | 3.10 (系统自带) |
| FastAPI + uvicorn | 最新稳定版 (`pip install fastapi uvicorn`) |
| Nav2 | Humble 发行版自带 |
| SLAM Toolbox | Humble 发行版自带 |
| depthai-ros-driver | Humble 发行版 (OAK-D 相机驱动) |
| Create3 固件 | H.2.6 |
| 网络 | Jetson ↔ Pi WiFi (192.168.1.x), Pi ↔ Create3 USB Ethernet (192.168.186.x) |

---

## 安装与部署

### Jetson 端安装

```bash
# 确保 ROS_SUPER_CLIENT 已设置 (接收 Pi 端完整拓扑)
echo 'export ROS_SUPER_CLIENT=True' >> ~/.bashrc
source ~/.bashrc

# 复制项目到 Jetson
git clone <repo-url> /home/jetson/turtlebot4_auto_control

# 安装 Python 依赖
pip install fastapi uvicorn

# 安装 systemd 服务
sudo cp config/tb4-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tb4-bridge
sudo systemctl start tb4-bridge

# 验证
curl -s http://localhost:8001/
```

### Pi 端部署

```bash
# 备份原 Nav2 配置
ssh ubuntu@192.168.1.5 "sudo cp /opt/ros/humble/share/turtlebot4_navigation/config/nav2.yaml{,.bak}"

# 复制配置文件 (scp 到 /tmp 再 sudo cp，因为目标目录属 root)
scp pi_side/nav2.yaml ubuntu@192.168.1.5:/tmp/
scp pi_side/turtlebot4-nav2.service ubuntu@192.168.1.5:/tmp/
scp pi_side/nav2_bringup.sh ubuntu@192.168.1.5:/tmp/

# Pi 上安装
ssh ubuntu@192.168.1.5
sudo mv /tmp/nav2.yaml /opt/ros/humble/share/turtlebot4_navigation/config/
sudo mv /tmp/turtlebot4-nav2.service /etc/systemd/system/
sudo mv /tmp/nav2_bringup.sh /home/ubuntu/tb4_nav2/
sudo systemctl daemon-reload
sudo systemctl enable turtlebot4-nav2
```

### 时钟同步

时间链：`Jetson (systemd-timesyncd) → Pi (chrony) → ntp.ubuntu.com`

```bash
# Pi: /etc/chrony/chrony.conf 添加
allow 192.168.1.0/24

# Jetson: /etc/systemd/timesyncd.conf
NTP=192.168.1.5
FallbackNTP=ntp.ubuntu.com
```

详见 `pi_side/chrony.conf`。配置完成后 Jetson 与 Pi 时钟差 < 0.3s，避免 TF "extrapolation into the future" 错误。

### OpenClaw 技能安装

```bash
mkdir -p ~/.openclaw/workspace/skills/turtlebot4-bridge
cp skill/SKILL.md ~/.openclaw/workspace/skills/turtlebot4-bridge/
```

---

## 运行方法

### 仿真环境

本项目目前仅支持实机运行，无 Gazebo/Ignition 仿真配置。如需仿真测试，可使用 TurtleBot 4 官方仿真环境测试 Nav2 基础功能，但 Bridge API 需在实机上使用。

### 实机运行

**前置条件（必须全部满足，按顺序启动）：**

1. **TurtleBot 4 底盘上电** — 按下电源按钮，确认 Create3 指示灯正常
2. **Pi 端导航栈已启动** — SSH 到 Pi 确认 `turtlebot4-nav2.service` 状态正常
3. **Jetson 桥接服务已启动** — `sudo systemctl start tb4-bridge`
4. **WiFi 网络正常** — Jetson 能 ping 通 Pi (192.168.1.5)
5. **时钟同步正常** — Jetson 与 Pi 时钟差 < 0.3s

**启动步骤：**

```bash
# 1. Jetson 端启动桥接 (如未设为自启动)
./scripts/start_bridge.sh

# 2. 验证服务在线
curl -s http://localhost:8001/

# 3. 初始化定位 (必须先做，否则导航失败)
curl -s -X POST http://localhost:8001/localization/initialize \
  -H "Content-Type: application/json" \
  -d '{"x": -3.24, "y": 3.10, "theta": 1.558}'

# 4. 测试导航
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": 0.20, "y": 3.80, "theta": 0.0, "wait": true}'
```

**停止方式：**

```bash
# 紧急停止 (保留机器人当前位置，取消所有导航)
curl -s -X POST http://localhost:8001/control/stop

# 停止 Bridge 服务
sudo systemctl stop tb4-bridge

# 或使用脚本
./scripts/stop_bridge.sh
```

**进程管理：**

```bash
sudo systemctl start tb4-bridge      # 启动
sudo systemctl stop tb4-bridge       # 停止
sudo systemctl restart tb4-bridge    # 重启
sudo systemctl status tb4-bridge     # 查看状态
journalctl -u tb4-bridge -f          # 查看日志
```

---

## 安全注意事项

> **实机操作必须严格遵守以下安全规则！**

1. **紧急停止** — 如机器人异常运动，立即调用 `/control/stop` 或按下 Create3 底盘实体急停按钮
2. **人员距离** — 机器人自主导航时，操作人员应与机器人保持至少 1 米安全距离
3. **回充安全** — 自动回充 (`/navigation/dock`) 依赖红外对接，充电桩前方 2 米内不得有障碍物
4. **网络中断** — 如 WiFi 断开，机器人会停在原地（Nav2 无指令时速度归零），但需手动恢复连接后重新定位
5. **电池监控** — 导航任务前检查电池电量 (`/status/battery`)，低于 20% 应先回充
6. **地面条件** — 确保地面平整、无液体、无松散线缆，SLAM 依赖稳定的激光扫描特征
7. **地图一致性** — 导航依赖已保存的地图与当前环境一致，如环境布局有较大变化需重新建图
8. **TF 异常保护** — 如 `transform_tolerance` 放宽到 1.0s 仍频繁触发 abort，说明时钟同步已严重偏离，需排查 chrony/timesyncd
9. **安全覆盖** — Pi 端启动时会执行 `ros2 param set /_do_not_use/motion_control safety_override full`，允许底盘全速后退，仅在受控环境中使用
10. **Super Client 风险** — `ROS_SUPER_CLIENT=True` 会使 Jetson 上的 ROS 节点认为自己是整个 ROS 图的一部分；如果 Jetson 与 Pi 时钟不同步，TF 变换会出错导致定位跳变

---

## API 端点一览

### 导航

| 端点 | 方法 | 说明 |
|------|------|------|
| `/navigation/goto` | POST | Nav2 导航到目标 `{x, y, theta, wait?}` |
| `/navigation/cancel` | POST | 取消当前导航 |
| `/navigation/dock` | POST | 返回充电桩 (导航 + 红外对接) |
| `/navigation/undock` | POST | 离开充电桩 |

### 控制

| 端点 | 方法 | 说明 |
|------|------|------|
| `/control/move` | POST | 定时速度指令 `{linear_x, angular_z, duration}` |
| `/control/stop` | POST | 紧急停止 |
| `/control/continuous_move` | POST | 持续速度 (无自动停止，谨慎使用) |
| `/openclaw/move` | POST | 简化方向控制 `{direction: "forward/backward/left/right/stop"}` |

### 相机

| 端点 | 方法 | 说明 |
|------|------|------|
| `/camera/capture` | GET | 拍照, 返回 base64 JPEG + 文件路径 |
| `/camera/detect` | GET | YOLO 检测指定类别 `?object=人&timeout_sec=20` |
| `/camera/detect-and-center` | GET | 检测 + 自动居中目标 + 拍照 |

### 定位与建图

| 端点 | 方法 | 说明 |
|------|------|------|
| `/localization/initialize` | POST | 发布 AMCL 初始位姿 |
| `/mapping/save` | POST | 保存 SLAM 地图 |

### 状态

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 健康检查 + 机器人状态 |
| `/status/robot` | GET | 详细状态 (位姿/电量/导航) |
| `/status/battery` | GET | 电量百分比 |
| `/status/pose` | GET | 当前坐标 (x, y, z) |
| `/openclaw/functions` | GET | 返回 OpenClaw 函数定义 |

### 导航示例

```bash
# 异步 (立即返回)
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": 1.0, "y": 0.5, "theta": 0.0}'

# 同步 (等待到达)
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": 1.0, "y": 0.5, "theta": 0.0, "wait": true}'
```

---

## 关键技术点

### 通信

- **DDS Discovery Server** — Pi (`192.168.1.5:11811`) 作为发现服务器，解决 WiFi 跨主机发现
- **`ROS_SUPER_CLIENT=True`** — Jetson 需设此环境变量以接收 Pi 端完整拓扑
- **CORS 全开放** — FastAPI 允许任意来源访问
- **按需订阅** — OAK-D 全分辨率流仅在拍照时临时订阅，用完销毁，节省 WiFi 带宽

### 导航

- **Nav2 Action 客户端** — 通过 `NavigateToPose` 发送目标，支持异步/阻塞两种模式
- **TF 桥接** — 从 `/odom` 手动广播 `odom → base_link` (TRANSIENT_LOCAL QoS)，供 AMCL 使用
- **AMCL 初始位姿** — 连续发布 5 次 `/initialpose` 粒子云, 然后等待 15s 收敛

### Nav2 参数调优 (Pi `nav2.yaml`)

| 参数 | 默认 | 调后 | 原因 |
|------|------|------|------|
| `use_sim_time` | True | False | 真机无 `/clock`，导致 TF 异常 |
| `controller_patience` | 无 | 10.0s | 短暂定位抖动不触发 abort |
| `transform_tolerance` (controller) | 0.2 | 1.0 | TF 时差 > 0.2s 即丢弃, 太严 |
| `transform_tolerance` (behavior) | 0.1 | 1.0 | 恢复行为不因 TF 失败 |

### 自主回充

- **两阶段对接** — 阶段 1: Nav2 导航到充电桩前方 0.8m；阶段 2: Create3 红外精确对接
- **自动脱桩** — 导航前检测 `dock_status`，在桩则先脱 (带线程锁防并发)

### 视觉与检测

- **OAK-D Pro** — 连接 Pi (USB)，内置 Myriad X VPU
- **YOLOv8n** — 416×416 输入，COCO 80 类，推理在 VPU 上，不占 CPU/GPU
- **中英文类别映射** — `"人" → "person"`, `"椅子" → "chair"` 等
- **目标居中** — `detect-and-center` 两阶段：旋转扫描 → 角速度迭代居中，含振荡检测

### 预设航点

`config/location_707.json` 中定义 5 个位置：

| 名称 | 坐标 (x, y, θ) |
|------|-----------------|
| 初始点 | (-3.24, 3.10, 89.3°) |
| 前门门口 | (0.20, 3.80, 0°) |
| 后门 | (0.00, -3.49, 0°) |
| 冰箱 | (-2.71, -2.96, 0°) |
| 黑板/屏幕 | (-0.50, -0.50, 0°) |

---

## 故障排查

| 现象 | 排查 |
|------|------|
| `localhost:8001` 拒绝连接 | `sudo systemctl start tb4-bridge` |
| `ros2 topic list` 看不到 Pi 节点 | 检查 `echo $ROS_SUPER_CLIENT` 是否为 True |
| 导航频繁 abort | 检查 Pi 时钟同步: `date +%s.%N` 对比 Jetson |
| 相机无数据 | QoS mismatch — OAK-D 用 `best_effort`，需匹配 |
| `/cmd_vel` 无订阅者 | 检查底盘上电 + `ros2 node list \| grep motion` |

## 已知问题

1. **AMCL 初始化需等待 15s** — 连续发布初始位姿后 AMCL 需要时间收敛粒子云，期间导航可能返回失败
2. **WiFi 波动导致 TF 丢弃** — 即使 `transform_tolerance` 放宽到 1.0s，WiFi 丢包严重时仍可能触发 TF 错误
3. **OAK-D QoS 不匹配** — 默认 `best_effort`，Bridge 需显式匹配，否则收不到图像数据
4. **回充需要充电桩已配对** — Create3 必须已在充电桩上配对过（红外通信），首次使用需手动配对
