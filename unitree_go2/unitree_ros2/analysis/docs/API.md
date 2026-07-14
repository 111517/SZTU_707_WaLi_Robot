# Unitree ROS2 SDK — 完整 API 参考

> SDK 版本：v0.3.0 | 支持机器人：Go2 / B2 / B2W / H1 / G1

---

## 目录

1. [运动控制 API（SportClient）](#1-运动控制-api)
2. [机器人状态 API（RobotStateClient）](#2-机器人状态-api)
3. [底层电机控制（LowCmd）](#3-底层电机控制)
4. [状态获取 Topic](#4-状态获取-topic)
5. [通用请求/响应协议](#5-通用请求响应协议)
6. [Python 调用方式](#6-python-调用方式)

---

## 1. 运动控制 API

所有运动控制指令通过 `SportClient` 封装，发布到 Topic `/api/sport/request`，消息类型为 `unitree_api::msg::Request`。

### 1.1 基础运动

| API ID | 方法 | 参数 | 说明 |
|--------|------|------|------|
| 1001 | `Damp()` | 无 | 阻尼模式（关节柔性） |
| 1002 | `BalanceStand()` | 无 | 平衡站立 |
| 1003 | `StopMove()` | 无 | 停止运动 |
| 1004 | `StandUp()` | 无 | 起立 |
| 1005 | `StandDown()` | 无 | 趴下 |
| 1006 | `RecoveryStand()` | 无 | 恢复站立（跌倒后） |
| 1007 | `Euler(roll, pitch, yaw)` | roll, pitch, yaw (float) | 欧拉角姿态控制 |
| 1008 | `Move(vx, vy, vyaw)` | vx, vy, vyaw (float) | 速度控制移动 |
| 1009 | `Sit()` | 无 | 坐下 |
| 1010 | `RiseSit()` | 无 | 从坐下起身 |
| 1015 | `SpeedLevel(level)` | level (int) | 设置速度挡位 |
| 1016 | `Hello()` | 无 | 打招呼动作 |
| 1017 | `Stretch()` | 无 | 伸懒腰动作 |
| 1020 | `Content()` | 无 | 开心动作 |
| 1022 | `Dance1()` | 无 | 舞蹈 1 |
| 1023 | `Dance2()` | 无 | 舞蹈 2 |
| 1027 | `SwitchJoystick(flag)` | flag (bool) | 切换摇杆控制 |
| 1028 | `Pose(flag)` | flag (bool) | 姿态控制 |
| 1029 | `Scrape()` | 无 | 刮擦动作 |
| 1030 | `FrontFlip()` | 无 | 前空翻 |
| 1031 | `FrontJump()` | 无 | 前跳 |
| 1032 | `FrontPounce()` | 无 | 前扑 |
| 1036 | `Heart()` | 无 | 比心动作 |

### 1.2 高级步态（v0.2.0+）

| API ID | 方法 | 参数 | 说明 |
|--------|------|------|------|
| 1061 | `StaticWalk()` | 无 | 静态步行 |
| 1062 | `TrotRun()` | 无 | 小跑 |
| 1063 | `EconomicGait()` | 无 | 节能步态 |

### 1.3 特技动作（v0.2.0+）

| API ID | 方法 | 参数 | 说明 |
|--------|------|------|------|
| 2041 | `LeftFlip()` | 无 | 左侧空翻 |
| 2043 | `BackFlip()` | 无 | 后空翻 |
| 2044 | `HandStand(flag)` | flag (bool) | 倒立 |
| 2045 | `FreeWalk()` | 无 | 自由行走 |
| 2046 | `FreeBound(flag)` | flag (bool) | 自由跳跃行进 |
| 2047 | `FreeJump(flag)` | flag (bool) | 自由跳跃 |
| 2048 | `FreeAvoid(flag)` | flag (bool) | 自由避障 |
| 2049 | `ClassicWalk(flag)` | flag (bool) | 经典行走 |
| 2050 | `WalkUpright(flag)` | flag (bool) | 直立行走 |
| 2051 | `CrossStep(flag)` | flag (bool) | 交叉步 |

### 1.4 系统配置（v0.2.0+）

| API ID | 方法 | 参数 | 说明 |
|--------|------|------|------|
| 2054 | `AutoRecoverySet(flag)` | flag (bool) | 设置自动恢复 |
| 2055 | `AutoRecoveryGet(flag)` | flag (out bool) | 查询自动恢复状态 |
| 2058 | `SwitchAvoidMode()` | 无 | 切换避障模式 |

### 1.5 已废弃的 API（v0.1.0）

以下 API 在 v0.2.0 中已移除：

| API ID | 方法 |
|--------|------|
| 1011 | `SwitchGait()` |
| 1012 | `Trigger()` |
| 1013 | `BodyHeight()` |
| 1014 | `FootRaiseHeight()` |
| 1018 | `TrajectoryFollow()` |
| 1019 | `ContinuousGait()` |
| 1021 | `Wallow()` |
| 1024-1026 | GetBodyHeight / GetFootRaiseHeight / GetSpeedLevel |

---

## 2. 机器人状态 API

通过 `RobotStateClient` 封装（**仅支持 ROS2 Humble**），发布到 Topic `/api/robot_state/request`。

| API ID | 方法 | 参数 | 说明 |
|--------|------|------|------|
| 1001 | `ServiceSwitch(name, swit, status)` | name (str), swit (int), status (out int) | 切换服务开关 |
| 1002 | `SetReportFreq(interval, duration)` | interval (int), duration (int) | 设置报告频率 |
| 1003 | `ServiceList(list)` | list (out vector) | 获取服务列表 |

---

## 3. 底层电机控制

### 3.1 LowCmd 消息结构

发布到 Topic `/lowcmd`，消息类型 `unitree_go::msg::LowCmd`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `head` | `uint8[2]` | 帧头 (0xFE, 0xEF) |
| `level_flag` | `uint8` | 级别标志 (0xFF = 高级别) |
| `frame_reserve` | `uint8` | 帧保留 |
| `sn` | `uint32[2]` | 序列号 |
| `version` | `uint32[2]` | 版本 |
| `bandwidth` | `uint16` | 带宽 |
| `motor_cmd` | `MotorCmd[20]` | 20 个电机指令 |
| `bms_cmd` | `BmsCmd` | BMS 指令 |
| `wireless_remote` | `uint8[40]` | 无线遥控数据 |
| `led` | `uint8[12]` | LED 控制 |
| `fan` | `uint8[2]` | 风扇控制 |
| `gpio` | `uint8` | GPIO |
| `reserve` | `uint32` | 保留 |
| `crc` | `uint32` | CRC 校验 |

### 3.2 MotorCmd 子消息

| 字段 | 类型 | 说明 |
|------|------|------|
| `mode` | `uint8` | 模式：0x01=伺服(FOC)，0x00=待机 |
| `q` | `float32` | 目标关节角度 (rad) |
| `dq` | `float32` | 目标关节角速度 (rad/s) |
| `tau` | `float32` | 目标关节力矩 (N·m) |
| `kp` | `float32` | 刚度系数 |
| `kd` | `float32` | 阻尼系数 |
| `reserve` | `uint32[3]` | 保留 |

---

## 4. 状态获取 Topic

### 4.1 高层状态 SportModeState

Topic: `/sportmodestate` 或 `/lf/sportmodestate`

| 字段 | 类型 | 说明 |
|------|------|------|
| `stamp` | `TimeSpec` | 时间戳 |
| `error_code` | `uint32` | 错误码 |
| `imu_state` | `IMUState` | IMU 状态 |
| `mode` | `uint8` | 运动模式（0=idle, 1=balanceStand, 2=pose, 3=locomotion, 5=lieDown, 6=jointLock, 7=damping, 8=recoveryStand, 10=sit, 11=frontFlip, 12=frontJump, 13=frontPounce） |
| `progress` | `float32` | 动作执行进度 |
| `gait_type` | `uint8` | 步态类型（0=idle, 1=trot, 2=run, 3=climbStair, 4=forwardDownStair, 9=adjust） |
| `foot_raise_height` | `float32` | 抬腿高度 (m) |
| `position` | `float32[3]` | 当前位置 (x, y, yaw) |
| `body_height` | `float32` | 机体高度 (m) |
| `velocity` | `float32[3]` | 线速度 (m/s) |
| `yaw_speed` | `float32` | 偏航角速度 (rad/s) |
| `range_obstacle` | `float32[4]` | 障碍物距离范围 |
| `foot_force` | `int16[4]` | 足端力 |
| `foot_position_body` | `float32[12]` | 足端相对机体位置 |
| `foot_speed_body` | `float32[12]` | 足端相对机体速度 |

### 4.2 底层状态 LowState

Topic: `/lowstate` 或 `/lf/lowstate`

| 字段 | 类型 | 说明 |
|------|------|------|
| `head` | `uint8[2]` | 帧头 |
| `level_flag` | `uint8` | 级别标志 |
| `frame_reserve` | `uint8` | 保留 |
| `sn` / `version` | `uint32[2]` | 序列号/版本 |
| `bandwidth` | `uint16` | 带宽 |
| `imu_state` | `IMUState` | IMU 状态 |
| `motor_state` | `MotorState[20]` | 20 个电机状态 |
| `bms_state` | `BmsState` | BMS 状态 |
| `foot_force` | `int16[4]` | 足端力 |
| `foot_force_est` | `int16[4]` | 估计足端力 |
| `tick` | `uint32` | 计数值 |
| `wireless_remote` | `uint8[40]` | 无线遥控 |
| `bit_flag` | `uint8` | 位标志 |
| `adc_reel` | `float32` | ADC 值 |
| `temperature_ntc1/2` | `int8` | NTC 温度 |
| `power_v` | `float32` | 电池电压 (V) |
| `power_a` | `float32` | 电池电流 (A) |
| `fan_frequency` | `uint16[4]` | 风扇频率 |
| `crc` | `uint32` | CRC |

### 4.3 MotorState 子消息

| 字段 | 类型 | 说明 |
|------|------|------|
| `mode` | `uint8` | 工作模式 |
| `q` | `float32` | 当前角度 (rad) |
| `dq` | `float32` | 当前角速度 (rad/s) |
| `ddq` | `float32` | 当前角加速度 |
| `tau_est` | `float32` | 估计外力矩 (N·m) |
| `q_raw` | `float32` | 角度原始值 |
| `dq_raw` | `float32` | 角速度原始值 |
| `ddq_raw` | `float32` | 角加速度原始值 |
| `temperature` | `int8` | 温度 (°C) |
| `lost` | `uint32` | 丢包计数 |
| `reserve` | `uint32[2]` | 保留 |

### 4.4 IMUState 子消息

| 字段 | 类型 | 说明 |
|------|------|------|
| `quaternion` | `float32[4]` | 四元数 (w,x,y,z) |
| `gyroscope` | `float32[3]` | 陀螺仪 (rad/s) |
| `accelerometer` | `float32[3]` | 加速度计 (m/s²) |
| `rpy` | `float32[3]` | 欧拉角 (roll, pitch, yaw) |
| `temperature` | `int8` | 温度 |

### 4.5 BmsState 子消息

| 字段 | 类型 | 说明 |
|------|------|------|
| `version_high/low` | `uint8` | BMS 版本 |
| `status` | `uint8` | 状态 |
| `soc` | `uint8` | 电量百分比 |
| `current` | `int32` | 电流 (mA) |
| `cycle` | `uint16` | 循环次数 |
| `bq_ntc` | `int8[2]` | BQ 温度 |
| `mcu_ntc` | `int8[2]` | MCU 温度 |
| `cell_vol` | `uint16[15]` | 电芯电压 (mV) |

### 4.6 遥控器状态 WirelessController

Topic: `/wirelesscontroller`

| 字段 | 类型 | 说明 |
|------|------|------|
| `lx` | `float32` | 左摇杆 X |
| `ly` | `float32` | 左摇杆 Y |
| `rx` | `float32` | 右摇杆 X |
| `ry` | `float32` | 右摇杆 Y |
| `keys` | `uint16` | 按键键值 |

### 4.7 其他 Topic

| Topic | 消息类型 | 说明 |
|-------|----------|------|
| `/utlidar/cloud` | `sensor_msgs/PointCloud2` | 激光雷达点云 |
| `/utlidar/cloud_deskewed` | `sensor_msgs/PointCloud2` | 去畸变点云 |
| `/utlidar/imu` | `sensor_msgs/Imu` | 激光雷达内置 IMU |
| `/utlidar/switch` | `std_msgs/String` | 雷达开关控制 |
| `/utlidar/client_command` | `std_msgs/String` | 雷达客户端命令 |

---

## 5. 通用请求/响应协议

### 5.1 调用流程

```
应用 → 发布 Request (api_id + JSON参数) 到 /api/sport/request
     → 订阅 Response 从 /api/sport/response (过滤 api_id)
     → 解析 JSON data 字段获取结果
```

### 5.2 Request 结构

```python
# unitree_api::msg::Request
request = Request()
request.header.identity.api_id = 1008   # API ID
request.header.identity.id = timestamp   # 唯一请求 ID
request.parameter = '{"x": 0.3, "y": 0.0, "z": 0.0}'  # JSON 参数
request.binary = []  # 可选二进制数据
```

### 5.3 Response 结构

```python
# unitree_api::msg::Response
response.header.identity.api_id  # 与请求对应的 API ID
response.header.identity.id      # 与请求对应的 ID
response.header.status.code      # 0 = 成功
response.data                    # JSON 字符串响应数据
response.binary                  # 可选二进制数据
```

---

## 6. Python 调用方式

本项目为纯 ROS2 消息定义 + C++ 示例。**Python 中直接使用 `rclpy` 即可调用所有 API**。

### 6.1 环境准备

```bash
source /opt/ros/humble/setup.bash          # 或 foxy
source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="eth0" />
</Interfaces></General></Domain></CycloneDDS>'
```

### 6.2 发布运动控制指令

```python
import rclpy
from rclpy.node import Node
from unitree_api.msg import Request
import json

class Go2Controller(Node):
    def __init__(self):
        super().__init__('go2_controller')
        self.pub = self.create_publisher(Request, '/api/sport/request', 10)
    
    def move(self, vx, vy, vyaw):
        req = Request()
        req.header.identity.api_id = 1008  # Move
        req.parameter = json.dumps({"x": vx, "y": vy, "z": vyaw})
        self.pub.publish(req)
```

### 6.3 订阅状态

```python
from unitree_go.msg import SportModeState, LowState

# 订阅高层状态
self.create_subscription(SportModeState, '/sportmodestate', callback, 10)

# 订阅底层状态
self.create_subscription(LowState, '/lowstate', callback, 10)
```