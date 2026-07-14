# Unitree ROS2 SDK 架构分析

> 分析日期：2026-05-10  
> SDK 版本：v0.3.0  
> 项目路径：`/home/unitree/unitree_ros2/`

---

## 1. 项目概览

Unitree ROS2 SDK（unitree_ros2）是宇树科技官方提供的、基于 ROS2 的机器人控制与通讯接口。该项目旨在让开发者通过 ROS2 的标准 Topic/Service 机制，直接与宇树机器人（Go2、B2、B2W、H1、G1）进行数据通讯和指令控制，**无需通过额外的 SDK 转发层**。

## 2. 通信架构：基于 DDS/ROS2

### 2.1 核心结论：DDS + ROS2

该 SDK 的接口实现**直接基于 ROS2，底层数据传输依赖 DDS（Data Distribution Service）**。

原因是：
- 宇树机器人内部运行 **Unitree SDK2**，该 SDK 使用 **CycloneDDS** 作为数据通信中间件
- ROS2 同样使用 DDS 作为通信层，因此两者在底层天然兼容
- 本 SDK 做的事情是将机器人内部 DDS 通信的 Topic 结构以 ROS2 `.msg` 格式定义出来，使 ROS2 节点可以直接发布/订阅机器人的 Topic

### 2.2 三层通信架构

```
┌──────────────────────────────────────┐
│          应用层 (Python/C++)          │
│  SportClient / LowCmd / 状态订阅      │
├──────────────────────────────────────┤
│          ROS2 中间件层                │
│  rclcpp / rclpy                      │
│  rmw_cyclonedds_cpp (RMW 实现)       │
├──────────────────────────────────────┤
│          DDS 层                       │
│  Eclipse CycloneDDS 0.10.x           │
│  UDP 多播 / 单播                      │
├──────────────────────────────────────┤
│          网络层                       │
│  以太网 (直连: 192.168.123.0/24)      │
│  无线网络 (可选)                      │
└──────────────────────────────────────┘
```

### 2.3 RMW（ROS Middleware）实现

- **使用 `rmw_cyclonedds_cpp`** 作为 ROS2 的 RMW 实现
- 需要编译特定版本的 CycloneDDS（0.10.x 分支）
- Humble 版本 ROS2 自带的 CycloneDDS 可用，Foxy 需自行编译

### 2.4 网络配置

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$HOME/cyclonedds_ws/cyclonedds.xml"
```

默认网卡：`eth0`（配置在 `cyclonedds.xml` 中），可通过修改该文件或环境变量切换。

## 3. 项目目录结构

```
unitree_ros2/
├── cyclonedds_ws/           # ROS2 工作空间（核心消息定义）
│   ├── src/
│   │   ├── cyclonedds.xml   # DDS 网络配置（默认 eth0）
│   │   └── unitree/
│   │       ├── unitree_api/ # 通用 API 消息（Request/Response）
│   │       ├── unitree_go/  # Go2/B2/B2W 机器人消息
│   │       └── unitree_hg/  # H1/G1 人形机器人消息
│   └── install/             # 编译产出
├── example/                 # C++ 示例程序
│   ├── src/
│   │   ├── include/common/  # 通用客户端库头文件
│   │   └── src/
│   │       ├── common/      # 客户端实现（SportClient 等）
│   │       ├── go2/         # Go2 专用示例
│   │       ├── b2/          # B2 专用示例
│   │       ├── b2w/         # B2W 专用示例
│   │       ├── g1/          # G1 专用示例
│   │       └── h1-2/        # H1-2 专用示例
│   ├── build/
│   └── install/
├── docs/                    # 文档图片
├── setup.sh                 # 环境配置脚本（需指定网卡）
├── setup_local.sh           # 本地回环配置（lo）
├── setup_default.sh         # 不指定网卡
├── README.md / README _zh.md
└── analysis/                # 本分析产出目录
    ├── docs/                # 文档
    ├── tests/               # 测试程序
    └── logs/                # 日志
```

## 4. ROS2 消息包详解

### 4.1 unitree_api — 通用请求/响应协议

定义了一个基于 DDS/JSON 的 RPC 风格通信协议：

| 消息 | 字段 | 说明 |
|------|------|------|
| `Request` | `header: RequestHeader` + `parameter: string` + `binary: uint8[]` | 请求消息 |
| `Response` | `header: ResponseHeader` + `data: string` + `binary: int8[]` | 响应消息 |
| `RequestHeader` | `identity: RequestIdentity` + `lease: RequestLease` + `policy: RequestPolicy` | 请求头 |
| `RequestIdentity` | `id: int64` + `api_id: int64` | 请求标识 |
| `RequestLease` | `id: int64` | 租约标识 |
| `RequestPolicy` | `priority: int32` + `noreply: bool` | 请求策略 |
| `ResponseHeader` | `identity: RequestIdentity` + `status: ResponseStatus` | 响应头 |
| `ResponseStatus` | `code: int32` | 状态码 |

**关键设计**：parameter 和 data 字段使用 **JSON 字符串**传递实际业务参数。每条请求通过 `api_id` 区分接口，通过 `id` 关联请求与响应。

### 4.2 unitree_go — Go2/B2/B2W 机器人消息

| 消息 | 类型 | 用途 |
|------|------|------|
| `SportModeState` | 状态 | 高层运动状态（位置、速度、姿态、步态） |
| `SportModeCmd` | 指令（Topic 直接发布） | 高层运动指令（已不推荐，改用 Request 协议） |
| `LowState` | 状态 | 底层状态（电机、IMU、电池、足端力） |
| `LowCmd` | 指令 | 底层电机控制（力矩/位置/速度 + KP/KD） |
| `MotorState` | 子消息 | 单个电机状态（角度、角速度、转矩估计、温度） |
| `MotorCmd` | 子消息 | 单个电机指令（目标位置/速度/力矩 + PID 参数） |
| `MotorStates` | 子消息 | 电机状态数组 |
| `MotorCmds` | 子消息 | 电机指令数组 |
| `IMUState` | 子消息 | IMU 状态（四元数、陀螺仪、加速度计、欧拉角） |
| `BmsState` | 子消息 | 电池管理系统状态 |
| `BmsCmd` | 子消息 | BMS 指令 |
| `WirelessController` | 状态 | 遥控器状态（摇杆、按键） |
| `LidarState` | 状态 | 激光雷达状态 |
| `HeightMap` | 状态 | 高度地图 |
| `AudioData` | 数据 | 音频数据 |
| `Go2FrontVideoData` | 数据 | Go2 前置摄像头数据 |
| `InterfaceConfig` | 配置 | 接口配置 |
| `Error` | 消息 | 错误信息 |
| `TimeSpec` | 子消息 | 时间戳 |
| `PathPoint` | 子消息 | 路径点（时间、位置、速度） |
| `UwbState` | 状态 | UWB 状态 |
| `UwbSwitch` | 指令 | UWB 开关 |
| `Req` | 消息 | 通用请求（uuid + body） |
| `Res` | 消息 | 通用响应（uuid + data + body） |

## 5. ROS2 Topic 映射

### 5.1 状态获取（订阅）

| ROS2 Topic | 消息类型 | 频率 | 说明 |
|------------|----------|------|------|
| `/sportmodestate` | `unitree_go::msg::SportModeState` | 高频 | 高层运动状态 |
| `/lf/sportmodestate` | `unitree_go::msg::SportModeState` | 低频 | 高层运动状态（低频版） |
| `/lowstate` | `unitree_go::msg::LowState` | 高频 | 底层状态 |
| `/lf/lowstate` | `unitree_go::msg::LowState` | 低频 | 底层状态（低频版） |
| `/wirelesscontroller` | `unitree_go::msg::WirelessController` | - | 遥控器状态 |
| `/utlidar/cloud` | `sensor_msgs::msg::PointCloud2` | - | 激光雷达点云 |
| `/utlidar/cloud_deskewed` | `sensor_msgs::msg::PointCloud2` | - | 去畸变点云 |
| `/utlidar/imu` | `sensor_msgs::msg::Imu` | - | 激光雷达内置 IMU |

### 5.2 指令控制（发布/请求）

| ROS2 Topic | 消息类型 | 方式 | 说明 |
|------------|----------|------|------|
| `/api/sport/request` | `unitree_api::msg::Request` | 发布 | 运动控制请求（高层） |
| `/api/sport/response` | `unitree_api::msg::Response` | 订阅 | 运动控制响应 |
| `/api/robot_state/request` | `unitree_api::msg::Request` | 发布 | 机器人状态控制请求（Humble） |
| `/api/robot_state/response` | `unitree_api::msg::Response` | 订阅 | 机器人状态控制响应 |
| `/lowcmd` | `unitree_go::msg::LowCmd` | 发布 | 底层电机指令 |
| `/utlidar/switch` | `std_msgs::msg::String` | 发布 | 激光雷达开关 |
| `/utlidar/client_command` | `std_msgs::msg::String` | 发布 | 激光雷达客户端命令 |

## 6. 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 20.04 (Foxy) / Ubuntu 22.04 (Humble, 推荐) |
| ROS2 版本 | Foxy 或 Humble |
| RMW 实现 | rmw_cyclonedds_cpp |
| CycloneDDS | 0.10.x（Foxy 需自行编译） |
| 网卡 | 以太网直连，IP：192.168.123.99，子网：255.255.255.0 |

## 7. 与 Unitree SDK2 的关系

- Unitree SDK2 是宇树的 C++ 官方 SDK（https://github.com/unitreerobotics/unitree_sdk2）
- unitree_ros2 是 ROS2 生态的适配层，将 SDK2 的 DDS Topic 映射为 ROS2 Topic
- 优势：无需在应用程序中集成 C++ SDK，纯 ROS2 节点即可与机器人通信
- Python 支持：通过 `rclpy` 即可用 Python 编写控制程序，**本 SDK 本身不包含 Python 包装代码**，开发者直接使用 rclpy 订阅/发布对应 Topic

## 8. 架构总结

```
                     ┌──────────────────┐
                     │   Unitree Go2    │
                     │  (运行 SDK2)      │
                     │  CycloneDDS 0.10 │
                     └────────┬─────────┘
                              │ 以太网 (192.168.123.x)
                              │
                     ┌────────▼─────────┐
                     │    开发主机       │
                     │  ROS2 + rclpy     │
                     │  rmw_cyclonedds   │
                     ├──────────────────┤
                     │ Python 控制程序   │
                     │ • publish 指令    │
                     │ • subscribe 状态  │
                     └──────────────────┘
```

**结论**：接口实现 = **ROS2 + CycloneDDS（DDS 实现）**，不是单独的 ROS 也不是纯 DDS，而是以 ROS2 为框架、DDS 为传输层的混合架构。