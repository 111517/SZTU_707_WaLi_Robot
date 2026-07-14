# Go2 专属 API 参考手册

> 基于 Unitree ROS2 SDK v0.3.0  
> 适用机器人：Unitree Go2（四足机器人）

---

## 快速开始

### 连接配置

1. 用网线连接 Go2 和电脑
2. 将电脑的以太网 IP 设为 `192.168.123.99`，子网掩码 `255.255.255.0`
3. 配置环境：

```bash
source /opt/ros/humble/setup.bash
source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$HOME/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"
```

4. 验证连接：

```bash
ros2 topic list
# 应能看到 /sportmodestate、/lowstate 等话题
```

---

## 一、Go2 运动控制 API

所有运动控制通过 `/api/sport/request` Topic 发送 `unitree_api::msg::Request` 消息。

### 1.1 基本动作

| API ID | 动作 | Python 示例 |
|--------|------|------------|
| 1004 | 起立 | `publish(api_id=1004)` |
| 1005 | 趴下 | `publish(api_id=1005)` |
| 1002 | 平衡站立 | `publish(api_id=1002)` |
| 1001 | 阻尼模式 | `publish(api_id=1001)` |
| 1006 | 恢复站立 | `publish(api_id=1006)` |
| 1003 | 停止运动 | `publish(api_id=1003)` |

```python
def stand_up(self):
    req = Request()
    req.header.identity.api_id = 1004
    self.pub.publish(req)
```

### 1.2 移动控制

| API ID | 动作 | 参数 |
|--------|------|------|
| 1008 | 速度移动 | `x`(vx), `y`(vy), `z`(vyaw) — 前/侧/旋转速度 |
| 1007 | 欧拉角控制 | `x`(roll), `y`(pitch), `z`(yaw) |

```python
def move(self, vx, vy, vyaw):
    req = Request()
    req.header.identity.api_id = 1008
    req.parameter = json.dumps({"x": vx, "y": vy, "z": vyaw})
    self.pub.publish(req)

def euler(self, roll, pitch, yaw):
    req = Request()
    req.header.identity.api_id = 1007
    req.parameter = json.dumps({"x": roll, "y": pitch, "z": yaw})
    self.pub.publish(req)
```

### 1.3 坐/起

| API ID | 动作 |
|--------|------|
| 1009 | 坐下 |
| 1010 | 从坐下起身 |

### 1.4 表演动作

| API ID | 动作 | 说明 |
|--------|------|------|
| 1016 | Hello | 挥手打招呼 |
| 1017 | Stretch | 伸懒腰 |
| 1022 | Dance1 | 舞蹈 1 |
| 1023 | Dance2 | 舞蹈 2 |
| 1020 | Content | 开心 |
| 1029 | Scrape | 刮擦地面 |
| 1036 | Heart | 比心 |

### 1.5 特技动作 ⚠️ 确保环境安全

| API ID | 动作 | 说明 |
|--------|------|------|
| 1030 | FrontFlip | 前空翻 |
| 1031 | FrontJump | 前跳 |
| 1032 | FrontPounce | 前扑 |
| 2041 | LeftFlip | 左侧空翻 |
| 2043 | BackFlip | 后空翻 |
| 2044 | HandStand | 倒立（需要 flag 参数） |

### 1.6 步态控制

| API ID | 动作 | 参数 | 说明 |
|--------|------|------|------|
| 1061 | StaticWalk | 无 | 静态步行（最稳） |
| 1062 | TrotRun | 无 | 小跑 |
| 1063 | EconomicGait | 无 | 节能步态 |
| 2045 | FreeWalk | 无 | 自由行走 |
| 2046 | FreeBound | flag (bool) | 自由跳跃行进 |
| 2047 | FreeJump | flag (bool) | 自由跳跃 |
| 2048 | FreeAvoid | flag (bool) | 自由避障 |
| 2049 | ClassicWalk | flag (bool) | 经典行走 |
| 2050 | WalkUpright | flag (bool) | 直立行走 |
| 2051 | CrossStep | flag (bool) | 交叉步 |

### 1.7 配置与系统

| API ID | 动作 | 参数 | 说明 |
|--------|------|------|------|
| 1015 | SpeedLevel | level (int) | 速度挡位 |
| 1027 | SwitchJoystick | flag (bool) | 切换摇杆 |
| 1028 | Pose | flag (bool) | 姿态模式 |
| 2054 | AutoRecoverySet | flag (bool) | 自动恢复开关 |
| 2055 | AutoRecoveryGet | flag (out bool) | 查询自动恢复 |
| 2058 | SwitchAvoidMode | 无 | 切换避障模式 |

---

## 二、Go2 状态获取

### 2.1 高层运动状态

**Topic**: `/sportmodestate`（高频）或 `/lf/sportmodestate`（低频）  
**类型**: `unitree_go::msg::SportModeState`

```python
from unitree_go.msg import SportModeState

self.sub = self.create_subscription(
    SportModeState, '/sportmodestate', self.sport_callback, 10)

def sport_callback(self, msg):
    x, y, yaw = msg.position
    vx, vy, vz = msg.velocity
    roll, pitch, yaw_imu = msg.imu_state.rpy
    mode = msg.mode         # 当前运动模式
    gait = msg.gait_type    # 当前步态类型
```

**运动模式（mode）枚举**：

| 值 | 含义 |
|----|------|
| 0 | idle（默认站立） |
| 1 | balanceStand |
| 2 | pose |
| 3 | locomotion（运动） |
| 5 | lieDown |
| 6 | jointLock |
| 7 | damping |
| 8 | recoveryStand |
| 10 | sit |
| 11 | frontFlip |
| 12 | frontJump |
| 13 | frontPounce |

**步态类型（gait_type）枚举**：

| 值 | 含义 |
|----|------|
| 0 | idle |
| 1 | trot |
| 2 | run |
| 3 | climb stair |
| 4 | forwardDownStair |
| 9 | adjust |

### 2.2 底层状态

**Topic**: `/lowstate`（高频）或 `/lf/lowstate`（低频）  
**类型**: `unitree_go::msg::LowState`

```python
from unitree_go.msg import LowState

self.sub = self.create_subscription(
    LowState, '/lowstate', self.low_callback, 10)

def low_callback(self, msg):
    # IMU
    acc = msg.imu_state.accelerometer  # [x, y, z]
    gyro = msg.imu_state.gyroscope     # [x, y, z]
    rpy = msg.imu_state.rpy            # [roll, pitch, yaw]
    
    # 关节电机
    for i in range(12):  # Go2 有12个主动关节
        motor = msg.motor_state[i]
        angle = motor.q          # 当前角度
        velocity = motor.dq      # 角速度
        torque_est = motor.tau_est  # 估计力矩
    
    # 电池
    soc = msg.bms_state.soc       # 电量 %
    voltage = msg.power_v         # 电压 V
    current = msg.power_a         # 电流 A
    
    # 足端力
    fl = msg.foot_force[0]        # 前左
    fr = msg.foot_force[1]        # 前右
    rl = msg.foot_force[2]        # 后左
    rr = msg.foot_force[3]        # 后右
```

### 2.3 IMU 状态

```python
quat = msg.imu_state.quaternion   # [w, x, y, z]
gyro = msg.imu_state.gyroscope    # [gx, gy, gz] rad/s
acc  = msg.imu_state.accelerometer # [ax, ay, az] m/s²
rpy  = msg.imu_state.rpy          # [roll, pitch, yaw] rad
temp = msg.imu_state.temperature   # °C
```

### 2.4 遥控器

**Topic**: `/wirelesscontroller`  
**类型**: `unitree_go::msg::WirelessController`

```python
lx = msg.lx   # 左摇杆前后
ly = msg.ly   # 左摇杆左右
rx = msg.rx   # 右摇杆前后
ry = msg.ry   # 右摇杆左右
keys = msg.keys  # 按键（位掩码）
```

---

## 三、Go2 底层电机控制

**Topic**: `/lowcmd`  
**类型**: `unitree_go::msg::LowCmd`

⚠️ **底层控制需要理解机器人运动学，使用不当可能损坏电机或关节。必须设置正确的 CRC 校验。**

```python
from unitree_go.msg import LowCmd, MotorCmd

# 初始帧头
cmd = LowCmd()
cmd.head = [0xFE, 0xEF]
cmd.level_flag = 0xFF
cmd.gpio = 0

# 配置电机命令
for i in range(20):
    cmd.motor_cmd[i].mode = 0x01     # 伺服模式
    cmd.motor_cmd[i].q = 0.0           # 目标角度
    cmd.motor_cmd[i].dq = 0.0          # 目标角速度
    cmd.motor_cmd[i].tau = 0.0         # 目标力矩
    cmd.motor_cmd[i].kp = 60.0         # 刚度
    cmd.motor_cmd[i].kd = 5.0          # 阻尼

# CRC 校验（必须调用）
# 参考 example/src/src/common/motor_crc.cpp 中的 get_crc() 函数
```

---

## 四、机器人状态管理（Humble Only）

**Topic**: `/api/robot_state/request`  
**实现**: `RobotStateClient`

### 4.1 服务开关

```python
# API ID: 1001
req.parameter = '{"name": "sport_mode", "switch": 1}'  # 1=开, 0=关
```

### 4.2 设置报告频率

```python
# API ID: 1002
req.parameter = '{"interval": 3, "duration": 30}'
```

### 4.3 获取服务列表

```python
# API ID: 1003
# 返回可用服务列表
```

---

## 五、Go2 关节编号参考

Go2 每条腿有 3 个关节，共 12 个主动关节：

| 腿 | 髋关节 (Hip) | 大腿关节 (Thigh) | 小腿关节 (Calf) |
|----|-------------|-----------------|----------------|
| 前左 (FL) | 0 | 1 | 2 |
| 前右 (FR) | 3 | 4 | 5 |
| 后左 (RL) | 6 | 7 | 8 |
| 后右 (RR) | 9 | 10 | 11 |

---

## 六、安全注意事项

1. **特技动作（空翻/跳）**：确保 Go2 周围有足够空间，地面平坦有缓冲
2. **底层控制**：必须先让机器人进入阻尼模式，再发送 LowCmd
3. **CRC 校验**：底层指令必须通过 CRC 校验，否则机器人会忽略指令
4. **停止运动**：紧急情况调用 `StopMove()` (API ID 1003) 或 `Damp()` (API ID 1001)
5. **电池监控**：务必关注 BMS 电量，避免机器人低电量倒地
6. **网络稳定性**：直连网线，避免 WiFi 延迟导致控制中断