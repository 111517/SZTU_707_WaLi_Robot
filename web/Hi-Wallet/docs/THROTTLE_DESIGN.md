# unitree_bridge_node 话题节流设计文档

## 概述

`unitree_bridge_node` 将 Go2 机器人的高频原始话题桥接到标准 ROS2 类型，再通过 rosbridge WebSocket 推送到 Web 前端。源话题速率通常为 **100+ Hz**（如 `/lowstate`、`/sportmodestate`），若逐帧转发会造成 rosbridge 和前端的大量带宽浪费。

本文档描述了为每个桥接话题配置的**基于时间的节流（throttle）**机制。

## 机制

### `_should_publish(throttle_key: str) -> bool`

使用 `self.get_clock().now()` 记录每个 throttle_key 的最后发布时间。如果距离上次发布的时间 ≥ 设定的间隔，返回 `True` 并更新时间戳；否则返回 `False` 跳过发布。

```python
# 伪代码
now = clock.now()
elapsed = (now - last_publish[key]).nanoseconds * 1e-9
if elapsed >= interval:
    last_publish[key] = now
    return True
return False
```

### 回调中的使用模式

```python
def _on_lowstate(self, msg):
    if self._should_publish('throttle.joint_states'):
        # 构建并发布 /joint_states
        ...

    if self._should_publish('throttle.battery'):
        # 构建并发布 battery_state 等相关话题
        ...
```

> **关键点**：源回调仍以全速率触发——我们只是在发布端跳过冗余输出。TF 姿态追踪等非发布状态更新不受节流影响。

## 节流参数表

所有参数均为 ROS2 参数，可在 launch 文件或运行时动态调整，无需重新编译。

| ROS2 参数 | 默认间隔 | 实际频率 | 影响的话题 | 说明 |
|-----------|---------|---------|-----------|------|
| `throttle.joint_states` | 0.05s | **20 Hz** | `/joint_states` | 3D 机器人模型流畅动画 |
| `throttle.odom` | 0.05s | **20 Hz** | `/odom` | 平滑 TF 树和位置追踪 |
| `throttle.imu` | 0.1s | **10 Hz** | `/imu/data` | 姿态/方向显示，低状态和运动状态回调共享同一节流键 |
| `throttle.point_cloud2` | 0.2s | **5 Hz** | `/point_cloud2` | 大消息体，5Hz 可视化已足够 |
| `throttle.velocity` | 0.1s | **10 Hz** | `/robot/velocity/x`、`/y`、`/yaw` | 速度指示器需要一定平滑度 |
| `throttle.body_height` | 1.0s | **1 Hz** | `/robot/body_height` | 身高变化缓慢 |
| `throttle.gait_type` | 0.5s | **2 Hz** | `/robot/gait_type` | 步态极少变化 |
| `throttle.foot_force` | 1.0s | **1 Hz** | `/robot/foot_force` | 仅用于监控 |
| `throttle.battery` | 120.0s | **1次/2分钟** | `/battery_state`、`/battery/voltage`、`/battery/current`、`/battery/percent` | 电池电压以分钟为尺度漂移 |
| `throttle.diagnostics` | 10.0s | **0.1 Hz** | `/diagnostics` | 状态日志，非实时 |

## 带宽节省估计

以 `/sportmodestate` 源速率 ~100 Hz 为基准：

| 话题组 | 节流前 | 节流后 | 减少比例 |
|--------|--------|--------|---------|
| `battery*` (4 个话题) | ~400 msg/s | ~0.03 msg/s | **99.99%** |
| `diagnostics` | ~100 msg/s | ~0.1 msg/s | **99.9%** |
| `velocity*` (3 个话题) | ~300 msg/s | ~30 msg/s | **90%** |
| `body_height` | ~100 msg/s | ~1 msg/s | **99%** |
| `foot_force` | ~100 msg/s | ~1 msg/s | **99%** |
| `gait_type` | ~100 msg/s | ~2 msg/s | **98%** |
| `point_cloud2` | ~10 msg/s | ~5 msg/s | **50%** |
| `imu/data` | ~200 msg/s | ~10 msg/s | **95%** |
| `joint_states` | ~100 msg/s | ~20 msg/s | **80%** |
| `odom` | ~30 msg/s | ~20 msg/s | **33%** |

> 总计：从 ~1,540 msg/s 降至 ~89 msg/s，减少约 **94%**。

## 中继话题（未修改）

以下话题通过 `_relay_sub` 直接转发，不做节流，因为它们本身就是低频事件型话题：

| 源话题 | 目标话题 |
|--------|---------|
| `/servicestate` | `/robot/service_state` |
| `/lf/battery_alarm` | `/robot/battery_alarm` |
| `/gas_sensor` | `/sensor/gas` |
| `/gpt_state` | `/ai/gpt_state` |

UWB 话题（`/uwb_state`、`/uwb_switch`）也不做节流——同样为低频事件。

## 运行时调参

### 命令行

```bash
# 查看全部节流参数
ros2 param list /unitree_bridge_node | grep throttle

# 运行时修改（立即生效）
ros2 param set /unitree_bridge_node throttle.battery 60.0
ros2 param set /unitree_bridge_node throttle.body_height 0.5
```

### launch 文件

```python
Node(
    package='go2_web_bridge',
    executable='unitree_bridge_node',
    name='unitree_bridge_node',
    parameters=[{
        'throttle.battery': 60.0,       # 自定义电池更新频率
        'throttle.point_cloud2': 0.1,    # 自定义点云频率
    }],
),
```

### YAML 配置文件

```yaml
# config/throttle_overrides.yaml
unitree_bridge_node:
  ros__parameters:
    throttle.battery: 60.0
    throttle.point_cloud2: 0.1
```

```bash
ros2 run go2_web_bridge unitree_bridge_node --ros-args --params-file config/throttle_overrides.yaml
```

## 新增节流键步骤

如需为未覆盖的话题添加节流：

1. 在 `__init__` 的 `throttle_defaults` 字典中新增条目：
   ```python
   'throttle.new_topic': 0.5,  # 2 Hz
   ```

2. 在对应的回调中包裹 `_should_publish` 检查：
   ```python
   if self._should_publish('throttle.new_topic'):
       self.new_pub.publish(msg)
   ```

3. 重新构建：
   ```bash
   colcon build --packages-select go2_web_bridge
   ```

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/go2_web_bridge/go2_web_bridge/unitree_bridge_node.py` | 桥接节点（节流实现处） |
| `src/go2_web_bridge/launch/dashboard.launch.py` | 主 launch 文件 |
| `src/ros_web_gui_app/src/components/panels/RobotCorePanel.tsx` | 前端机器人状态面板（含速度 SMA 平滑） |
| `src/ros_web_gui_app/src/utils/RosbridgeConnection.ts` | rosbridge WebSocket 连接封装 |
