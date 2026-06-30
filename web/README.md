# Hi-Wallet — 多机器人协调系统 Web 控制台

自包含的 Go2 / TurtleBot4 / UAV 多机器人 Web 可视化与远程控制平台。基于 React + Three.js + ROS2 rosbridge，提供类 RViz 的 3D 视口、实时遥测面板、AI 对话助手与机器人运动控制。

## 系统架构

```
浏览器 (React)
    │
    │  ws://robot-ip:9090            HTTP SSE (AI Chat)
    │  roslib WebSocket              /api/ai → OpenClaw 网关 → LLM
    │
    ▼
[ROS2]  rosbridge_websocket          serve.py (静态文件 + API 代理, :3000)
    │    rosapi (话题/服务发现)
    │    robot_state_publisher (TF)
    │    unitree_bridge_node (类型桥接)
    │
    ├── publish:   /tf, /tf_static, /joint_states, /battery_state, /imu/data ...
    ├── subscribe: /cmd_vel, /api/sport/request, /initialpose ...
    └── services:  rosapi 话题发现
        │
        ▼
[Go2 / TB4 / UAV]  机器人板载
    ├── Go2:      unitree_go SDK → CycloneDDS / WebRTC
    ├── TB4:      Create3 底盘 + Nav2 + OAK-D Pro 相机
    └── UAV:      PX4 / ArduPilot
```

---

## 目录结构

```
web/Hi-Wallet/
├── .env.example                          # 环境变量模板（网关地址、token、摄像头流）
├── README.md                             # 详细快速开始指南
├── serve.py                              # 生产环境静态服务器 + API 反向代理
├── start.sh                              # 一键启动脚本（ROS2 后端 + Web 前端）
├── docs/                                 # 设计文档与变更记录
│   └── location_707                      # 707 场地坐标数据
│
└── src/
    ├── go2_description/                  # ROS2 包：Go2 URDF 机器人模型
    │   ├── CMakeLists.txt / package.xml
    │   ├── config/                       # RViz 配置
    │   ├── launch/                       # robot_state_publisher 启动
    │   ├── meshes/  dae/                 # STL / Collada 网格文件
    │   └── urdf/  xacro/                 # URDF 描述 + Xacro 宏
    │
    ├── go2_web_bridge/                   # ROS2 包：类型桥接 + rosbridge 启动
    │   ├── go2_web_bridge/
    │   │   └── unitree_bridge_node.py    # 核心桥接节点 (~500 行, unitree_go → 标准 ROS2)
    │   ├── launch/
    │   │   └── dashboard.launch.py       # 主启动文件（bridge + rosbridge + TF）
    │   └── package.xml  setup.py
    │
    └── ros_web_gui_app/                  # React + Vite + Three.js Web 前端
        ├── index.html                    # HTML 入口
        ├── package.json                  # 依赖与脚本 (React 19, Three.js, roslib)
        ├── vite.config.ts                # Vite 构建 + API 代理配置
        ├── public/                       # 静态资源 (地图 / URDF / 图标)
        └── src/
            ├── main.tsx                  # React 入口
            ├── App.tsx                   # 根组件（状态路由 + 布局编排）
            ├── styles/variables.css      # 设计令牌（CSS 自定义属性）
            ├── components/
            │   ├── ConnectionPage.tsx    # 机器人连接对话框
            │   ├── Go2ControlPanel.tsx   # Go2 遥控面板（姿态 / 速度 / D-pad）
            │   ├── TB4ControlPanel.tsx   # TB4 遥控面板
            │   ├── ai/                   # AI 聊天模块 (FAB + Dialog + Message + Settings)
            │   ├── layout/               # Shell / Sidebar / TopBar
            │   ├── layers/               # 3D 视口可视化图层 (11 个图层)
            │   ├── pages/                # DashboardPage / DronePage
            │   └── panels/               # 仪表盘面板挂件 (20+ 面板)
            ├── context/FleetContext.tsx   # 全局机队状态 (useReducer)
            ├── hooks/                    # useImageLayers / useOpenClawChat
            ├── types/                    # FleetTypes / LayerConfig / TopicInfo
            └── utils/
                ├── RosbridgeConnection.ts # 核心：WebSocket ↔ ROS rosbridge
                ├── tf2js.ts              # TF2 变换树 (Three.js 实现)
                ├── openclawApi.ts        # AI API 客户端 (SSE 流式)
                ├── MapManager.ts         # 拓扑地图 + 占据栅格单例
                ├── StaticMapLoader.ts    # PGM+YAML 静态地图加载
                └── ...                   # 持久化 / 颜色 / 导入工具
```

---

## 环境依赖

| 组件 | 版本/说明 |
|------|-----------|
| 操作系统 | Ubuntu 22.04 (机器人端) / 任意 (浏览器端) |
| ROS 2 | Humble Hawksbill |
| Python | 3.10 (系统自带) |
| Node.js | 18+ (仅用于构建前端) |
| [unitree_ros2](https://github.com/unitreerobotics/unitree_ros2) | SDK 提供 `unitree_go` 消息类型 |
| roslib | 1.4.1 (浏览器端 WebSocket 通信) |
| @lichtblick/cdr | CBOR 二进制 ROS 消息序列化 |
| Three.js | 0.181 (3D 视口渲染) |
| React | 19.2 + TypeScript 5.9 |
| Go2 机器人 | 开机并可达（CycloneDDS 或 WebRTC） |

---

## 安装与部署

### 0. 配置私有环境变量

当前仓库处于私有开发阶段，根目录 `.env` 集中保存机器人网关、摄像头地址和 OpenClaw token，随私有仓库一起提交。

> **安全提醒：** 开源前必须轮换/作废旧 token，清理 git 历史，并删除 `VITE_OPENCLAW_*_TOKEN`，避免公开构建产物暴露 token。

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
- `OPENCLAW_*_TOKEN` — 由本地代理读取并注入 `Authorization` 请求头，前端源码不内置 token。
- `VITE_OPENCLAW_*_TOKEN` — 进入浏览器端运行时，仅私有开发阶段使用。
- `VITE_*` 变量会进入浏览器端构建产物，只适合放私有开发阶段允许前端可见的配置。

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

### 3. 部署 systemd 服务（可选，生产环境）

```bash
# 将 start.sh 注册为 systemd 自启动服务
sudo cp config/dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl start dashboard
```

---

## 运行方法

**前置条件（必须全部满足，按顺序启动）：**

1. **Go2 机器人上电** — 按下电源按钮，确认机器人状态指示灯正常
2. **网络可达** — 运行 Web 服务的机器能 ping 通 Go2（或通过 CycloneDDS 发现）
3. **ROS2 环境已配置** — `/opt/ros/humble/setup.bash` 和 `~/unitree_ros2/setup.sh` 可用
4. **工作空间已构建** — `colcon build` 成功完成
5. **前端已构建** — `src/ros_web_gui_app/dist/` 目录存在（生产模式）

### 一键启动

```bash
./start.sh
```

打开 http://localhost:3000

启动流程：

```
[1/4] source /opt/ros/humble/setup.bash        # ROS2 Humble
       source ~/unitree_ros2/setup.sh           # Go2 SDK 消息类型
[2/4] source install/setup.bash                 # 本工作空间
[3/4] ros2 launch go2_web_bridge dashboard.launch.py
       → unitree_bridge_node     — 类型桥接 + TF + JointState
       → robot_state_publisher   — 完整 TF 树 (odom→base→joints)
       → rosbridge_websocket     — WebSocket 端口 9090
       → rosapi                  — 话题/服务发现
[4/4] python3 serve.py 3000 dist/              # 生产模式静态服务
```

### 手动启动（调试用）

终端 1 — ROS2 后端：

```bash
source install/setup.bash
ros2 launch go2_web_bridge dashboard.launch.py
```

终端 2 — 前端开发服务器（HMR 热更新）：

```bash
cd src/ros_web_gui_app && npm run dev
```

### 停止方式

- 一键启动模式：`Ctrl+C` 终止所有服务
- 手动模式：分别在两个终端 `Ctrl+C`

---

## 安全注意事项

> **实机操作必须严格遵守以下安全规则！**

1. **紧急停止** — Go2 遥控面板提供 Stop 按钮，按下立即发送零速指令；机器人本身也配备物理急停开关
2. **人员距离** — 机器人运动时，操作人员应与机器人保持至少 1 米安全距离
3. **速度限制** — 遥控面板提供慢/中/快三档速度预设，调试阶段建议使用低速档
4. **网络中断** — 如 WebSocket 断开，`rosbridge` 停止接收指令，机器人保持最后状态。需刷新页面重新连接
5. **电池监控** — 仪表盘面板实时显示电池电压/电流/百分比，低于 20% 应停止运动任务
6. **地面条件** — Go2 为四足机器人，需确保地面平整、无液体、无松散线缆
7. **姿态控制** — 遥控面板的姿态编辑器（roll/pitch/yaw/bodyHeight）可发送自定义姿态，输入前确认参数在合理范围
8. **运动前确认** — 发送运动指令前，确认 3D 视口中机器人模型与实际姿态一致
9. **多机器人切换** — 切换控制目标时，前一个机器人不会自动停止，需手动停止
10. **TF 异常保护** — 如 3D 视口机器人模型与实机姿态明显不符，说明 TF 变换出现异常，需检查时钟同步和 TF 树

---

## API 端点一览

### ROS 话题（WebSocket rosbridge :9090）

| 话题 | 方向 | 说明 |
|------|------|------|
| `/tf` `/tf_static` | 订阅 | TF 坐标变换（驱动 3D 视口所有图层） |
| `/joint_states` | 订阅 | 关节状态（驱动 URDF 机器人模型） |
| `/battery_state` | 订阅 | 电池状态（电压/电流/百分比） |
| `/imu/data` | 订阅 | IMU 数据（roll/pitch/yaw） |
| `/scan` | 订阅 | 激光雷达扫描 |
| `/map` | 订阅 | 占据栅格地图 |
| `/plan` `/global_plan` | 订阅 | 全局/局部路径规划 |
| `/odom` | 订阅 | 里程计数据 |
| `/cmd_vel` | 发布 | 速度控制指令 |
| `/api/sport/request` | 发布 | Go2 运动 API（姿态/步态/站立/恢复） |
| `/initialpose` | 发布 | AMCL 初始位姿 |

### AI 聊天代理（HTTP REST）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/ai/v1/chat/completions` | POST | Go2 AI 对话（SSE 流式） |
| `/api/ai/v1/models` | GET | Go2 可用模型列表 |
| `/api/ai-tb4/v1/chat/completions` | POST | TB4 AI 对话（SSE 流式） |
| `/api/ai-tb4/v1/models` | GET | TB4 可用模型列表 |

---

## 关键技术点

### 通信

- **rosbridge WebSocket** — 浏览器通过 `roslib` 连接 `ws://robot-ip:9090`，订阅/发布 ROS2 话题
- **CBOR 二进制序列化** — 使用 `@lichtblick/cdr` 进行 CBOR 二进制消息反序列化，性能优于 JSON，JSON 作为 fallback
- **自动类型适配** — `RosbridgeConnection` 自动检测 ROS1/ROS2 版本，处理 `pkg/Msg` 和 `pkg/msg/Msg` 两种格式
- **话题发现** — 通过 `rosapi` 每 15 秒轮询话题变化，带 5 秒缓存
- **ROS2 Action** — 自定义实现了 ROS2 action 协议（send_goal / status / feedback / get_result），不依赖 roslib ActionClient
- **API 代理** — Vite dev server 和 `serve.py` 均将 `/api/ai` 转发到 OpenClaw 网关，在服务端注入 Bearer token，前端代码不含敏感凭证

### 状态管理

- **FleetContext** — React `useReducer` + Context 管理全局机队状态
- **持久化** — 机器人配置写入 `localStorage`（key: `robotcore_fleet`），页面刷新后自动恢复并重连
- **多机器人支持** — 支持同时连接 Go2 / TB4 / UAV，通过 FleetContext 切换控制目标
- **TF2JS** — Per-robot TF 变换树，Three.js 实现，支持多机器人独立坐标系

### 3D 视口

- **Three.js + URDF Loader** — 加载 Go2/TB4 机器人 3D 模型，60fps 渲染循环
- **OrbitControls** — 鼠标旋转/缩放/平移，支持机器人跟随模式
- **11 个可视化图层** — Grid / StaticMap / OccupancyGrid / LaserScan / PointCloud / Path / Footprint / Robot / TF / Image / Topo
- **TF 驱动** — 所有图层位置由 `/tf` 话题实时更新，`position` / `quaternion` 每帧刷新
- **固定帧切换** — 支持 odom/map 固定帧切换，含 map→odom 校准偏移
- **静态地图** — 支持 PGM+YAML 格式，ZIP 导入

### AI 聊天

- **SSE 流式响应** — 基于 OpenAI 兼容 API，支持 `reasoning_content`（DeepSeek-R1 / Claude thinking）
- **多预设** — Go2 / TB4 预设切换，独立对话历史
- **Markdown 渲染** — 思维链、代码高亮、复制/重试/重新生成
- **快捷键** — Enter 发送 / Shift+Enter 换行 / Ctrl+N 新建 / Ctrl+W 关闭 / Esc 退出

### Go2 运动控制

- **站立/趴下/恢复/急停** — Unitree Go2 sport API，通过 `/api/sport/request` 话题发送
- **D-pad 方向控制** — 点击方向按钮发送定时速度指令
- **速度预设** — 慢/中/快三档，支持滑块微调
- **姿态模板编辑器** — roll/pitch/yaw/bodyHeight 自定义参数，支持预设模板

---

## 故障排查

| 现象 | 排查 |
|------|------|
| `localhost:3000` 无法访问 | 检查 `start.sh` 是否正常运行，或 `npm run dev` 是否启动 |
| `localhost:9090` WebSocket 拒绝连接 | `ros2 launch go2_web_bridge dashboard.launch.py` 是否运行 |
| 3D 视口空白/无机器人模型 | 检查 `/tf` 和 `/joint_states` 话题是否有数据：`ros2 topic echo /tf` |
| 机器人模型不随实机运动 | TF 变换异常，检查 `robot_state_publisher` 是否运行 |
| AI 聊天无响应 | 检查 OpenClaw 网关是否可达，`.env` 中 token 是否正确 |
| 摄像头无图像 | 检查 `VITE_GO2_CAMERA_URL` / `VITE_TB4_CAMERA_URL` 配置，确认相机流可用 |
| 连接机器人失败（offline） | 确认 IP/端口正确，机器人上电，rosbridge 运行中 |
| 话题列表为空 | 检查 ROS2 环境是否正常：`ros2 topic list` |
| Go2 遥控无反应 | 检查 `/api/sport/request` 话题是否有订阅者 |
| `npm run build` 失败 | 检查 Node.js >= 18，`npm install` 是否成功 |
| CBOR 序列化报错 | 消息类型不在注册表中，自动 fallback 到 JSON |

---

## 已知问题

1. **首次连接等待** — 首次连接机器人需要加载 CBOR 消息定义，WebSocket 握手 + 话题发现可能需要 5-10 秒
2. **多机器人 TF 冲突** — 当前 TF2JS 为每个机器人独立维护变换树，但同一页面连接多台同型号机器人时坐标系可能混淆
3. **URDF mesh 路径** — URDF 中引用的 mesh 文件路径为 ROS2 标准路径，Web 端需在 `public/` 目录维护副本
4. **CBOR fallback** — 部分自定义 ROS2 消息类型未在 CBOR 注册表中，会自动降级为 JSON 序列化
5. **WiFi 波动** — 网络不稳定时 WebSocket 可能断开，需手动刷新页面重连
6. **浏览器兼容** — 推荐 Chrome/Edge，Safari 部分 WebGL 特性兼容性较差
7. **大规模点云** — PointCloud2 大量数据点可能导致浏览器渲染帧率下降
8. **Go2 sport API 权限** — 部分高级运动控制需要 Go2 运动权限，标准用户可能无法使用
