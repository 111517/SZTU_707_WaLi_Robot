# AI 助手对话框 — 实现计划

> 创建日期: 2026-06-08
> 关联: 机械狗 OpenClaw Gateway `<go2-ip>:18789`

## 目标

在 Go2 Web Dashboard 上添加一个 AI 助手对话框 —— 浮动按钮触发，配置后可连接机械狗的 OpenClaw Gateway 进行自然语言对话。

---

## 功能设计（从使用者角度）

### 🟢 核心功能（第一版）
1. **浮动 AI 按钮 (FAB)** — 固定在右下角，最小干扰，始终可见
2. **聊天对话框** — 点击 FAB 弹出，模态窗口
3. **设置面板** — 配置 Gateway URL、Token、Agent ID、Model、System Prompt
4. **流式回复** — SSE streaming，逐字显示 AI 回复
5. **对话历史** — 自动保存到 localStorage，刷新不丢失
6. **Markdown 渲染** — AI 回复支持代码块、列表等

### 🟡 进阶功能（后续迭代）
- 快捷指令模板（"查看状态"、"移动控制"、"传感器数据"）
- 上下文注入（机器人电池/姿态/速度 → system prompt）
- 导出对话为 Markdown/JSON
- 多轮对话管理（新建/切换/删除）

---

## 技术方案

### 组件树
```
App.tsx
 └─ AIChatFAB                    ← 浮动按钮 (fixed, bottom-right)
     └─ AIChatDialog            ← 弹窗
         ├─ header: 标题 + ⚙️设置 + ✕关闭
         ├─ body: AIChatMessage[] ← 消息列表
         ├─ footer: 输入框 + 发送
         └─ AIChatSettings       ← 侧滑面板
```

### 新建文件
```
项目根目录/
├── serve.py                           # Python 静态文件服务 + API 代理
├── AI助手实现记录.md                   # 实现文档
└── 对go2的改动.md                      # 远端配置变更记录

src/ros_web_gui_app/src/
├── components/ai/
│   ├── AIChatFAB.tsx + .css           # 浮动按钮
│   ├── AIChatDialog.tsx + .css        # 主对话框
│   ├── AIChatMessage.tsx + .css       # 消息气泡
│   └── AIChatSettings.tsx + .css      # 设置面板
├── hooks/
│   └── useOpenClawChat.ts             # 聊天状态 + API 调用
└── utils/
    └── openclawApi.ts                 # fetch + SSE 流式解析 + Markdown 渲染
```

### 修改文件
```
src/ros_web_gui_app/src/
├── styles/variables.css               ← 新增 10 个 AI Token + 3 个 keyframes
├── App.tsx                             ← 集成 AIChatFAB + AIChatDialog
└── vite.config.ts                      ← 端口改为 3000，新增 /api/ai proxy

start.sh                               ← python3 http.server → serve.py
```

### 数据流
```
localStorage ("ai_chat_settings")
  └─ { baseUrl, token, agentId, model, systemPrompt }
       │
       ▼
useOpenClawChat hook
  ├─ messages: Message[]
  ├─ isStreaming: boolean
  ├─ sendMessage(text) → fetch POST + ReadableStream SSE
  └─ clearMessages()
       │
       ▼
openclawApi.ts
  └─ streamChat() → POST /v1/chat/completions
       Headers: Authorization: Bearer <token>
       Body: { model, messages, stream: true }
       Response: SSE → parse data: chunks → onChunk callback
```

### API 端点
```
POST /api/ai/v1/chat/completions       ← 前端调用（同源，通过 serve.py 或 Vite 代理）
  → http://<go2-ip>:18789/v1/chat/completions   ← 实际转发目标
GET  /api/ai/v1/models                  ← 获取模型列表
  → http://<go2-ip>:18789/v1/models

Headers:
  Authorization: Bearer <token>
  Content-Type: application/json
  x-openclaw-session-key: <conversationId>   ← 显式控制 session 路由

Body:
  {
    "model": "openclaw/main",
    "stream": true,
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."}
    ],
    "temperature": 0.7,
    "top_p": 1,
    "max_tokens": 4096,
    "user": "<conversationId>"              ← OpenAI 标准字段，Gateway 派生 session key
  }

注意：OpenClaw 使用 body.user 字段（非 conversation_id）来关联同一会话的多个请求。
```

### 默认配置

| 项 | 值 |
|---|---|
| 代理路径 | `/api/ai` → `http://<go2-ip>:18789` |
| Token | `<go2-token>` |
| Model | `openclaw/main` |

---

## UI 设计规范（方向 C — 精炼浮动助手）

> **氛围关键词:** 暖精密度 · 机器人伙伴 · 毛玻璃层次 · 呼吸感 · 克制优雅
>
> 不是冷冰冰的科技产品，也不是幼稚的玩具。像一台精密仪器——有温度、有存在感。

---

### 扩展色彩 Token

在现有 `variables.css` 基础上新增，不覆盖任何已有变量：

```css
/* ── AI Chat 扩展 Token ─────────────────────────────── */
--ai-glass: rgba(255, 252, 247, 0.88);      /* 暖调毛玻璃底色 */
--ai-glass-border: rgba(0, 0, 0, 0.06);     /* 玻璃边缘 */
--ai-glass-shadow: 0 4px 32px rgba(0,0,0,0.12),
                   0 0 0 1px rgba(0,0,0,0.04);  /* 玻璃浮起阴影 */
--ai-glow: 0 0 24px rgba(37, 99, 235, 0.2); /* FAB 呼吸光晕 */
--ai-glow-connected: 0 0 20px rgba(22, 163, 74, 0.25);
--ai-bubble-user: linear-gradient(135deg, #2563eb, #1d4ed8);
--ai-bubble-ai: #f0efe9;
--ai-code-surface: #1a1917;
--ai-code-text: #e5e3dc;
--ai-fab-size: 52px;
--ai-dialog-width: 400px;
--ai-dialog-height: 600px;
--ai-header-height: 48px;
--ai-footer-height: 60px;
```

---

### FAB 按钮 — 机器人伙伴

**不是圆形，是超椭圆（squircle）**。像小型设备栖息在屏幕右下角。

| 属性 | 值 |
|---|---|
| 形状 | 超椭圆，`border-radius: 18px` |
| 尺寸 | 52×52px |
| 位置 | `fixed, bottom: 24px, right: 24px, z-index: 9999` |
| 背景 | `#ffffff` + 微阴影 |
| 图标 | 抽象机器人脸 — 两个圆点（眼睛）+ 一条微弧（嘴） |

**状态变化：**

| 状态 | 视觉效果 |
|---|---|
| 默认 | 纯白 squircle，浅阴影，眼睛 `#9e9b94`（灰色） |
| Hover | 放大至 1.08×，阴影加深，眼睛变 `#2563eb`，光晕浮现 |
| 已连接 | 眼睛变 `#16a34a`（绿色），3s 呼吸周期（光晕淡入淡出） |
| 连接中 | 眼睛变 `#d97706`（琥珀色），1s 快速脉冲 |
| 有新消息 | 右上角 8px 琥珀色圆点脉冲 |
| 对话框打开 | FAB 缩小消失，对话框从 FAB 位置 scale 弹出 |

---

### 对话框 — 暖调毛玻璃

核心思路：不是实色卡片，而是一块悬浮的毛玻璃，隐约透出 Dashboard 内容。

| 属性 | 值 |
|---|---|
| 尺寸 | 400×600px（桌面）/ 全屏（移动 < 480px） |
| 背景 | `rgba(255, 252, 247, 0.88)` |
| 模糊 | `backdrop-filter: blur(24px) saturate(1.2)` |
| 圆角 | 20px（比系统 14px 更饱满） |
| 阴影 | 多层玻璃阴影 |
| 边框 | 1px solid `rgba(0, 0, 0, 0.06)` |
| 顶部装饰线 | 2px 渐变条，颜色反映连接状态 |
| 动画原点 | `transform-origin: bottom right`（从 FAB 位置展开） |

**顶部装饰线（连接状态条）：**
- 绿色渐变 `#16a34a → #22c55e`：已连接
- 琥珀色渐变 `#d97706 → #f59e0b`：连接中
- 灰色 `#e5e3dc`：未配置/断开

**布局划分：**
```
┌─ 顶部装饰线 (2px) ───────────────────┐
│ 🏷 GO2 AI  ·  ● 已连接      ⚙️ ✕  │ ← header 48px
├──────────────────────────────────────┤
│                                      │
│   消息列表（flex-1, overflow-y）      │ ← body
│                                      │
├──────────────────────────────────────┤
│ ┌──────────────────────────────┐     │ ← footer 60px
│ │ 输入消息...              ➤   │     │
│ └──────────────────────────────┘     │
└──────────────────────────────────────┘
```

---

### 消息气泡 — 不对称设计

用户和 AI 的形状、颜色、对齐完全不同，一眼可辨。

#### 用户消息
| 属性 | 值 |
|---|---|
| 对齐 | 右对齐 |
| 背景 | 蓝色渐变 `linear-gradient(135deg, #2563eb, #1d4ed8)` |
| 文字颜色 | `#ffffff` |
| 圆角 | 16px / 16px / 4px / 16px（右下角锐利） |
| 内边距 | 10px 16px |
| 最大宽度 | 75% |
| 字体 | DM Sans, 13px |

#### AI 消息
| 属性 | 值 |
|---|---|
| 对齐 | 左对齐 |
| 前缀标签 | `GO2 >` 小标签（10px, DM Mono, `--text3`）在气泡上方 |
| 背景 | `#f0efe9` |
| 文字颜色 | `#1a1917` |
| 圆角 | 4px / 16px / 16px / 16px（左上角锐利） |
| 内边距 | 12px 16px |
| 最大宽度 | 80% |
| 字体 | DM Sans, 13px |

#### 代码块（AI 消息内）
| 属性 | 值 |
|---|---|
| 背景 | `#1a1917`（深色翻转） |
| 文字 | `#e5e3dc` |
| 字体 | DM Mono, 12px |
| 圆角 | 8px |
| 语言标签 | 右上角小标签（如 `json`, `bash`） |
| 复制按钮 | hover 时出现在右上角 |

#### 流式输出指示器
AI 消息末尾，流式输出时显示三个小圆点依次跳动（每个延迟 0.15s），颜色 `--accent`。

---

### 输入区域

| 属性 | 值 |
|---|---|
| 容器 | 56px 高，顶部 1px 分割线 |
| 输入框 | 弹性 pill，`border-radius: 28px`，背景 `--surface2` |
| 输入框文字 | DM Sans, 13px |
| Placeholder | `"向 GO2 发送指令..."` |
| 发送按钮 | 40×40px 圆形，`--accent-bg` 背景 |
| 发送图标 | 简洁箭头 `→`，hover 时向右滑动 2px |

**发送按钮状态机：**
```
[空闲] → 点击 → [箭头旋转 360°] → [三个脉冲点] → [流式结束] → [恢复箭头]
```

---

### 设置面板 — 设备舱门

从对话框**右侧滑入的抽屉**，像打开精密仪器的侧舱盖。

| 属性 | 值 |
|---|---|
| 宽度 | 对话框的 85%（约 340px） |
| 动画 | 从右滑入 + 淡入，0.28s cubic-bezier |
| 背景 | `--surface`（实色，非玻璃） |
| 遮罩 | 对话框其余区域半透明暗色 |
| 标题 | `⚙️ 连接设置` + 返回箭头 |

**快捷配置预设：**
```
┌─ 快捷配置 ──────────────────────┐
│ ○ 本地开发  http://localhost    │
│ ● 机械狗    http://<go2-ip>  │
│ ○ 自定义                        │
└────────────────────────────────┘
```

**表单元素：**
- 标签：11px, `--text3`, uppercase, letter-spacing
- 输入框：DM Mono 14px, `--surface2` 背景, 8px 圆角
- Token 输入：`type="password"`，带 👁 显示/隐藏切换
- 保存按钮：`action-btn primary` 风格
- 测试连接按钮：`action-btn` outline 风格

---

### 动画与微交互

| # | 动画 | 实现 | 时长 | 缓动 |
|---|------|------|------|------|
| 1 | FAB 入场 | translateY(20px) + opacity + scale 0.8→1 | 0.4s | spring-like cubic-bezier |
| 2 | FAB 呼吸 | box-shadow glow + scale 微变 | 3s | ease-in-out, infinite |
| 3 | 对话框打开 | scale(0.6)→scale(1) + opacity，原点 bottom-right | 0.28s | `var(--transition)` |
| 4 | 对话框关闭 | 反向，原点 bottom-right | 0.2s | ease-in |
| 5 | 消息入场 | `fadeSlideIn`（复用已有）+ 每条延迟 50ms | 0.28s | ease-out |
| 6 | 流式光标 | opacity 0↔1 blink | 0.6s | step-end |
| 7 | 流式三点 | 三个点依次 scale 0.5→1，间隔 0.2s | 0.6s/点 | ease-in-out |
| 8 | 发送按钮箭头 | hover 右移 2px + 点击旋转 360° | 0.28s | ease-out |
| 9 | 设置抽屉滑入 | translateX(100%) → 0 | 0.28s | cubic-bezier |
| 10 | 连接状态条变色 | background-color 渐变过渡 | 0.5s | ease |
| 11 | 新消息通知点 | 复用已有 `pulse-dot` | 1.5s | ease-in-out |
| 12 | 输入框 focus | border-color 过渡 + box-shadow glow | 0.2s | ease |

**性能原则：** 所有动画用 CSS `transform` + `opacity`，不触发 layout/reflow。移动端禁用 `backdrop-filter`，对话框全屏 + 从底部滑入。

---

### 可访问性

| 要求 | 实现 |
|---|---|
| FAB aria-label | `aria-label="打开 AI 助手"` |
| 对话框 role | `role="dialog"` + `aria-modal="true"` |
| ESC 关闭 | 键盘监听 Escape |
| Focus trap | 打开时 focus 锁定在对话框内 |
| 返回焦点 | 关闭后 focus 回到 FAB |
| 颜色对比度 | 暖白底 `#1a1917` 满足 AA，蓝色按钮白字满足 AAA |

---

### 整体效果

> 用户打开 Dashboard，右下角栖息着一个柔和发光的 squircle，两个小圆点像眼睛一样安静地注视。连接成功后，眼睛变绿，光晕开始缓慢呼吸。点击后，一块暖调毛玻璃从右下角展开，隐约透出 Dashboard 的内容。AI 的每一条回复前都带着 `GO2 >` 的小标签，像一个熟悉的机器人在终端里回话。这不是一个聊天窗口，这是一个**机器人伙伴的通讯频道**。

---

## CORS 处理

| 方案 | 说明 | 状态 |
|------|------|------|
| **serve.py 代理**（主方案） | 项目根 `serve.py` 替代 `python3 -m http.server`，同源转发 `/api/ai/*` → `http://<go2-ip>:18789`，支持 POST + SSE 流式 | ✅ 已实现 |
| **Vite proxy**（开发） | `vite.config.ts` 添加 `/api/ai` → `http://<go2-ip>:18789` | ✅ 已实现 |
| **OpenClaw CORS**（直接） | 远端 `openclaw.json` 的 `controlUi.allowedOrigins` 设为 `["*"]`，但 API 端点不返回 CORS 头，浏览器跨域不可用 | ❌ 不可行 |

> **结论：** OpenClaw 的 HTTP API 端点不返回 `Access-Control-*` 头，浏览器直连必然失败。必须使用代理（serve.py 或 Vite proxy），将请求转为同源。

### 远端 Go2 配置变更

对 `<go2-ip>` 的 `openclaw.json` 做了三处增量修改（详见 [对go2的改动.md](./对go2的改动.md)）：

| 改动 | 说明 |
|------|------|
| `gateway.bind: "lan"` | 监听 `0.0.0.0`，允许局域网访问 |
| `gateway.http.endpoints.chatCompletions.enabled: true` | 开启 HTTP Chat API（注意 endpoints 是对象） |
| `gateway.controlUi.allowedOrigins: ["*"]` | 允许任意来源（非 loopback 绑定时必需） |

全部为增量添加，不影响本地使用和飞书 Bot。

### 远端 Tb4 (<tb4-ip>) 配置

已通过 SSH 远程完成，与 Go2 相同三处配置：

```json
{
  "gateway": {
    "bind": "lan",
    "http": {
      "endpoints": {
        "chatCompletions": {
          "enabled": true
        }
      }
    },
    "controlUi": {
      "allowedOrigins": ["*"]
    }
  }
}
```

> ⚠️ `http.endpoints` 必须是对象 `{"chatCompletions": {"enabled": true}}`，不能是布尔值 `true`。设为布尔值会导致 OpenClaw 启动失败并自动恢复 last-good 配置。

---

## UI 设计工作流

实现时遵循以下流水线（Skills 已安装）：

```
/frontend-design → /baseline-ui → /fixing-accessibility → /fixing-motion
```

---

## 验证清单

- [x] `npm run dev` 或 `./start.sh` 启动后右下角出现 FAB 按钮
- [x] 点击 FAB → 对话框弹出
- [x] 设置面板可配置 Gateway URL + Token
- [x] 发送消息 → 流式显示 AI 回复
- [x] 刷新页面 → 设置和历史保留（localStorage）
- [x] 无 CORS 报错（通过 serve.py / Vite 代理解决）
