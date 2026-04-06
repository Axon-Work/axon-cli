# Design Study Notes — 2026-04-04

Study of Claude Code (cc) and OpenClaw architecture, for informing OpenScienceNet design decisions.

---

## Part 1: Claude Code (cc)

### What It Is
Anthropic 官方 CLI 工具。TypeScript + React (Ink) 构建的终端 AI 编程助手。

### 核心架构

```
用户输入 → query.ts (主循环) → Claude API → Tool 执行 → 结果回注 → 循环
```

**关键文件**：
- `query.ts` (68K行) — 整个查询编排在一个文件里。为什么不拆？因为是紧耦合的循环逻辑，拆了反而增加复杂度
- `main.tsx` (4.6K行) — CLI 入口，参数解析，初始化管道
- `Tool.ts` — Tool 接口定义，所有 42 个工具实现统一接口

### 值得学习的设计模式

**1. Tool 系统 — 统一接口 + 权限管理**
```typescript
interface Tool {
  name: string
  inputSchema: JSONSchema
  execute(input, context): Promise<ToolResult>
}
```
- 40+ 工具（Bash、文件读写、Agent 派生、搜索等）全部实现同一接口
- 三级权限：always-allow / always-deny / ask-user
- 权限检查在执行前，不在工具内部

**对 OS 的启发**：我们的 eval 类型也是类似模式（engine.py dispatcher），但更简单。如果未来 eval 类型很多，可以借鉴这个 Tool 注册 + 权限的模式。

**2. 状态管理 — Zustand 风格的不可变 store**
```typescript
setAppState(prev => ({ ...prev, field: newValue }))
```
- 永不直接 mutate
- 所有副作用通过 `onChangeAppState` 观察者触发
- 支持 undo/redo、时间旅行调试

**对 OS 的启发**：我们后端用的是 SQLAlchemy ORM + 直接修改对象属性。状态管理相对简单，但如果未来加 WebSocket 实时推送，需要考虑类似的事件驱动模式。

**3. Feature Gate — 编译期条件编译**
```typescript
if (feature('KAIROS')) {
  const assistant = require('./assistant/index.js')
}
```
- 构建时消除死代码
- 一套代码出多个产品变体（内部版 vs 外部版）

**对 OS 的启发**：我们目前只有一个版本，但如果未来区分"平台版"和"社区版"（如官方任务 vs 用户任务），可以用 feature flag。

**4. 查询循环 — 流式执行 + 自动压缩**
```
Input → Build System Prompt → Stream API Call → Execute Tools → Collect Results → Loop
```
关键特性：
- 接近 token 上限时自动压缩历史消息
- Tool 调用流式并发执行
- 网络错误智能重试
- 成本实时追踪

**对 OS 的启发**：Mining loop 已经类似这个模式。但我们缺少：
- 成本追踪（矿工花了多少 API 费用 vs 赚了多少 OS）
- 自动上下文管理（矿工的 prompt 可能超长）

**5. 自定义终端 UI — 全控 Ink 渲染器**
```
/ink/
├── layout/ (Yoga flexbox)
├── events/ (键盘、鼠标、焦点)
├── components/ (Box, Text, Button)
└── termio/ (ANSI 解析)
```
- 不用第三方 UI 库，完全自研
- 原因：需要对性能、键盘处理、主题系统有完全控制

**对 OS 的启发**：我们的 CLI 用 Typer + Rich，已经够用。但如果未来做实时挖矿仪表盘（score 变化曲线、多任务并行），可能需要更复杂的终端 UI。

**6. Session 持久化**
- 消息历史写入磁盘
- 可以跨会话恢复
- 成本也持久化

**对 OS 的启发**：CLI 的 mining session 目前不持久化。如果矿工挖到一半断了，没法恢复。应该考虑保存 my_best_answer/my_best_score 到本地。

---

## Part 2: OpenClaw

### What It Is
个人 AI 助手，支持 25+ 通讯渠道（WhatsApp, Telegram, Slack, Discord 等），本地运行优先。

### 核心架构 — Hub & Spoke

```
消息渠道 (WhatsApp, Telegram, Slack...)
        ↓
┌────────────────────────┐
│   Gateway (WebSocket)   │ ← 控制平面: ws://127.0.0.1:18789
│   核心基础设施           │
└─────────┬──────────────┘
    ├─ Agent Runtime (RPC)
    ├─ CLI
    ├─ WebChat
    ├─ macOS/iOS/Android App
    └─ Plugins
```

### 值得学习的设计模式

**1. Plugin SDK — 公开契约隔离核心**
```
extensions/ 只能导入 openclaw/plugin-sdk/*
不能导入 src/** 或 src/channels/**
```
- Plugin 通过 manifest (`openclaw.plugin.json`) 声明能力
- 核心重构不影响插件
- SDK 版本化，向后兼容

**对 OS 的启发**：如果 OS 未来开放第三方 eval 类型，应该定义类似的 eval plugin SDK：
```python
class EvalPlugin:
    id: str
    config_schema: dict
    async def evaluate(answer: str, config: dict) -> EvalResult
```
第三方可以实现自己的 eval 类型（如特定领域的评分器），不需要改后端核心代码。

**2. Channel 系统 — 可插拔的消息适配器**
每个 Channel 实现统一接口：
```typescript
handleInbound(envelope)  // 接收消息
send(payload)           // 发送消息
probe()                 // 健康检查
monitor()               // 事件监听
```

**对 OS 的启发**：类比到 OS，"Channel" = "LLM Provider"。目前矿工用 litellm 封装了多个 provider，但后端的 llm_judge 是硬编码 Anthropic API。应该抽象为 provider plugin：
```python
class LLMProvider:
    id: str  # "anthropic", "openai", "ollama"
    async def complete(prompt, model, max_tokens) -> str
```

**3. Gateway-First — WebSocket 控制平面**
- 所有客户端（CLI、App、Web）通过 WebSocket 连 Gateway
- 不用 REST — 因为需要实时事件推送和流式传输
- RPC 模型：类型化的请求/响应

**对 OS 的启发**：目前后端是纯 REST API。但 mining 场景天然需要实时性：
- 矿工想看到其他矿工的 improvement 实时通知
- 任务 completion 的实时广播
- 排行榜实时更新
→ 未来应该加 WebSocket endpoint（FastAPI 原生支持）

**4. DM 安全 — 默认 Pairing 模式**
```
陌生发送者 → 生成配对码 → 需要人工审批
已批准发送者 → 加入白名单 → 正常处理
```

**对 OS 的启发**：类比到任务系统。目前"早期只有官方能发任务"是手动控制。未来开放用户发任务时，可以引入类似的"任务审核"机制：
- 新用户发任务 → 需要审核/质押
- 信誉高的用户 → 自动通过

**5. Config 系统 — 层级覆盖**
```
文件 (~/.openclaw/config.json)
  ↓ 被覆盖
环境变量
  ↓ 被覆盖
CLI 参数
  ↓ 被覆盖
Runtime patches (Session 级)
```

**对 OS 的启发**：我们的配置也类似（pydantic-settings 读环境变量，CLI 有 config.toml），但缺少 session 级覆盖。Mining 时矿工可能想临时改 model 或参数。

**6. 懒加载 — 性能优化**
- Channel 注册路径（热路径）保持精简
- 重操作延迟到 `*.runtime.ts`
- SDK facade 无循环依赖

**对 OS 的启发**：后端的 eval 加载已经是懒加载（engine.py import 时加载所有 evaluator）。如果 eval 类型很多，应该改为按需 import。

---

## Part 3: 对 OpenScienceNet 的设计建议

基于这两个项目的学习，OS 项目可以借鉴的几个核心改进方向：

### 优先级高

| 改进 | 来源 | 理由 |
|------|------|------|
| **Mining session 持久化** | CC 的 session 系统 | 矿工断线后能恢复，不丢失 best_answer |
| **WebSocket 实时通知** | OpenClaw 的 Gateway | 多矿工场景需要实时 score 更新 |
| **Eval Plugin SDK** | OpenClaw 的 Plugin SDK | 开放第三方 eval 类型，不改核心代码 |
| **成本追踪** | CC 的 cost tracker | 矿工需要知道 API 花了多少 vs 赚了多少 |

### 优先级中

| 改进 | 来源 | 理由 |
|------|------|------|
| **Provider 抽象层** | OpenClaw 的 Channel 系统 | llm_judge 不应该硬编码 Anthropic |
| **Config 层级覆盖** | OpenClaw 的 Config 系统 | Mining 时临时改参数 |
| **任务审核机制** | OpenClaw 的 DM Pairing | 开放用户发任务时的质量控制 |
| **Feature flags** | CC 的 feature gate | 区分平台版/社区版 |

### 优先级低（架构上的好东西但现在不急）

| 改进 | 来源 | 理由 |
|------|------|------|
| **不可变状态管理** | CC 的 Zustand store | 复杂状态流时有用，目前 ORM 够用 |
| **Terminal UI 升级** | CC 的 Ink renderer | 实时挖矿仪表盘，等 V2 再说 |
| **懒加载 eval** | OpenClaw 的懒加载 | eval 类型少时不需要 |

---

## Part 4: 架构对比表

| 维度 | Claude Code | OpenClaw | OpenScienceNet |
|------|-------------|----------|----------------|
| 语言 | TypeScript | TypeScript | Python |
| 运行时 | Bun/Node | Node | uvicorn (async) |
| UI | Custom Ink (React) | Multi-channel | Typer + Rich (CLI) |
| 状态管理 | Zustand store | Gateway state | SQLAlchemy ORM |
| 通信 | Direct API | WebSocket Gateway | REST API |
| 插件系统 | MCP + Tools | Plugin SDK | Eval types (硬编码) |
| 认证 | OAuth + API key | Gateway auth | JWT |
| 配置 | ~/.claude/ | ~/.openclaw/config.json | ~/.oscli/config.toml |
| 并发 | Streaming + Agent spawn | Multi-channel concurrent | SELECT FOR UPDATE |
| 测试 | Colocated .test.ts | Vitest + E2E | Pytest (38+13 tests) |

---

## Part 5: 立即可执行的 Action Items

1. **Mining session 持久化**：在 `~/.oscli/sessions/<task_id>.json` 保存 `{my_best_answer, my_best_score, round_log}`，mine 命令启动时检查恢复
2. **成本追踪**：mining loop 里记录每轮 LLM 调用的 token 数（litellm 返回 usage），summary 里显示预估 API 花费
3. **WebSocket endpoint**：FastAPI 加 `/ws` 端点，广播 task score 更新事件，CLI 可选订阅
4. **Eval Plugin interface**：定义 `EvalPlugin` 协议，当前 6 个 eval 重构为 plugin 实例，为第三方开放
