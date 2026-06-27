# AI 助手实现记录

> 日期: 2026-06-08
> 基于: [AI助手计划.md](./AI助手计划.md) 方向 C — 精炼浮动助手

## 文件清单

### 新建

```
src/ros_web_gui_app/src/
├── styles/variables.css          ← 新增 10 个 AI Token + 3 个 keyframes
├── utils/openclawApi.ts          ← SSE 流式解析 + Markdown 渲染 + localStorage 读写
├── hooks/useOpenClawChat.ts      ← 聊天状态管理（消息/流式/设置/持久化）
├── components/ai/
│   ├── AIChatFAB.tsx + .css      ← 浮动按钮（超椭圆 + 机器人面部 + 呼吸动画）
│   ├── AIChatDialog.tsx + .css   ← 主对话框（毛玻璃 + 连接状态条 + 响应式 + 快捷键）
│   ├── AIChatMessage.tsx + .css  ← 消息气泡（用户渐变蓝 / AI 暖灰 + 思考过程折叠块）
│   └── AIChatSettings.tsx + .css ← 设置面板（模型选择 + 参数滑块 + 双机代理预设）
└── App.tsx                        ← 集成 FAB + Dialog，全局可用

项目根目录/
├── serve.py                       ← Python 静态文件服务 + 多后端 API 代理（Go2 + Tb4）
├── AI助手实现记录.md              ← 本文件
└── 对go2的改动.md                 ← 远端 <go2-ip> 配置变更记录
```

### 修改

| 文件 | 改动 |
|---|---|
| `vite.config.ts` | 端口 5173→3000，新增 `/api/ai` + `/api/ai-tb4` 双代理 |
| `start.sh` | `python3 -m http.server` → `python3 serve.py`，支持 POST/代理 |

---

## 架构

```
App.tsx
 ├─ AIChatFAB           ← fixed 右下角，始终可见
 └─ AIChatDialog        ← 条件渲染，点击 FAB 弹出
     ├─ Sidebar         ← 对话列表（☰ 切换，侧滑）
     ├─ ai-dialog-main  ← 列容器（header + body + footer）
     │   ├─ Header      ← GO2 AI 标题 + 连接状态灯 + ⚙️/+/✕
     │   ├─ Body        ← 消息列表 or 空状态 or 设置面板
     │   │   ├─ AIChatMessage[]  ← 每条消息独立组件
     │   │   └─ AIChatSettings   ← 侧滑覆盖 body
     │   └─ Footer      ← textarea + 发送/停止按钮
     └─ ConnectionBar   ← 顶部 2px 状态线
```

数据流：
```
localStorage ──► openclawApi.loadSettings() ──► useOpenClawChat
                openclawApi.loadConversations() ──► conversations[]
                openclawApi.streamChat()  ←── sendMessage(text)
                       │
                       ▼
                POST /api/ai/v1/chat/completions (同源)
                       │
                       ▼
                serve.py 代理 → <go2-ip>:18789 (Go2)
                              → <tb4-ip>:18789 (Tb4)
                       │
                       ▼
                SSE ReadableStream → onToken/onReasoning → 逐字追加
```

---

## 关键实现细节

### 双机代理架构

```
浏览器 :3000
   │
   ├── /api/ai      → serve.py/Vite 代理 → <go2-ip>:18789 (Go2)
   │
   └── /api/ai-tb4  → serve.py/Vite 代理 → <tb4-ip>:18789 (Tb4)
```

设置面板预设：
| 预设 | 路径 | 说明 |
|------|------|------|
| Go2 (.3) 代理 | `/api/ai` | ✅ 走代理到 Go2 |
| Tb4 (.2) 代理 | `/api/ai-tb4` | ✅ 走代理到 Tb4 |
| Go2 (.3) 直连 | `http://<go2-ip>:18789` | ⚠️ OpenClaw 安全机制限制 |
| Tb4 (.2) 直连 | `http://<tb4-ip>:18789` | ⚠️ 需先配 CORS |
| 本地开发 | `localhost:18789` | 本机调试 |
| 自定义 | 手动输入 | 任意地址 |

**为什么直连不可用？** OpenClaw 有一个安全机制：`control UI requires device identity (use HTTPS or localhost secure context)`。即使配置了 `allowedOrigins: ["*"]` CORS 放行，应用层仍然会拒绝非 localhost、非 HTTPS 的请求。代理模式从服务端转发，不存在此问题。

**远端所需配置（代理模式）**：只需改两处 `openclaw.json`——
- `bind: "lan"`（监听所有网络接口）
- `http.endpoints: true`（开启 HTTP API）
- **不需要**配置 `allowedOrigins`

### CSS 布局修复

**Bug**：`.ai-dialog` 使用 `flex-direction: row`，但 header/body/footer 是直接子元素，缺少列容器，导致三个区域被排成一行，UI 挤成窄条。

**修复**：新增 `.ai-dialog-main` 作为列容器（`flex-direction: column; flex: 1`）包裹 header+body+footer。Sidebar 保持 `position: absolute` 侧滑覆盖。

### SSE 流式解析 (`openclawApi.ts`)
- 用 `fetch` + `ReadableStream` + `TextDecoder` 逐行解析 SSE `data:` 块
- 支持 `AbortController` 中途取消
- 解析 `[DONE]` 和 `finish_reason` 作为结束信号
- JSON 解析错误静默跳过（容忍畸形 chunk）
- **新增**：捕获 `delta.reasoning_content` / `delta.thinking_content` 作为思考过程
- **新增**：请求体传递 `temperature`、`top_p`、`max_tokens` 参数
- **新增**：`fetchModels()` 从 `/v1/models` 拉取可用模型列表

### 对话管理 (`useOpenClawChat.ts`)
- `Conversation[]` — 多对话支持，每条对话有 `id/title/messages[]/createdAt/updatedAt`
- `convsRef` + `activeIdRef` 模式 — 保持异步回调中状态引用始终最新，避免 stale closure
- `isStreaming` — 流式输出中标志，用于 UI 状态切换
- `settings` — 连接配置，变更自动写 localStorage
- 流式输出时用 `assistantId` 定位并逐字追加 content + reasoning
- `sendMessage()` — 构建 API messages，添加 user+assistant 消息，处理流式回调
- `retryLast()` — 移除失败回复，重发最后一条用户消息
- `regenerate()` — 移除最后 AI 回复，重新生成
- `stopStreaming()` — abort fetch
- `createConversation()` / `deleteConversation()` / `switchConversation()` — 完整 CRUD
- 自动标题：取第一条用户消息前 30 字
- 旧格式 `ai_chat_history` 自动迁移到新格式 `ai_chat_conversations`

### 思考过程展示 (`AIChatMessage.tsx`)
- 当模型支持 reasoning（DeepSeek-R1、Claude Thinking、o1 等），在回复上方渲染可折叠思考块
- 使用 `<details>` 元素，默认展开
- 思考中状态：琥珀色边框 + 脉冲指示点 + "思考中..." 标签
- 完成后：灰色边框 + "已完成思考" 标签 + 折叠箭头
- 思考内容最大高度 240px，超出滚动
- 复制消息时会包含思考过程

### 模型参数调节 (`AIChatSettings.tsx + .css`)
- **模型下拉框**：自动从 `/v1/models` 拉取，支持自定义输入，带刷新按钮
- **Temperature 滑块**：0–2，步长 0.1，显示精确/平衡/创造三档标签
- **Top P 滑块**：0–1，步长 0.05，实时显示当前值
- **Max Tokens**：256–32768 数字输入，控制单次回复最大长度
- **上下文用量条**：估算当前对话 token 数 + 可视化进度条（相对 32K 上下文）
- **Token 估算**：`estimateTokens()` / `estimateContextTokens()` — CJK 字符加权
- 连接测试按钮同时刷新模型列表 + 测试连通性，8s 超时

### 键盘快捷键 (`AIChatDialog.tsx`)
| 快捷键 | 动作 |
|--------|------|
| `Esc` | 层级退出：关闭设置 → 关闭侧栏 → 关闭对话框 |
| `⌘N` / `Ctrl+N` | 新建对话 |
| `⌘W` / `Ctrl+W` | 关闭对话框 |
| `⌘⇧K` / `Ctrl+Shift+K` | 删除当前对话 |
| `Enter` | 发送消息 |
| `Shift+Enter` | 换行 |

### Markdown 渲染 (`parseMarkdown()`)
- 无须额外依赖，纯正则替换
- 支持：代码块(` ``` `)、内联代码(` `` `)、粗体(`**`)、斜体(`*`)、无序列表(`- `)、链接(`[]()`)
- HTML 转义防 XSS

### FAB 按钮 (`AIChatFAB.tsx + .css`)
- 超椭圆形状 `border-radius: 18px`，56×56px，4 种状态：
  - 默认：灰色眼睛 + 灰色嘴
  - 已连接：绿色眼睛 + 绿色嘴 + 3s 呼吸光晕 (`fabBreathe`)
  - 连接中：琥珀色眼睛 + 1s 快速脉冲
  - Hover：放大 1.08× + 变蓝
- 入场动画：`fabEnter` — translateY + scale + opacity，0.4s spring 缓出
- 新消息通知点：右上角 8px 圆点脉冲（连通绿色/未通琥珀色）

### 对话框 (`AIChatDialog.tsx + .css`)
- 尺寸：480×680px，固定定位右下角（bottom: 92px, right: 24px）
- 毛玻璃：`backdrop-filter: blur(24px) saturate(1.2)` + 暖调半透明 `rgba(255,252,247,0.88)`
- 打开：`transform-origin: bottom right`，从 FAB 位置 scale 弹出，0.28s
- 顶部 2px 装饰线：颜色随连接状态渐变（绿/琥珀），0.5s 过渡
- 侧栏：260px 宽，滑入动画，显示对话列表（标题+日期+删除），按更新时间倒序
- 草稿保留：切换对话时保存未发送文本到 `draftRef`，切回时恢复
- 移动端 `< 480px`：全屏 + 禁用 backdrop-filter（性能）+ 底部滑入动画
- 空状态：🐕 图标 + 引导文案
- 流式三点指示器：流式开始、AI 内容为空时，三个圆点依次跳动（延迟 0.2s）
- **新增**：停止按钮在流式输出时替换发送按钮

### 消息气泡 (`AIChatMessage.tsx + .css`)
- 不对称设计：
  - 用户：右对齐，蓝色渐变背景，圆角 16/16/4/16（右下锐利），最大 75% 宽
  - AI：左对齐，暖灰 `#f0efe9`，圆角 4/16/16/16（左上锐利），最大 80% 宽
- AI 消息前缀标签 `GO2 >`（DM Mono, 10px, text3）
- 错误状态：红色边框 + 红色背景，左侧显示 🔄 重试按钮
- 思考过程：折叠块，琥珀色/灰色边框，脉冲指示点
- 代码块：深色翻转 `#1a1917` 背景，DM Mono 12px，右上角 📋 复制按钮
- 消息操作：hover 显示 📋 复制 / ↻ 重新生成 / 🔄 重试按钮
- 流式光标：8×15px 蓝色竖条，0.6s 闪烁
- 时间戳：相对时间（刚刚/X分钟前/具体时间）+ token 用量

### 设置面板 (`AIChatSettings.tsx + .css`)
- 从对话框 body 区域 overlay 滑入（非独立弹窗），0.28s cubic-bezier
- 6 个快捷预设 radio + URL/token/model 输入
- 测试连接按钮：fetch `/v1/models`，8s 超时，显示 ✅/❌
- Token 输入：`type="password"`，带 👁/🙈 切换
- System prompt textarea，DM Mono 字体
- Temperature/Top P range slider，自定义样式（蓝色圆形滑块 + 白色边框）
- 上下文用量条：进度条 + `~X,XXX tokens` 文字

### 可访问性
- FAB: `aria-label="打开 AI 助手"`
- Dialog: `role="dialog"` + `aria-modal="true"`
- ESC 关闭（全局 keydown 监听，设置面板打开时先关面板）
- 输入框: `aria-label="输入消息"`
- 关闭按钮 hover 变红 `var(--red-bg)`

---

## 网络层：跨域问题与解决方案

### 问题演进

| 阶段 | 现象 | 原因 |
|---|---|---|
| 1 | `NetworkError` | 浏览器直连 `http://<go2-ip>:18789`，跨域触发 OPTIONS 预检，OpenClaw 返回 405 |
| 2 | `501 Unsupported method` | 改为 `/api/ai` 相对路径，但 `start.sh` 用 `python3 -m http.server`，不支持 POST |
| 3 | ✅ 正常 | 写 `serve.py` 替代 http.server，同源代理转发 |
| 4 | `control UI requires device identity` | OpenClaw 应用层安全机制，拒绝非 localhost/HTTPS 请求 |
| 5 | ✅ 直连不可用，代理可用 | 代理从服务端转发，绕过浏览器安全检查 |

### 最终方案：serve.py

在项目根目录写了 [serve.py](./serve.py) — 一个同时提供静态文件服务和多后端 API 代理的 Python 脚本：

```
浏览器 fetch('/api/ai/v1/chat/completions')     ← 同源请求，无跨域
       │
       ▼
serve.py (端口 3000)
  ├─ 路径不以 /api/ai* 开头 → 作为静态文件处理（GET）
  ├─ 路径以 /api/ai/ 开头   → 转发到 http://<go2-ip>:18789 (Go2)
  └─ 路径以 /api/ai-tb4/ 开头 → 转发到 http://<tb4-ip>:18789 (Tb4)
                                · 逐 chunk 流式写回（SSE 兼容）
                                · 处理 CORS 预检（OPTIONS → 204）
```

环境变量：
- `AI_PROXY_GO2` — 覆盖 Go2 代理目标（默认 `http://<go2-ip>:18789`）
- `AI_PROXY_TB4` — 覆盖 Tb4 代理目标（默认 `http://<tb4-ip>:18789`）

`start.sh` 已修改为调用 `serve.py` 而非 `python3 -m http.server`。

### Vite 开发模式

`vite.config.ts` 中配置了双代理：
- `/api/ai` → `http://<go2-ip>:18789` (Go2)
- `/api/ai-tb4` → `http://<tb4-ip>:18789` (Tb4)

使用 `npm run dev` 同样可用。端口统一改为 3000。

---

## 默认配置

| 项 | 值 |
|---|---|
| Go2 Gateway URL | `/api/ai`（通过代理 → `http://<go2-ip>:18789`） |
| Tb4 Gateway URL | `/api/ai-tb4`（通过代理 → `http://<tb4-ip>:18789`） |
| Token | `<go2-token>` |
| Model | `openclaw/main`（可从下拉列表切换） |
| Temperature | 0.7 |
| Top P | 1 |
| Max Tokens | 4096 |

设置和对话历史自动保存到 localStorage（key: `ai_chat_settings` / `ai_chat_conversations`），刷新不丢失。历史最多保留 50 个对话，旧格式 `ai_chat_history` 自动迁移。

---

## 远端 Go2 设备变更

详见 [对go2的改动.md](./对go2的改动.md)。摘要：
- `gateway.bind` → `"lan"`（局域网可访问）
- `gateway.http.endpoints.chatCompletions` → `enabled: true`
- `gateway.controlUi.allowedOrigins` → `["*"]`
- 全部为增量添加，不影响飞书 Bot / CLI / 本地使用

Tb4 (<tb4-ip>) 配置已于 2026-06-08 通过 SSH 远程修改完成：
- `gateway.bind` → `"lan"`（监听 0.0.0.0）
- `gateway.http.endpoints.chatCompletions.enabled` → `true`（注意：endpoints 是对象不是布尔值！）
- `gateway.controlUi.allowedOrigins` → `["*"]`（非 loopback 绑定时必需）
- 已重启 `openclaw gateway` 进程使配置生效
- 配置备份：`~/.openclaw/openclaw.json.bak.20260608_214457`

---

## 会话追踪修复 (2026-06-08)

### 问题
OpenClaw Dashboard 中每次发送消息都创建新会话，同一对话窗口的消息无法归入同一 session。

### 根因
OpenClaw 的 `/v1/chat/completions` 端点使用 **OpenAI 标准 `user` 字段** 来派生 session key，而非自定义字段。之前错误地发送了 `conversation_id` / `session_id` / `X-Conversation-ID` / `X-Session-ID`，这些字段 OpenClaw 均不识别。

### 修复
`openclawApi.ts` → `streamChat()`：
- 移除 header `X-Conversation-ID`、`X-Session-ID`
- 移除 body `conversation_id`、`session_id`
- 移除 header `x-openclaw-session-key`（裸 conversationId 作 key，Dashboard 不显示）
- 仅用 body `user`：conversationId（OpenAI 标准字段，Gateway 派生 `agent:main:openai-user:<id>` 格式 session key）

### 最终方案（2026-06-08 最终确认）
经过多轮测试，确认：
- ❌ `x-openclaw-session-key` header → 裸 ID 作 session key → Dashboard 不认
- ✅ `user` body 字段 → Gateway 自动派生 `agent:main:openai-user:<id>` → Dashboard 正常显示 + 会话正确归组

参考：实际查看 Tb4 的 `~/.openclaw/agents/main/sessions/sessions.json`，确认 session key 格式规律：
```
agent:main:main                  ← Control UI WebSocket
agent:main:feishu:group:...      ← 飞书群聊
agent:main:openai-user:test-123  ← HTTP API (user 字段) ✅
1780916376971-b0nb8bf            ← HTTP API (x-openclaw-session-key 裸 ID) ❌
```

---

## 预设切换器 & 对话隔离 (2026-06-08)

### 标题栏预设切换器
在标题栏添加 `GO2 ◉ TB4` pill toggle 按钮，点击直接切换机器预设（无需进入设置面板）。同时切换 baseUrl、token、对话列表和历史。

### 对话按预设完全隔离
每个机器（Go2/Tb4）有独立的对话空间：

**数据层** (`openclawApi.ts`)：
- `Conversation` 新增 `baseUrl` 字段

**Hook 层** (`useOpenClawChat.ts`)：
- `createConversation(baseUrl?)` 新建对话时打上预设标签

**UI 层** (`AIChatDialog.tsx`)：
- 侧栏只显示当前预设的对话（按 baseUrl 过滤）
- `presetActiveRef` 记录每个预设最后活跃的对话 ID
- 切换预设时自动保存/恢复各预设的对话和历史
- 旧对话（无 baseUrl）自动归入 Go2

**预设 token 同步** (`AIChatSettings.tsx`)：
- `PRESETS` 增加 `token` 字段
- 切换预设时自动填入对应 token 并刷新模型列表
- Go2: `<go2-token>` / Tb4: `<tb4-token>`

### 标题动态显示
标题从硬编码 `"GO2 AI"` 改为根据 `settings.baseUrl` 动态切换 (`"/api/ai-tb4"` → `"TB4 AI"` / 其他 → `"GO2 AI"`)。

---

## serve.py GET 代理修复 (2026-06-08)

### 问题
`/v1/models` 等 GET 端点返回 404，因为 `serve.py` 只代理了 POST 和 OPTIONS 方法。

### 修复
- 提取 `_proxy_request(method)` 通用方法，支持任意 HTTP 方法
- 新增 `do_GET()`：匹配代理路径时转发 GET，否则回退到静态文件服务
- 更新 CORS preflight：允许的方法从 `POST, OPTIONS` 改为 `GET, POST, OPTIONS`

---

## 待后续迭代

- [x] Vite proxy 转发（双机）
- [x] Python serve.py 代理（双后端路由）
- [x] CORS 跨域解决
- [x] 多轮对话管理（新建/切换/删除）
- [x] 多行输入（textarea，Enter 发送，Shift+Enter 换行）
- [x] 消息复制（整条 + 代码块）
- [x] 发送失败重试
- [x] 重新生成（regenerate）
- [x] 时间戳显示
- [x] Token 用量显示
- [x] 草稿保留（per-conversation）
- [x] 停止生成
- [x] 模型选择下拉（从 API 拉取）
- [x] Temperature / Top P / Max Tokens 参数调节
- [x] 思考过程展示（reasoning/thinking 折叠块）
- [x] 键盘快捷键（Esc/⌘N/⌘W/⌘⇧K）
- [x] 上下文用量估算
- [x] CSS 布局修复（dialog 挤成一条）
- [x] 对话框尺寸调整（480×680）
- [x] 双机代理架构（Go2 .3 + Tb4 .2）
- [x] Tb4 远端配置（openclaw.json — bind=lan + http.endpoints + controlUi）
- [x] 会话追踪修复（user 字段 → agent:main:openai-user 格式）
- [x] serve.py GET 请求代理（/v1/models 等）
- [x] 预设切换器（标题栏 GO2 ◉ TB4 pill toggle）
- [x] 对话按预设完全隔离（baseUrl 标签 + 侧栏过滤 + 历史独立）
- [x] 预设 token 自动切换
- [x] 标题动态显示（GO2 AI / TB4 AI）
- [ ] 上下文注入（电池/姿态/速度 → system prompt）
- [ ] 导出对话为 Markdown/JSON
- [ ] 更好的 Markdown 渲染（代码语法高亮、表格）
- [ ] 上下文窗口余量警告
