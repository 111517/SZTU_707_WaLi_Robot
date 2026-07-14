# Go2 机器狗 HTTP API 速查卡

## 连接信息

```
Base URL: http://192.168.1.105:8001    (WiFi)  ← 推荐
         或 http://192.168.123.18:8001  (直连)
```

所有端点在 `0.0.0.0:8001` 监听，局域网内任意设备可访问。仅需 HTTP，无需 ROS2 环境。

---

## 基础指令

```bash
curl -X POST http://192.168.1.105:8001/stand     # 站立
curl -X POST http://192.168.1.105:8001/sit       # 坐下
curl -X POST http://192.168.1.105:8001/lie       # 趴下
curl -X POST http://192.168.1.105:8001/stop      # 停止
curl -X POST http://192.168.1.105:8001/recovery  # 恢复站立
curl -X POST http://192.168.1.105:8001/damping   # 阻尼卸力
```

端口可省略（默认 8001）。

## 移动控制

```bash
# 前进
curl -X POST http://192.168.1.105:8001/walk -H 'Content-Type: application/json' -d '{"vx":0.3}'

# 后退
curl -X POST http://192.168.1.105:8001/walk -H 'Content-Type: application/json' -d '{"vx":-0.2}'

# 原地左转
curl -X POST http://192.168.1.105:8001/turn -H 'Content-Type: application/json' -d '{"vyaw":0.5}'

# 复合移动（前进+横移+转向）
curl -X POST http://192.168.1.105:8001/move -H 'Content-Type: application/json' -d '{"vx":0.3,"vy":0,"vyaw":0.1}'
```

## 表演动作

```bash
curl -X POST http://192.168.1.105:8001/action -H 'Content-Type: application/json' -d '{"name":"hello"}'     # 打招呼
curl -X POST http://192.168.1.105:8001/action -H 'Content-Type: application/json' -d '{"name":"dance"}'     # 跳舞
curl -X POST http://192.168.1.105:8001/action -H 'Content-Type: application/json' -d '{"name":"wave"}'      # 挥手
curl -X POST http://192.168.1.105:8001/action -H 'Content-Type: application/json' -d '{"name":"heart"}'     # 比心
curl -X POST http://192.168.1.105:8001/action -H 'Content-Type: application/json' -d '{"name":"stretch"}'   # 伸展
```

## 状态查询

```bash
curl http://192.168.1.105:8001/health    # 健康检查
curl http://192.168.1.105:8001/status    # 完整状态
```

## 紧急停止

```bash
curl -X POST http://192.168.1.105:8001/emergency_stop    # 急停→阻尼
```

---

## 用户指令 → API 映射

| 用户说 | 对应 API |
|--------|----------|
| 站起来 / 起立 / stand up | `POST /stand` |
| 趴下 / 躺下 / lie down | `POST /lie` |
| 坐下 / sit | `POST /sit` |
| 停下 / 停 / stop | `POST /stop` |
| 前进 / 往前走 | `POST /walk {"vx":0.3}` |
| 后退 / 往后 | `POST /walk {"vx":-0.2}` |
| 左转 / 右转 | `POST /turn {"vyaw":0.5}` 或 `-0.5` |
| 跳舞 / 表演 | `POST /action {"name":"dance"}` |
| 打个招呼 / 你好 | `POST /action {"name":"hello"}` |
| 急停 / 紧急停止 | `POST /emergency_stop` |
| 状态 / 怎么样 | `GET /status` |

---

## 安全准则

1. **动作前确认周围空间**（建议 ≥2m×2m）
2. 涉及行走控制时建议先用低速 (`vx=0.1`)
3. `emergency_stop` 优先于所有其他指令
4. 直立状态才能执行行走/动作