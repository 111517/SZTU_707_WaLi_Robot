# Unitree Go2 Python SDK 分析 & 测试工具包

> 基于 Unitree ROS2 SDK v0.3.0  
> 生成日期：2026-05-10

## 目录结构

```
analysis/
├── .env                    # 统一配置文件
├── docs/
│   ├── overview.md         # 架构分析：ROS2 + DDS 通信机制
│   ├── API.md              # 完整 API 接口参考（全部机器人）
│   └── API_for_Go2.md      # Go2 专属 API 快速参考
├── tests/
│   ├── test_01_connection.py      # 连接诊断
│   ├── test_02_high_state.py      # 高层运动状态读取
│   ├── test_03_low_state.py       # 底层状态读取
│   ├── test_04_basic_motion.py    # 基本运动控制
│   ├── test_05_move_control.py    # 移动控制
│   ├── test_06_actions.py         # 表演/特技动作
│   ├── test_07_joystick.py        # 遥控器状态
│   └── test_08_robot_config.py    # 系统配置管理
└── logs/                   # 测试日志（运行时生成）
```

## 快速开始

### 1. 配置环境

```bash
cd /home/unitree/unitree_ros2/analysis

# 连接 Go2 机器人
source ../setup.sh

# 或本地仿真
source ../setup_local.sh
```

### 2. 验证连接

```bash
python3 tests/test_01_connection.py
```

### 3. 运行测试

**按顺序执行**：

```bash
# 安全：仅读取状态
python3 tests/test_02_high_state.py       # 查看高层状态
python3 tests/test_03_low_state.py        # 查看底层状态
python3 tests/test_07_joystick.py         # 查看遥控器

# 需注意安全：有机器人动作
python3 tests/test_04_basic_motion.py     # 基本动作（起立/趴下）
python3 tests/test_05_move_control.py     # 移动控制（前进/转向）

# 可选
python3 tests/test_06_actions.py          # 表演动作（Hello/Dance）
python3 tests/test_06_actions.py --extreme # 含特技（需确认！）
python3 tests/test_08_robot_config.py     # 系统配置菜单
python3 tests/test_08_robot_config.py --humble  # Humble 扩展
```

## 安全准则

| 测试 | 风险 | 前提条件 |
|------|------|----------|
| test_01 ~ 03 | ✅ 无 | 仅数据订阅 |
| test_07 | ✅ 无 | 仅数据订阅 |
| test_04 | ⚠️ 低 | 2m×2m 平地 |
| test_05 | ⚠️ 低 | 3m×3m 平地 |
| test_06 | ⚠️ 中 | 3m×3m 平地 |
| test_06 --extreme | 🔴 高 | 5m×5m + 缓冲垫 |
| test_08 | ✅ 无 | 仅配置查询 |

## 配置文件

编辑 `.env` 修改默认参数：

```bash
NETWORK_INTERFACE=eth0     # 网卡名称
DEFAULT_VX=0.3             # 默认前进速度
DEFAULT_VYAW=0.5           # 默认旋转速度
TEST_DURATION=10           # 默认测试时长
```

## 依赖

```bash
pip3 install python-dotenv  # 可选，用于加载 .env 配置
```

## 架构概述

```
应用 (Python/rclpy)
    │
    ├── 发布 Request → /api/sport/request  ──→ 运动控制
    ├── 发布 LowCmd  → /lowcmd              ──→ 底层电机
    │
    ├── 订阅 SportModeState ← /sportmodestate ── 高层状态
    ├── 订阅 LowState       ← /lowstate       ── 底层状态
    ├── 订阅 WirelessController ← /wirelesscontroller ── 遥控器
    │
    └── 传输层: CycloneDDS (rmw_cyclonedds_cpp)
```