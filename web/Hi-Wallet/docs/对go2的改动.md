# 对 Go2 的改动

> 日期: 2026-06-08
> 目标设备: <go2-ip> / <go2-ip-alt> (<ssh-user>@<ssh-host>)
> 配置文件: `~/.openclaw/openclaw.json`

## 改动原因

开发机 (<dev-ip>) 需要调用 Go2 上的 OpenClaw Chat API，但远端配置只绑定了 loopback，局域网无法访问。

## 具体改动

### 1. `gateway.bind` → `"lan"`

原来未设置（默认仅监听 `127.0.0.1`），改为 `"lan"`（监听 `0.0.0.0`），允许局域网设备访问。

### 2. `gateway.http.endpoints` → 开启 Chat Completions

原来未设置，新增：

```json
"http": {
  "endpoints": {
    "chatCompletions": {
      "enabled": true
    }
  }
}
```

### 3. `gateway.controlUi.allowedOrigins` → `["*"]`

原来未设置，新增以允许浏览器跨域请求（开发阶段用 `*`，生产环境建议改为具体域名）。

## 影响评估

全部为**增量添加**，未修改或删除任何原有配置：
- 本地 localhost 访问不受影响
- 飞书 Bot（bot_a / bot_b）不受影响
- DeepSeek API Key 配置未改动
- 原有 auth token 未改动

## 服务重启

修改后执行了 `systemctl --user restart openclaw-gateway`，服务正常运行。

## 验证

```bash
# 无需认证（应返回 401 — 正常）
curl http://<go2-ip>:18789/v1/models

# 带认证（应返回 200 + 模型列表）
curl -H "Authorization: Bearer <go2-token>" \
     http://<go2-ip>:18789/v1/models
```
