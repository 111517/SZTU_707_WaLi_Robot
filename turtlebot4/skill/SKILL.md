---
name: turtlebot4-bridge
description: |
  Control TurtleBot4 via the OpenClaw Nav2 Bridge HTTP API.
  Bridge 常驻后台运行（systemd 管理）。所有导航任务自动走完整流水线：检查bridge → 脱桩 → 执行任务 → 回桩。
  当用户说"回充电桩"/"回原点"/"回去"/"充电"/"dock"，直接调用 /navigation/dock。
  Triggers: "turtlebot4", "robot", "机器人", "move", "stop", "save map", "navigate", "goto", "dock", "charge", "充电", "回去", "原点", "出发", "离开", "undock", "拍照", "巡逻", "巡检", "依次", "先去", "再去", "然后去", "途经", "挨个", "居中", "对准", "瞄准".
---

# TurtleBot4 Bridge Skill

Control the TurtleBot4 robot through a local FastAPI bridge at `localhost:8001`.

## 完整任务流水线（自动执行）

**所有导航类任务都走这个流水线，无需手动分步操作。**

```
Step 0: 检查bridge     →  Step 1: 脱桩
Step 2: 执行任务       →  Step 3: 回充电桩
```

### Step 0 — 检查 bridge（bridge 常驻后台，通常已在线）

```bash
curl -s --max-time 2 http://localhost:8001/
```
有 JSON 返回 → bridge 在线，进入 Step 1。

无响应 → bridge 未运行，需要启动：
```bash
sudo systemctl start tb4-bridge
```
等待 bridge HTTP 就绪后继续（`curl -s --max-time 2 http://localhost:8001/` 确认）。

**`--max-time 2` 必须带，否则 curl 会在 bridge 离线时卡 30 秒。**

### Step 1 — 脱离充电桩

```bash
curl -s -X POST http://localhost:8001/navigation/undock
```
Create3 原生 undock，自动离开。返回 success 后进入 Step 2。

### Step 2 — 执行任务

根据用户指令执行，常见模式见下方"任务模式"。**所有导航必须用 `wait: true`**，确保到达后才执行后续操作。

### Step 3 — 回到充电桩

```bash
curl -s -X POST http://localhost:8001/navigation/dock
```
内部分两步：① Nav2 导航到充电桩前方 0.8m 接近点（自动避障）② 红外精确对接。
对接完成后坐标自动更新为原点坐标。

### 流水线规则

- **严格按顺序执行** — 上一步成功才进入下一步
- **任务完成后必须回桩**（Step 3）—— 即使任务失败也要回
- **Step 2 的导航必须用 `wait: true`** — 同步等待到达，否则后续步骤时机错乱
- **任何一步失败** → 告诉用户哪一步失败了，仍执行 Step 3 回桩收尾

---

## API 速查

### 导航

```bash
# 异步导航（不等待到达）
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": 1.0, "y": 0.5, "theta": 0.0}'

# 同步导航（等到达才返回，流水线中必须用这个）
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": 1.0, "y": 0.5, "theta": 0.0, "wait": true}'

# 取消导航
curl -s -X POST http://localhost:8001/navigation/cancel
```

### Dock / Undock

```bash
curl -s -X POST http://localhost:8001/navigation/dock     # 回充电桩
curl -s -X POST http://localhost:8001/navigation/undock    # 离开充电桩
```

### 位姿标定

```bash
curl -s -X POST http://localhost:8001/localization/initialize -H "Content-Type: application/json" -d '{}'
```

### 相机

```bash
curl -s http://localhost:8001/camera/capture    # 拍照 → JSON 含 base64 + file_path

# 照片自动保存到 /tmp/openclaw_capture.jpg，直接读这个文件即可，无需处理 base64

# YOLO 检测（原地慢速旋转扫描）
curl -s "http://localhost:8001/camera/detect?object=人&timeout_sec=20&confidence=0.4"

# YOLO 检测 + 居中 + 拍照（检测到后自动对准目标、拍照返回）
curl -s "http://localhost:8001/camera/detect-and-center?object=人&timeout_sec=30&confidence=0.4"
```
- `found_centered` → 目标居中，照片在 `/tmp/openclaw_capture.jpg`
- `not_found` → 全程未检测到
- `found_lost` → 检测到但居中时丢失，已对最后方向拍照

### 控制

```bash
curl -s -X POST http://localhost:8001/control/move \
  -H "Content-Type: application/json" \
  -d '{"linear_x": 0.2, "angular_z": 0, "duration": 5}'

curl -s -X POST http://localhost:8001/control/stop
```

### 状态

```bash
curl -s http://localhost:8001/status/robot
curl -s http://localhost:8001/status/battery
curl -s http://localhost:8001/status/pose
```

### SLAM

```bash
curl -s -X POST http://localhost:8001/mapping/save \
  -H "Content-Type: application/json" \
  -d '{"name": "office_map"}'
```

### 进程管理

Bridge 由 systemd 服务 `tb4-bridge` 管理，常驻后台。

```bash
sudo systemctl start tb4-bridge     # 启动
sudo systemctl stop tb4-bridge      # 停止
sudo systemctl restart tb4-bridge   # 重启
sudo systemctl status tb4-bridge    # 查看状态
```

---

## 任务模式

### 模式 A：去某地拍照回来

用户说"去 X 拍照回来"、"去 X 看一眼"：

执行完整流水线 Step 0→1，然后：

```
Step 2a — 同步导航到目标（wait: true 必须）：
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": <x>, "y": <y>, "theta": 0, "wait": true}'
成功 → 2b，失败 → 跳到 Step 3

Step 2b — 拍照（自动保存到 /tmp/openclaw_capture.jpg）：
curl -s http://localhost:8001/camera/capture
然后直接读 /tmp/openclaw_capture.jpg 返回图片给用户
```

然后执行 Step 3（回桩）。

### 模式 B：去某地找东西回来

用户说"去 X 看看有没有 Y"、"去 X 找 Z"：

执行完整流水线 Step 0→1，然后：

```
Step 2a — 同步导航到目标：
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": <x>, "y": <y>, "theta": 0, "wait": true}'

Step 2b — YOLO 检测（中英文均可）：
curl -s "http://localhost:8001/camera/detect?object=<目标物体>&timeout_sec=10"
  - found → 告诉用户"找到了，置信度 X"
  - not_found → 告诉用户"没有找到"
```

用户说"去 X 对准 Y 拍照"、"去 X 居中拍 Y"、"去 X 找 Y 并拍清楚"：

```
Step 2b — YOLO 检测 + 自动居中拍照：
curl -s "http://localhost:8001/camera/detect-and-center?object=<目标物体>&timeout_sec=30"
  - found_centered → 读 /tmp/openclaw_capture.jpg 返回给用户
  - not_found → 告诉用户"没有找到"
  - found_lost → 返回现有的照片，标注"找到但未居中"
```

然后执行 Step 3（回桩）。

### 模式 C：纯导航（去某地不回来）

用户只说"去 X"（没有说拍照/找东西/回来）：

执行完整流水线 Step 0→1，然后导航到目标（`wait: true`），然后 **仍然执行 Step 3**（默认回桩）。

### 纯 dock/undock（无任务）

用户只说"回充电桩"、"回去"、"出发"、"离开"：

- **回桩**：直接 `curl -s -X POST http://localhost:8001/navigation/dock`
- **出发**：执行 Step 0→1，告诉用户"已离开充电桩，请告诉我接下来做什么"
- **无任务时的 dock**：先检查 bridge（Step 0），然后直接 dock。

### 模式 D：多点任务（巡逻/巡检/依次访问）

用户说"先去A再去B"、"巡逻三个点"、"依次去X、Y、Z"、"去A拍照然后去B看看有没有人"：

执行完整流水线 Step 0→1，然后按顺序遍历每个地点：

```
Step 2a — 导航到地点1 (wait: true)：
curl -s -X POST http://localhost:8001/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"x": <x1>, "y": <y1>, "theta": 0, "wait": true}'
成功 → [可选动作]，失败 → 记录失败，继续下一个

Step 2b — 导航到地点2 (wait: true)：
成功 → [可选动作]，失败 → 记录失败，继续下一个

... 依次执行所有地点 ...
```

**每个地点可选的动作**：
- `拍照` → `curl -s http://localhost:8001/camera/capture`
- `找东西` → `curl -s "http://localhost:8001/camera/detect?object=<物体>&timeout_sec=10"`
- `对准拍照` → `curl -s "http://localhost:8001/camera/detect-and-center?object=<物体>&timeout_sec=30"`
- `纯到达` → 不执行额外动作，直接进入下一个点

**规则**：
- 必须按顺序执行，当前点到达后才进入下一点
- 单个点导航失败 → 记录为失败，**跳过并继续**下一个点
- 所有点都失败 → 报告"所有地点均导航失败"
- 任何情况下都执行 Step 3 回桩
- 用户说"停"/"取消" → 取消当前导航，跳到 Step 3

**结果汇总回报**（所有点执行完毕后统一输出）：

```
✅ 前门门口：已到达
❌ 后门：导航失败，已跳过
✅ 冰箱：已到达，检测到1人
✅ 初始点：已到达，拍照成功

正在返回充电桩...
```

---

## 地点查找

所有任务需要去某地时，从位置文件查找坐标：

```bash
cat config/location_707.json
```
匹配 `name` 或 `aliases` 找到 `x`, `y`。未找到 → 回答"没有查找到该物体的位置"。

---

## 默认参数

- 移动速度: `0.2 m/s`
- 角速度: `0.5 rad/s`
- 导航超时: 120s

## Troubleshooting

- `localhost:8001` 拒绝连接 → `sudo systemctl start tb4-bridge`
- Bridge / Nav2 / AMCL 常驻后台运行（systemd 管理）
