# Dify vs Coze vs aiPlat — 三方深度对比分析

> 2026-05-16 · 先深研 Dify/Coze, 再对照 aiPlat, 找出差距与优势

---

## 目录

1. [Dify 深度分析](#1-dify-深度分析)
2. [Coze 深度分析](#2-coze-深度分析)
3. [aiPlat 深度分析](#3-aiplat-深度分析)
4. [系统架构深度对比](#4-系统架构深度对比) ← 🆕
5. [三方圆桌对比 (功能维度)](#5-三方圆桌对比-功能维度)
6. [aiPlat 差距清单](#6-aiplat-差距清单)
7. [aiPlat 独有优势](#7-aiplat-独有优势)
8. [改进路线：差距→方案→优先级](#8-改进路线差距方案优先级)
9. [逐项采纳分析 (34项)](#9-逐项采纳分析)
10. [对比表逐项采纳分析 (48点)](#10-对比表逐项采纳分析)
11. [遗漏补充：节点与变量全覆盖](#11-遗漏补充节点与变量系统全覆盖分析)

---

## 1. Dify 深度分析

### 1.1 架构全景

```
┌────────────────────────────────┐
│  Next.js 前端 (React + Zustand) │  ← 画布编辑器, 50+ workflow 文件
├────────────────────────────────┤
│  Flask API (Gunicorn + gevent)  │  ← REST + SSE streaming
├────────────────────────────────┤
│  Celery Worker (Redis broker)   │  ← 异步任务: 工作流执行/索引/邮件
├────────────────────────────────┤
│  PostgreSQL  │  Redis  │  Weaviate/Qdrant  │  ← 状态/缓存/向量
├────────────────────────────────┤
│  Docker Sandbox  │  SSRF Proxy  │  Plugin Daemon  │  ← 安全隔离层
└────────────────────────────────┘
```

**关键设计决策**:
- **Celery 作为执行引擎**: 工作流不是即时执行, 而是作为 Celery 任务入队。支持自动扩缩容 (`CELERY_AUTO_SCALE`)。
- **Flask 非 FastAPI**: 历史选择, 但 SSE streaming 通过 gevent 协程实现。
- **Plugin Daemon**: 独立的 Docker 容器运行插件, 实现进程级隔离。
- **DSL 驱动**: 所有工作流存储为 YAML DSL, 可导出/导入/版本管理。

### 1.2 节点系统 (21 种)

| 类别 | 节点 | 核心能力 |
|------|------|---------|
| **AI** | LLM | 100+ 模型, Jinja2 模板, 结构化输出 (JSON Schema), 视觉, 记忆窗口 |
| **AI** | Agent | Function Calling / ReAct 策略, 工具绑定 |
| **AI** | 知识检索 | 多模态 RAG, 重排序, 元数据过滤, 分层召回 |
| **AI** | 问题分类器 | 基于 LLM 的分类路由 |
| **AI** | 参数提取器 | 从自然语言提取结构化参数 |
| **逻辑** | If-Else | 多条件 (AND/OR), 多分支 (IF→ELIF→ELSE), 条件操作符丰富 |
| **逻辑** | 迭代 | 数组遍历, 顺序/并行模式, 最大10并发, 三种错误策略 |
| **逻辑** | 循环 | 条件循环, 直到满足终止条件 |
| **数据** | Code | Python/JS, Docker 沙箱隔离, 预装 numpy/pandas/requests |
| **数据** | Template | Jinja2 模板引擎, 支持 `{{var}}` 深度对象访问 |
| **数据** | Variable Assigner | 会话变量赋值, 跨轮次持久化 |
| **数据** | Variable Aggregator | 多分支输出聚合 |
| **集成** | HTTP | 6 种方法, 4 种认证, SSL 配置, 超时分段控制 |
| **集成** | Tool | 自定义工具 (通过插件) |
| **集成** | 文档提取器 | 从文件提取文本 |
| **流程** | Start/End | 输入定义 + 输出定义 |
| **交互** | Human Input | 人工输入节点, 暂停等待 |
| **工具** | List Operator | 列表过滤/排序/切片 |

### 1.3 变量系统

```
输入变量 (Start 节点定义, 不可变)
  ├── sys.user_id / sys.app_id / sys.workflow_id / sys.workflow_run_id
  ├── sys.conversation_id / sys.dialogue_count (Chatflow)
  └── 环境变量 (每个应用独立, DSL 导出时剥离)

节点输出变量 (每个节点自动暴露)
  ├── 通过下拉选择器引用
  ├── 支持深度对象访问: {{api_response.data.items[0].id}}
  └── / 斜杠快捷插入

对话变量 (仅 Chatflow)
  └── 跨多轮持久化, Variable Assigner 节点更新
```

### 1.4 扩展机制

| 机制 | 实现 |
|------|------|
| **插件系统** | 独立 Plugin Daemon Docker 容器, 插件类型: 模型提供商/工具/Agent策略/触发器/数据源 |
| **插件开发** | CLI 工具 `dify-plugin`, 本地构建→远程调试→打包 `.difypkg` |
| **插件市场** | GitHub PR + 审核, 支持第三方签名验证 |
| **API 暴露** | Service API (`/v1/workflows/run`), SSE 流式, Webhook, MCP Server |
| **DSL 导出** | YAML 格式, 跨实例导入导出, 版本控制 (草稿→发布→历史) |
| **SDK** | 无官方多语言 SDK, 依赖 REST API 直接调用 |

### 1.5 生产特性

| 能力 | 实现 |
|------|------|
| **部署** | Docker Compose (单机) / K8s (Helm/社区) / Terraform / 阿里云计算巢 |
| **监控** | 内置仪表板 (消息/用户/token), Langfuse/LangSmith 等外部追踪集成 |
| **日志** | 节点级执行日志 (输入/输出/耗时), 可视化执行图, 保留策略可配 |
| **协作** | WebSocket 实时协作编辑, 评论+@提及, 多光标 |
| **安全** | Docker 沙箱 (Code 节点), SSRF 代理, JWT 认证, OAuth, RBAC (Owner/Admin/Editor/Member) |
| **版本** | 内置版本控制 (发布/回滚/历史) |

### 1.6 独特优势

1. **最丰富的节点类型**: 21 种 vs Coze 15+ vs aiPlat 15
2. **成熟的插件生态**: 插件市场 + Plugin Daemon + 标准化打包
3. **Jinja2 模板**: 深度对象访问 `{{a.b.c[0].d}}`
4. **实时协作**: WebSocket 多人编辑
5. **最完善的文档**: 中文/英文双语文档, llms.txt 索引
6. **DSL 标准化**: YAML 格式工作流可跨实例移植

---

## 2. Coze 深度分析

### 2.1 架构全景

```
┌──────────────────────────────────────┐
│ 前端: React + TypeScript             │
│ ├── FlowGram (画布引擎)               │  ← 字节自研, 自由/固定布局
│ ├── rspack (打包器)                   │  ← Rust 构建, 性能优于 Webpack
│ └── Semi Design (UI)                 │  ← 字节设计系统
├──────────────────────────────────────┤
│ 后端: Go 微服务 (Hertz HTTP 框架)      │  ← domain-driven design
│ ├── Eino (AI 引擎)                    │  ← Agent/Workflow 运行时
│ ├── Coze Loop (评测/可观测性)          │  ← 全链路 trace + 多维评测
│ └── 内置数据库 / Memory / Voice       │  ← 平台级能力
├──────────────────────────────────────┤
│ 部署: Docker Compose / K8s (Helm)     │
└──────────────────────────────────────┘
```

**关键设计决策**:
- **FlowGram + Eino 双引擎**: 前端画布(FrameGram)和后端执行(Eino)是独立的两套系统, 通过标准化协议通信。
- **Go 语言全栈后端**: 高并发低延迟, Hertz 基于 Netpoll (epoll/kqueue), 性能优于 Flask/Gunicorn。
- **DDD 微服务**: 按领域拆分服务, 非单体架构。
- **Monorepo 管理**: Rush.js + pnpm, 135+ 前端包。

### 2.2 节点系统 (15+ 种)

| 类别 | 节点 | 核心能力 |
|------|------|---------|
| **AI** | LLM | 多模型, Prompt 编辑器 (支持变量嵌入), 温度等参数 |
| **AI** | Knowledge/RAG | Eino Retriever 驱动, 文档上传→索引→检索 |
| **逻辑** | Condition | 基于变量值分支路由, 条件组合 |
| **逻辑** | Loop | 数组迭代, 自动推导 item/index 变量, 输出聚合 |
| **逻辑** | Batch | 批量处理, 并行/顺序 |
| **数据** | Code | Python Docker 沙箱, Code Editor 含变量嵌入 |
| **数据** | Variable/Assign | 变量声明/赋值, 作用域链, 类型推导 |
| **数据** | Database | SQL 查询, 数据库条件配置 |
| **集成** | HTTP | REST API 调用, JSON body, 变量嵌入 |
| **集成** | Plugin/Tool | 自定义插件, 插件商店 |
| **集成** | MCP | coze-mcp-server, 暴露为 MCP 工具 |
| **流程** | Start/End | 入参 JSON Schema 校验, 出参定义 |
| **流程** | Input/Output | JSON Schema 编辑器, 类型管理 |

### 2.3 Eino 引擎 (Go)

```
ChatModel (LLM 抽象)
  └── 官方实现: OpenAI, Ollama, Claude, Gemini, Volcengine Ark

Tool (工具抽象)
  └── 任何函数可注册为 Tool

Retriever (检索抽象)
  └── Elasticsearch 等实现

Agent (ADK)
  ├── ChatModelAgent: Model + Tools = 完整 Agent (内置 ReAct)
  ├── DeepAgent: 拆解复杂任务, 委派子 Agent
  └── 多 Agent 协调 + 上下文管理

Composition (编排)
  ├── compose.NewGraph() 构建 Graph/Workflow
  ├── GraphTool: 组合工作流暴露为 Agent 工具
  ├── 自动流式处理 (拼接/装箱/合并/拷贝)
  └── 中断/恢复 (Human-in-the-Loop)
```

### 2.4 FlowGram 画布引擎

```
自由布局画布: 节点任意放置, 灵活连线
固定布局画布: 支持复合节点 (分支/循环容器)

Form 引擎: 节点数据 CRUD + 渲染 + 校验 + 副作用 + 联动 + 错误捕获
  └── 底层: Semi Design 组件库

Variable 引擎: 作用域约束, 变量结构检查, 类型推导
  └── 循环内 item/index 推导, 输出变量作用域链调整

Runtime: 运行时执行抽象
```

### 2.5 变量系统

```
作用域链管理:
  ├── 全局变量
  ├── 节点级变量
  └── 循环作用域: item / index 自动推导

类型推导:
  └── Variable 引擎自动推断变量类型

跨节点引用:
  └── 变量选择器 UI, 链式引用
```

### 2.6 扩展机制

| 机制 | 实现 |
|------|------|
| **插件** | 自定义工具创建/管理, API 密钥验证, 发布到商店 |
| **MCP** | coze-mcp-server, 暴露 Coze 能力给 Claude/Zed 等客户端 |
| **SDK** | JS/TS, Go, Python, Java, Kotlin KMP, iOS, Android, C — 8 种语言 |
| **Open API** | 完整 REST API: Chat/Workflow/Bot/Dataset/Conversation/File/Voice |
| **WebSocket** | Realtime API: chat/speech(TTS)/transcriptions(STT) |
| **OAuth** | PAT, OAuth Web App, PKCE, JWT, Device Code Flow |

### 2.7 生产特性

| 能力 | 实现 |
|------|------|
| **部署** | Docker Compose / K8s (Helm), 纯云端 + 开源社区版可自托管 |
| **监控** | Coze Loop: 全链路 trace (用户输入→提示词→模型→工具→输出), 自动捕获中间结果 |
| **评测** | Coze Loop: 多维自动评测 (准确度/简洁度/合规度), 评测集管理, 实验管理 |
| **版本** | Bot/Workflow 的 commit 版本 + 发布版本 + 灰度发布 + PPE 预发布环境 |
| **安全** | 企业私有网络, OAuth 2.0, PAT 细粒度权限, SSO |
| **协作** | 企业版: 组织管理/成员管理/SSO/空间隔离 |

### 2.8 独特优势

1. **FlowGram + Eino 双引擎**: 前端画布和后端执行都是自研, 集成度最高
2. **Go 全栈**: 高并发低延迟, 企业级性能
3. **Coze Loop**: 独立的全生命周期 AI Agent 平台 (开发→调试→评测→监控)
4. **8 语言 SDK**: 最广泛的多语言覆盖
5. **WebSocket Realtime API**: chat/speech/transcriptions 实时通信
6. **UI Builder**: 可视化构建 Bot 前端界面
7. **移动端**: Taro/UniApp/iOS/Android/KMP 多平台
8. **Monorepo 架构**: 135+ 前端包的极致模块化

---

## 3. aiPlat 深度分析

### 3.1 架构全景

```
┌────────────────────────────────────┐
│ 前端: Vite + React (useState)       │  ← 1 文件 ~500 行画布
├────────────────────────────────────┤
│ 后端: Python FastAPI (单进程)        │  ← 单体应用
│ ├── Pipeline Engine                 │  ← 流水线编排 + HITL + Git
│ ├── Harness (ReActLoop)             │  ← Agent 运行时内核
│ ├── Memory (3层)                    │  ← Working/Episodic/Semantic
│ ├── Hook System (17 phases)         │  ← 事件驱动扩展
│ ├── Skill Registry (24 built-in)    │  ← 可复用能力单元
│ └── Tool Registry (10+ built-in)    │  ← 原子操作
├────────────────────────────────────┤
│ 存储: JSON 文件 + SQLite + 环境变量  │
└────────────────────────────────────┘
```

### 3.2 节点系统 (15 种)

| 节点 | 执行机制 | syscall 通道 | 沙箱 |
|------|---------|-------------|:--:|
| Agent | StageRunner → ReActLoop | ✅ (sys_llm_generate/tool_call/skill_call) | 可选 |
| LLM | sys_llm_generate 单轮 | ✅ (通过安全网关) | ❌ |
| Code | subprocess.run | ❌ (绕过syscall) | timeout=30 |
| HTTP | urllib.request | ❌ (绕过syscall) | timeout=15 |
| Condition | eval(expr) 空builtins | ❌ | 受限 |
| Knowledge | KnowledgeManager.search | ❌ (绕过syscall) | ❌ |
| Tool | sys_tool_call | ✅ (PolicyGate+ApprovalGate) | 依赖工具 |

### 3.3 执行引擎

```
ReAct 循环 (Reason→Act→Observe)
  ├── 17 个 Hook 生命周期阶段
  ├── DONE/FINAL 自动终止检测
  ├── "Not found" 连续检测 (3次后自动终止)
  └── Pause on syscall (HITL)

崩溃恢复:
  ├── 双写检查点: 内存 (50条) + 磁盘 (JSON)
  └── Wake recovery: 从最后健康检查点自动恢复

失败降级 (3 策略):
  ├── fail_pipeline: 停止
  ├── skip_stage: 跳过继续
  └── use_fallback_result: 使用备用输出

Token 预算:
  ├── 5 级压缩 (70%→99%)
  ├── 模型降级 (简单任务自动换低成本模型)
  └── Artifact 截断 (可配置字符预算)

Git 闭环:
  ├── auto-commit per stage
  ├── rollback on test fail
  └── deploy tag 自动创建
```

### 3.4 扩展机制

| 机制 | 成本 | 规模 |
|------|------|------|
| **Hook** (17 phases) | 0 token | 7 内置 + 用户可扩展 |
| **Skill** (24 built-in) | 低 token | 纯 prompt + Python handler + Tool-capable |
| **Tool** (10+ types) | 中 token | PolicyGate + ApprovalGate 双门禁 |
| **MCP** (3 transports) | 高 token | stdio/HTTP/WebSocket, 生产环境 stdio 默认禁用 |
| **AGENT.md** | 0 token (永不压缩) | 每次 LLM 调用从磁盘重读 |
| **Template** | — | CRUD API + 版本号自增 |

### 3.5 独有优势

1. **HITL + 崩溃恢复**: 暂停→修改→恢复, 从健康检查点自动回退 — Dify/Coze 均无
2. **Git 闭环**: 每阶段 auto-commit + 测试失败 rollback — Dify/Coze 均无
3. **3 层记忆**: Working/Episodic/Semantic, 跨 session 学习 — Dify/Coze 均无
4. **5 级 Token 压缩**: 70%正常→99%紧急, 反抖动 — Dify/Coze 均无此粒度
5. **CLAUDE.md**: 永不压缩的项目规则 — Dify/Coze 均无
6. **Self-improvement**: Meta-optimization + Skill 结晶化 — Dify/Coze 均无
7. **1 文件 500 行**: 极限代码简洁 — Dify 50+ 文件, Coze 30+ 文件

---

## 4. 系统架构深度对比

> 从请求链路、组件耦合、数据架构、部署架构、安全架构五个子维度, 横向解剖三方的架构设计。

---

### 4.1 请求链路：一次工作流执行的全路径

#### Dify: 用户 → API → Celery 任务队列 → Worker 执行

```
用户请求 (SSE stream)
  ↓
Flask API (Gunicorn + gevent)
  ↓ 写入执行记录到 PostgreSQL
  ↓ 入队 Celery 任务 (Redis broker)
  ↓
Celery Worker (独立进程, 可多实例)
  ├── 读取 DSL (PostgreSQL)
  ├── 按拓扑排序执行节点
  │   ├── LLM 节点 → 调模型 API (通过插件)
  │   ├── Code 节点 → Docker Sandbox 子进程
  │   ├── HTTP 节点 → 经 ssrf_proxy 转发
  │   └── Knowledge 节点 → 查 Weaviate/Qdrant
  ├── 每节点完成后写日志 (PostgreSQL)
  └── 完成后标记 run status
  ↓
API 通过 SSE 推送进度给前端
```

| 特点 | 影响 |
|------|------|
| **异步执行模型** | 工作流不是即时执行, 有入队延迟。好处是可扩展 (多 Worker), 坏处是调试困难 |
| **Redis 作为中间件** | 引入 Redis 依赖。如果 Redis 挂, 所有异步任务丢失 |
| **状态全在 PostgreSQL** | 单点真理。崩溃恢复靠 PG 的持久性 |
| **SSE 进度推送** | 实时性好, 但需要 gevent 协程支持 |

#### Coze: 用户 → Go Hertz API → Eino Graph 执行

```
用户请求 (REST / WebSocket)
  ↓
Go Hertz API (Netpoll epoll/kqueue, 高并发)
  ↓ 解析工作流定义 (DSL/DB)
  ↓ 构建 Eino compose.Graph
  ↓
Eino 运行时 (同进程 goroutine)
  ├── 按 Graph 拓扑执行节点
  │   ├── LLM 节点 → 调模型 API (ChatModel 抽象)
  │   ├── Code 节点 → Docker Sandbox
  │   ├── HTTP 节点 → HTTP client
  │   └── Knowledge 节点 → Retriever 抽象
  ├── 自动流式处理 (拼接/装箱/合并/拷贝)
  ├── 中断/恢复 (HITL 支持)
  └── 每步触发 Callback (OnStart/OnEnd/OnError/OnStream)
  ↓
Coze Loop 采集全链路 trace (独立平台)
  ↓
结果返回 (流式 SSE 或 WebSocket)
```

| 特点 | 影响 |
|------|------|
| **同进程 goroutine 执行** | 无任务队列, 无 Redis 依赖。Go 的 goroutine 天然高并发 |
| **Eino Graph 抽象** | 工作流是 Graph 对象, 非 DSL 文本。类型安全, 编译期检查 |
| **Callback 切面** | 每个生命周期点可注入逻辑 (日志/追踪/指标), 非侵入式 |
| **Coze Loop 分离** | 可观测性是独立平台, 不嵌入运行时。好处是独立演进, 坏处是多一个依赖 |

#### aiPlat: 用户 → FastAPI → PipelineEngine 同步执行

```
用户请求 (REST)
  ↓
FastAPI (uvicorn, 单进程 asyncio)
  ↓ 构建 PipelineConfig (从 AGENT.md 或 API 参数)
  ↓ 创建 PipelineEngine 实例
  ↓
PipelineEngine (同步执行, 同进程)
  ├── initialize(): 创建 state, 加载 checkpoints
  ├── execute():
  │   └── _exec_single_stage() 逐阶段:
  │       ├── Agent 节点 → StageRunner → ReActLoop → sys_llm_generate
  │       ├── LLM 节点 → sys_llm_generate (经 Trace/Context/Resilience Gate)
  │       ├── Code 节点 → subprocess.run (绕过 syscall ⚠)
  │       ├── HTTP 节点 → urllib.request (绕过 syscall ⚠)
  │       ├── Condition 节点 → eval(expr)
  │       ├── Knowledge 节点 → KnowledgeManager.search (绕过 syscall ⚠)
  │       └── Tool 节点 → sys_tool_call (PolicyGate + ApprovalGate)
  │   ├── 每阶段: _snapshot() 双写检查点(内存+磁盘)
  │   ├── 每阶段: _git_commit_stage() (若启用)
  │   ├── HITL 时: pause → 等待 approve/reject → wake recovery
  │   └── 错误时: failure_strategy (fail/skip/fallback)
  └── 完成后: 返回结果 + graph_trace + HealthReport
  ↓
前端 2s 轮询 getState() 获取进度
```

| 特点 | 影响 |
|------|------|
| **同步单进程执行** | 无任务队列/无 Redis/无 Docker。部署极简, 调试可在断点中跟踪完整执行路径 |
| **无第三方中间件依赖** | 仅需 FastAPI + SQLite。适合离线/内网/安全敏感环境 |
| **双写检查点** | 崩溃恢复不依赖外部数据库, 内存+文件系统双保险 |
| **部分节点绕过 syscall** | Code/HTTP/Knowledge 直连执行, 无 trace_id/审计。已知短板, §9.5-30 采纳修复 |
| **轮询式进度** | 非 SSE/WebSocket 推送。前端每 2s 拉一次, 有延迟但实现简单 |

#### 请求链路三方圆桌

| 维度 | Dify | Coze | aiPlat |
|------|------|------|--------|
| 执行模式 | 异步 (Celery 任务队列) | 同步 (Go goroutine) | 同步 (同进程函数调用) |
| 入队延迟 | 有 (Redis queue) | 无 | 无 |
| 中间件依赖 | Redis + PostgreSQL | 无 (Go channel) | **无** |
| 进度推送 | SSE (gevent) | SSE / WebSocket | 轮询 (2s interval) |
| 崩溃恢复 | PG 事务回滚 | Go panic recover | **双写检查点 + wake recovery** |
| 调试体验 | 困难 (跨进程 trace) | 中等 (单进程 goroutine) | **简单** (同进程断点) |

---

### 4.2 组件耦合度

```
Dify:                 Coze:                 aiPlat:
┌──────┐             ┌──────┐              ┌──────────────┐
│ Web  │             │ Web  │              │  前端 (Vite  │
│(Next)│             │(React│              │  + React)    │
├──────┤             │ +rsp)│              ├──────────────┤
│ API  │             ├──────┤              │   FastAPI    │
│(Flask)             │ API  │              │  (monolith)  │
├──────┤             │(Go)  │              │              │
│Worker│             ├──────┤              │ ┌──────────┐ │
│(Cele)│             │Loop  │              │ │Pipeline   │ │
├──────┤             │(独立)│              │ │Engine     │ │
│Plugin│             ├──────┤              │ ├──────────┤ │
│Daemon│             │ 8    │              │ │ReActLoop  │ │
└──────┘             │ SDKs │              │ ├──────────┤ │
 6 进程              └──────┘              │ │Memory Mgr│ │
                     1+N 进程             │ ├──────────┤ │
                                          │ │Hook Sys  │ │
                                          │ └──────────┘ │
                                          └──────────────┘
                                           1 进程(生产)
                                           2 进程(开发:Vite+FastAPI)
```

| 维度 | Dify | Coze | aiPlat |
|------|------|------|--------|
| **进程数** | 6 (API+Worker+Web+Plugin+DB+Redis) | 1-N (API + 可选 Loop + 可选 DB) | **1** (生产) / 2 (开发: Vite+FastAPI) |
| **跨组件通信** | Redis 消息队列 | Go channel / gRPC | 函数调用 (同进程) + HTTP (dev Vite proxy) |
| **耦合风险** | API↔Worker 通过 Redis 松耦合, 但 Redis 是单点 | API↔Eino 通过 Go 接口松耦合 | 全耦合, 改一处影响全局 |
| **扩展方式** | 加 Worker 实例 (水平扩展) | 加 API 实例 (无状态) | 加 uvicorn worker (有限) |
| **部署复杂度** | 高 (6 容器) | 中 (2-3 容器) | **极低** (1 进程) |

---

### 4.3 数据架构

| 维度 | Dify | Coze | aiPlat |
|------|------|------|--------|
| **主数据库** | PostgreSQL (全状态) | MySQL/PostgreSQL (取决于部署) | **SQLite + JSON 文件** |
| **缓存/队列** | Redis | 无 (Go channel) | **无** |
| **向量数据库** | Weaviate / Qdrant / 等 | Elasticsearch / Milvus | **SQLite** (FTS5 全文检索) |
| **文件存储** | OpenDAL (S3/Azure/GCS/本地) | OSS / 本地 | **本地文件系统** (`~/.aiplat/`) |
| **状态持久化** | PG 事务 + Celery result backend | DB 事务 | **JSON 文件原子写入** (`.tmp` → `os.replace`) |
| **工作流定义** | YAML DSL (存 PG) | 内部格式 (存 DB) | **JSON 文件** (`~/.aiplat/workflow_templates/`) |
| **配置驱动** | 环境变量 + DB 配置表 | 环境变量 + DB | **环境变量 100% 驱动 + AGENT.md frontmatter** |

| 分析 | 结论 |
|------|------|
| **Dify 数据架构最"企业级"** | 但依赖 3 个外部服务 (PG+Redis+向量DB)。部署重, 运维成本高 |
| **Coze 数据架构最"平衡"** | Go 的高效内存管理减少了对 Redis 的依赖。但生产仍需 PG/MySQL |
| **aiPlat 数据架构最"轻量"** | SQLite+JSON 无外部依赖。适合嵌入式/边缘/单机。但缺少向量检索能力是硬伤 |

---

### 4.4 部署架构

| 维度 | Dify | Coze | aiPlat |
|------|------|------|--------|
| **最小部署** | `docker compose up` (6 容器, ~2GB 内存) | `docker compose up` (3 容器, ~1GB) | **`python -m aiplat`** (0 容器, ~200MB) |
| **水平扩展** | 加 Celery Worker / API 实例 | 加 API 实例 (无状态) | 加 uvicorn workers (有限, 受 GIL 约束) |
| **K8s 支持** | ✅ Helm + 社区 Chart | ✅ Helm | ❌ (单进程不适合 K8s) |
| **离线部署** | 困难 (需拉 Docker 镜像) | 困难 | **简单** (pip install + 本地文件) |
| **配置管理** | 环境变量 + Web UI | 环境变量 + Web UI | **环境变量 + AGENT.md 文件** |

---

### 4.5 安全架构

```
Dify 安全边界:           Coze 安全边界:            aiPlat 安全边界:
┌──────────────┐       ┌──────────────┐         ┌──────────────────┐
│ JWT (API)    │       │ OAuth 2.0    │         │ 注入检测 (6 patterns)│
├──────────────┤       │ PAT / JWT    │         │ 特殊 token 过滤    │
│ RBAC (4角色) │       │ SSO (企业版) │         │ 角色归一化         │
├──────────────┤       ├──────────────┤         ├──────────────────┤
│ Docker 沙箱  │       │ Eino 超时    │         │ PolicyGate (RBAC)  │
│ SSRF Proxy   │       │ + 重试       │         │ ApprovalGate (采样) │
├──────────────┤       ├──────────────┤         │ TraceGate (trace_id) │
│ 环境变量剥离 │       │ 企业私有网络 │         │ ContextGate (上下文)│
│ (DSL 导出)   │       │ 加密管理     │         │ ResilienceGate(超时)│
└──────────────┘       └──────────────┘         ├──────────────────┤
                                                 │ 沙箱 (进程/Docker) │
                                                 │ API key 剥离      │
                                                 │ 审计日志 (每次call)│
                                                 └──────────────────┘
```

| 维度 | Dify | Coze | aiPlat |
|------|:--:|:--:|:--:|
| 纵深层数 | 3 (JWT/RBAC/沙箱) | 3 (OAuth/PAT/私有网络) | **6** (注入检测→RBAC→双Gate→沙箱→审计) |
| 代码执行隔离 | ✅ Docker | ✅ Docker | ⚠️ subprocess (Docker 可选) |
| 网络隔离 | ✅ SSRF Proxy | ✅ 私有网络 | ❌ (直连, §9.5-30 采纳修复) |
| 密钥管理 | ✅ 环境变量 (DSL剥离) | ✅ 加密管理 | ⚠️ 环境变量 (无 DSL 级别隔离) |
| 审计日志 | ⚠️ 运行历史 (功能级) | ✅ Coze Loop (全链路) | ✅ 每次 syscall 记录 trace_id+span_id+duration_ms |
| 注入防护 | ❌ | ❌ | ✅ 6 种模式 + RuntimeError 拒绝 |

---

### 4.6 架构哲学总结

```
Dify  = "企业级全栈平台" 
        多服务 → 水平扩展 → 插件市场 → 社区生态
        适合: 团队协作, 需要完整开箱体验

Coze  = "工程化高性能平台"
        Go 微服务 → FlowGram+Eino 双引擎 → DDD → 8 SDK
        适合: 高并发场景, 云原生部署, 需要多语言集成

aiPlat = "安全深度优先的单体内核"
         1进程 → 配置驱动 → 6层安全 → Git闭环 → Self-improvement
        适合: 安全敏感, 离线部署, 深度定制 Agent 行为
```

### 4.7 架构维度汇总圆桌

| 维度 | Dify | Coze | aiPlat | 领先方 |
|------|------|------|--------|:--:|
| **执行模式** | 异步 (Celery+Redis) | 同步 (Go goroutine) | 同步 (Python asyncio) | Coze |
| **进程数** | 6+ | 1-3 | **1** (生产) | aiPlat |
| **中间件依赖** | PG + Redis + 向量DB | PG/MySQL (可选) | **SQLite + JSON (0依赖)** | aiPlat |
| **崩溃恢复** | PG 事务回滚 | Go panic recover | **双写检查点 + wake recovery** | aiPlat |
| **水平扩展** | ✅ 多 Worker | ✅ 多 API 实例 | ⚠️ uvicorn workers (有限) | Dify/Coze |
| **部署复杂度** | 高 (6容器, ~2GB) | 中 (2-3容器, ~1GB) | **极低** (0容器, ~200MB) | aiPlat |
| **离线部署** | 困难 | 困难 | **简单** | aiPlat |
| **安全纵深** | 3 层 | 3 层 | **6 层** | aiPlat |
| **可观测性** | Langfuse 等外部 | **Coze Loop (独立平台)** | trace_id + graph_trace | Coze |
| **向量检索** | ✅ Weaviate/Qdrant | ✅ ES/Milvus | ⚠️ SQLite FTS5 (无向量) | Dify/Coze |
| **代码执行隔离** | ✅ Docker | ✅ Docker | ✅ subprocess(CPU/Mem/Proc限制) + Docker可选 | — |
| **网络隔离** | ✅ SSRF Proxy | ✅ 私有网络 | ✅ HTTP_PROXY + aiohttp trust_env | — |
| **配置驱动深度** | 环境变量 + DB | 环境变量 + DB | **环境变量 + AGENT.md frontmatter (27+字段)** | aiPlat |
| **自优化能力** | ❌ | ❌ | ✅ Meta-optimization + Skill结晶化 | aiPlat |
| **Git 集成** | ❌ | ❌ | ✅ auto-commit + rollback | aiPlat |

### 4.8 架构落后项的逐项采纳分析

> 对上表中 aiPlat 落后于 Dify/Coze 的 8 个维度, 逐一给出是否采纳的判决。

---

#### 1. 执行模式 (同步 vs 异步) → ❌ 不采纳

| 维度 | 判 | 理由 |
|------|:--:|------|
| 改成异步 (Celery/Redis) | ❌ | 引入 Redis + Celery Worker 与"0依赖单进程"定位冲突。当前 Python asyncio 已支持并发请求。长工作流通过 2s 轮询获取进度对当前场景足够 |
| Go 语言重写 | ❌ | 全栈重写成本不可接受。Python 生态 (Jinja2/LangChain/transformers) 是 aiPlat 的核心依赖 |

#### 2. 水平扩展 (多 Worker) → ⚠️ 暂缓

| 维度 | 判 | 理由 |
|------|:--:|------|
| 多 Worker 并行 | ⚠️ | 当前单进程已够用 (大部分场景是串行流水线)。当用户反馈"一个流水线太慢"时再考虑 `uvicorn --workers N` 或 `gunicorn + uvicorn workers`。短期不追 Celery 模式 |

#### 3. 可观测性 → ✅ 采纳 (但分步)

| 维度 | 判 | 理由 |
|------|:--:|------|
| 追 Coze Loop (独立平台) | ❌ | 独立可观测性平台是另一个产品, 不在画布范围内 |
| 追 Dify (Langfuse 集成) | ✅ | 将 `_graph_trace` 导出为 OpenTelemetry 格式 → 接入 Langfuse/LangSmith。成本 ~150 行 Python (OTLP exporter), 前端 `npx @langfuse/openai` 已有现成方案 |
| 前端执行可视化 | ✅ | 已在 §9.5-28 采纳: graph_trace 前端卡片展示 per-node 输入/输出/耗时 |

**为什么采纳**: 可观测性是生产环境刚需。当前 trace_id + graph_trace 有数据, 缺展示和外部集成。补这两项即可追平 Dify 50% 的可观测性, 不追 Coze Loop 的 100%。

#### 4. 向量检索 → ⚠️ 暂缓 (但开放接口)

| 维度 | 判 | 理由 |
|------|:--:|------|
| 嵌入 Chroma/Milvus | ⚠️ | 引入外部向量数据库破坏"0依赖"定位。当前 SQLite FTS5 对关键词检索足够, 大部分 RAG 场景的召回瓶颈不在这里 |
| 向量检索接口 | ✅ | 在 Knowledge 节点/KnowledgeManager 中开放 `vector_search_provider` 接口, 用户可自行接入 `chromadb` / `lancedb` (嵌入式向量DB, 无服务端)。aiPlat 本身不捆绑任何向量数据库 |

**为什么暂缓**: 单机场景下 `lancedb` (Rust, 嵌入式, 零配置) 比 Milvus (需部署) 更适合 aiPlat 的定位。等用户需求明确后再决定默认捆绑哪个。

#### 5. 代码执行隔离 → ✅ 采纳 (但简化)

| 维度 | 判 | 理由 |
|------|:--:|------|
| Docker 沙箱 (默认) | ❌ | 强制 Docker 依赖破坏"单进程启动"体验 |
| Docker 沙箱 (可选) | ✅ | 已在前文 §9.2-10 采纳: 保留当前 subprocess 为默认, `sandbox_mode='docker'` 作为可选增强, 通过 `AIPLAT_SANDBOX_DOCKER_ENABLED` 开关 |
| subprocess 加固 | ✅ | 加 resource 限制 (memory/cpu/timeout/processes), 即使不用 Docker 也达到基本隔离 |

**为什么简化**: Docker 是"生产环境才需要"的能力, 不能成为默认依赖。开发/调试阶段 subprocess 足够, 部署时可选 Docker。

#### 6. 网络隔离 → ✅ 采纳

| 维度 | 判 | 理由 |
|------|:--:|------|
| SSRF 代理 | ✅ | 成本极低: 在 `pipeline_engine` 的 HTTP 路由中加 `HTTP_PROXY` 环境变量支持。用户可自行配置 Squid/Envoy 实例。aiPlat 本身不捆绑代理。核心: HTTP 节点不再直连, 而是走代理 |
| HTTP 节点改 syscall | ✅ | 已在 §9.5-30 采纳: HTTP 走 `sys_tool_call` → `HttpTool` → 通过 PolicyGate。syscall 通道天然支持代理配置 |

**为什么采纳**: 这是安全刚需, 且实现极简 (改 HTTP 节点路由 + 环境变量)。与 "0依赖" 定位不冲突 (代理是用户自己配置的外部服务)。

#### 7. 配置驱动深度 → ⬜ 不适用 (aiPlat 领先)

#### 8. 自优化能力 → ⬜ 不适用 (aiPlat 领先)

---

### 4.9 架构落后项裁决汇总

| 落后项 | 裁决 | 核心原因 |
|--------|:--:|---------|
| 执行模式 (同步) | ❌ 不采纳 | 0依赖定位, Python 够用 |
| 水平扩展 | ⚠️ 暂缓 | 当前够用, 按需加 uvicorn |
| **可观测性** | ✅ 采纳 | OTel 导出 + 前端可视化 |
| 向量检索 | ⚠️ 暂缓 | 开放接口, lancedb 可选 |
| **代码执行隔离** | ✅ 采纳(简化) | subprocess加固 + Docker可选 |
| **网络隔离** | ✅ 采纳 | SSRF代理 + HTTP走 syscall |
| 配置驱动 | ⬜ 领先 | 27+字段配置驱动 |
| 自优化 | ⬜ 领先 | Meta-optimization + Skill结晶化 |

---

## 5. 三方圆桌对比 (功能维度)

### 5.1 执行引擎

| 维度 | Dify | Coze | aiPlat | 优劣 |
|------|------|------|--------|------|
| 引擎架构 | Flask + Celery | Go Hertz + Eino | FastAPI + 自研 ReActLoop | Coze 性能最优; aiPlat 最简洁 |
| 工作流编排 | DSL-based, Celery 任务队列 | Eino compose.NewGraph() | PipelineEngine 编排 | Coze 编排最灵活; Dify 依赖任务队列 |
| Agent 模式 | Agent 节点 (FC/ReAct) | ChatModelAgent (ReAct内置) | ReActLoop (全手工控制) | Dify/Coze 配置式; aiPlat 可控性最强 |
| 循环/迭代 | ✅ 迭代+循环节点 | ✅ Loop 节点 + Batch | ❌ | **aiPlat 落后** |
| 条件分支 | IF→ELIF→ELSE (多条件) | 基于变量值分支 | eval(expr) 单条件 | Dify 最丰富 |
| 并行执行 | ✅ 同层并行 | ✅ 同层并行 | ✅ 同层并行 | 三方一致 |
| HITL | ❌ | ✅ (Eino 中断/恢复) | ✅ pause/resume + 崩溃恢复 | **aiPlat 领先** (独有崩溃恢复) |
| 错误处理 | 3 模式 (无/默认值/失败分支) | 节点级 | 3 策略 (fail/skip/fallback) + 连续失败检测 | 三方各有特色 |

### 5.2 节点丰富度

| 维度 | Dify | Coze | aiPlat | 优劣 |
|------|:--:|:--:|:--:|------|
| 节点总数 | **21** | **15+** | 10 | **aiPlat 差距缩小中** |
| AI 节点 | LLM, Agent, 知识检索, 分类器, 参数提取器 | LLM, Knowledge/RAG | Agent, LLM, Knowledge | Dify 最丰富 |
| 逻辑节点 | If-Else, 迭代, 循环 | Condition, Loop, Batch | Condition | **aiPlat 缺迭代/循环** |
| 数据节点 | Code, Template, Variable Assigner, Aggregator | Code, Variable/Assign, Database | Code, HTTP | **aiPlat 缺 Template/Assigner/Database** |
| 集成节点 | HTTP, Tool, 文档提取器 | HTTP, Plugin/Tool, MCP | HTTP, Tool | Dify/Coze 更丰富 |
| 交互节点 | Human Input, Answer | Start, End, Input/Output | ❌ | **aiPlat 缺 Human Input** |

### 5.3 变量系统

| 维度 | Dify | Coze | aiPlat | 优劣 |
|------|------|------|--------|------|
| 变量声明 | Start 节点定义 | Variable/Assign 节点 | 每节点 output_variables | 各有特色 |
| 类型系统 | ❌ 无类型标注 | ✅ 自动类型推导 | ✅ 手动 str/num/bool/obj/arr | Coze 最智能; aiPlat 最显式 |
| 引用语法 | `{{var}}` + 深度 `.` 访问 | 变量选择器 UI | `{{Node.var}}` + 点击插入 | Dify 深度访问最强 |
| 作用域 | 全局 + 节点 + 对话 | 全局 + 节点 + 循环(item/index) | BFS 层级树 (1-10层) | **aiPlat 作用域可视化最直观** |
| 系统变量 | ✅ 8种 | ✅ | ✅ 5种 | Dify 最全 |
| 环境变量 | ✅ 应用级 (DSL 剥离) | ✅ | ❌ | **aiPlat 缺环境变量隔离** |
| 模板引擎 | ✅ Jinja2 | ❌ | ❌ | **aiPlat 缺模板引擎** |

### 5.4 扩展与定制

| 维度 | Dify | Coze | aiPlat | 优劣 |
|------|------|------|--------|------|
| 插件/工具 | ✅ 插件市场 + Plugin Daemon | ✅ 插件商店 | ✅ Skill (24) + Tool (10+) | Dify 生态最大 |
| 自定义节点 | ❌ (需写插件) | ✅ FlowGram Material | ✅ 7种节点后端路由 | aiPlat 最易新增 |
| Hook 系统 | ❌ | ❌ | ✅ 17个生命周期钩子 | **aiPlat 独有** |
| MCP | ✅ (服务端) | ✅ (coze-mcp-server) | ✅ (3 transports) | 三方均有 |
| SDK | ❌ (REST only) | ✅ 8 语言 | ❌ (REST only) | **Coze 领先** |
| DSL/模板 | ✅ YAML DSL + 版本控制 | ✅ 版本管理 | ✅ JSON 模板 + 版本号 | Dify 最成熟 |
| AGENT.md | ❌ | ❌ | ✅ | **aiPlat 独有** |
| 记忆系统 | TokenBufferMemory | 用户级记忆 | 3层 (Working/Episodic/Semantic) | **aiPlat 最深** |

### 5.5 生产就绪度

| 维度 | Dify | Coze | aiPlat | 优劣 |
|------|------|------|--------|------|
| 部署复杂度 | Docker Compose / K8s | Docker Compose / K8s | 单进程 FastAPI | aiPlat 最简单 |
| 可观测性 | 内置仪表板 + Langfuse 等外部 | Coze Loop (全链路trace+评测) | trace_id + graph_trace + HealthReport | Coze Loop 最专业 |
| 日志 | 节点级执行日志 + 可视化 | Coze Loop 自动捕获 | graph_trace + 决策溯源 | Coze 最完整 |
| 协作 | ✅ WebSocket 实时编辑 + 评论 | ✅ 企业版 Space 隔离 | ❌ | **aiPlat 缺协作** |
| 版本管理 | ✅ 发布/回滚/历史 | ✅ commit/发布/灰度 | ⚠️ 模板版本号 | Dify/Coze 成熟 |
| 安全 | Docker 沙箱 + SSRF + JWT | OAuth 2.0 + PAT + SSO | 6层深度 (注入检测/RBAC/双Gate/沙盒/审计) | **aiPlat 安全最深** |
| CI/CD | ❌ | ❌ | ✅ Git auto-commit/rollback | **aiPlat 独有** |

### 5.6 综合评分

| 维度 | Dify | Coze | aiPlat |
|------|:--:|:--:|:--:|
| 节点丰富度 | ★★★★★ | ★★★★☆ | ★★★☆☆ |
| 执行引擎深度 | ★★★☆☆ | ★★★★☆ | ★★★★★ |
| 变量系统 | ★★★★★ | ★★★★☆ | ★★★★☆ |
| 扩展生态 | ★★★★★ | ★★★★☆ | ★★★★☆ |
| 生产就绪度 | ★★★★☆ | ★★★★★ | ★★★☆☆ |
| 代码简洁性 | ★★☆☆☆ | ★★★☆☆ | ★★★★★ |
| 安全深度 | ★★☆☆☆ | ★★★☆☆ | ★★★★★ |
| AI 记忆/学习 | ★★☆☆☆ | ★★★☆☆ | ★★★★★ |

---

## 6. aiPlat 差距清单

### 6.1 高优先级 (影响用户核心体验)

| # | 差距 | Dify | Coze | 建议 |
|---|------|:--:|:--:|------|
| 1 | **循环/迭代容器节点** | ✅ | ✅ | 新增 Loop/Iteration 容器节点, 支持数组遍历+输出聚合 |
| 2 | **Jinja2 模板引擎** | ✅ | ❌ | Prompt 字段支持 `{{var.deep.path}}` 模板语法 |
| 3 | **Template/Variable Assigner 节点** | ✅ | ✅ | 新增数据转换节点 |
| 4 | **Human Input 节点** | ✅ | ❌ | 新增人工输入节点, 支持暂停等待 |

### 6.2 中优先级 (提升竞争力)

| # | 差距 | Dify | Coze | 建议 |
|---|------|:--:|:--:|------|
| 5 | **WebSocket 实时协作** | ✅ | ✅ | 多人同时编辑画布 |
| 6 | **多条件 If-Else** (AND/OR, 多分支) | ✅ | ✅ | Condition 节点增强 |
| 7 | **环境变量隔离** | ✅ | ✅ | 每个应用/工作流独立的密钥变量 |
| 8 | **节点执行日志** (可视化) | ✅ | ✅ | 执行后可查看每节点详细输入/输出/耗时 |
| 9 | **多语言 SDK** | ❌ | ✅ | 至少 Go + Python SDK |
| 10 | **Code/HTTP 节点走 syscall 通道** | N/A | N/A | 补安全短板 |

### 6.3 低优先级 (锦上添花)

| # | 差距 | Dify | Coze | 建议 |
|---|------|:--:|:--:|------|
| 11 | 插件市场 | ✅ | ✅ | 开放社区贡献通道 |
| 12 | 发布为 API 端点 | ✅ | ✅ | 工作流发布后自动生成 REST API |
| 13 | 灰度发布 / PPE 预发布 | ❌ | ✅ | 版本灰度能力 |
| 14 | 移动端 SDK | ❌ | ✅ | 小程序/移动端支持 |

---

## 7. aiPlat 独有优势

### 7.1 不可替代的能力

| 优势 | Dify | Coze | aiPlat 实现 |
|------|:--:|:--:|------|
| **HITL + 崩溃恢复** | ❌ | 部分 | pause/resume/approve/reject + 从健康检查点自动回退 |
| **Git 闭环** | ❌ | ❌ | auto-commit per stage + rollback on test fail + deploy tag |
| **3 层记忆** (跨 session) | 单层 | 单层 | Working/Episodic/Semantic + SQLite FTS5 |
| **5 级 Token 压缩** (反抖动) | 无 | 无 | 70%→99% 逐级压缩, 保存历史防重复压缩 |
| **CLAUDE.md** (永不压缩规则) | ❌ | ❌ | 每次 LLM 调用从磁盘重读, 12KB 上限 |
| **Self-improvement** | ❌ | ❌ | Meta-optimization + Skill 结晶化 + AGENT.md 修补 |
| **6 层安全** | 3 层 | 3 层 | 注入检测/RBAC/PolicyGate/ApprovalGate/沙盒/审计 |
| **1 文件 500 行** | 50+ 文件 | 30+ 文件 | 极限代码简洁, 单文件可维护 |

### 7.2 差异化定位

```
Dify  = 最丰富的节点 + 最好的生态 + 最成熟的社区
Coze  = 最强的工程化 + 最广的 SDK + 最专业的评测
aiPlat = 最深的安全 + 最强的记忆 + 最完整的 Git/HITL 闭环
```

---

## 8. 改进路线：差距→方案→优先级

### 8.0 优先级评估矩阵

每项差距按 **影响 (Impact)** × **可行度 (Feasibility)** = **优先级** 评分 (1-5):

| 评分 | 含义 |
|:--:|------|
| 5 | 立即启动, 高影响+易实现 |
| 4 | 近期推进, 高影响或易实现 |
| 3 | 中期规划, 中等影响 |
| 2 | 远期目标, 需要前置依赖 |
| 1 | 观察等待, 成本高/影响低 |

---

### 8.1 节点系统增强 (当前最大短板: 7 vs Dify21 vs Coze15)

#### A. 新增节点类型

| # | 节点 | Dify | Coze | 影响 | 可行 | 优先级 | 方案 |
|---|------|:--:|:--:|:--:|:--:|:--:|------|
| 1 | **循环/迭代容器** | ✅ | ✅ | 5 | 3 | **4** | 自定义容器节点, 支持数组遍历(顺序/并行), 自动推导 item/index 变量, 输出聚合。前端：NodeResizer 扩展 + BatchVariableSelector UI。后端：pipeline_engine 新增 loop 路由, 子图递归执行 |
| 2 | **多条件 If-Else** | ✅ | ✅ | 4 | 4 | **4** | Condition 节点从 `eval(expr)` 升级为多条 AND/OR 规则链, 支持 ELIF 多分支, 每分支独立 Handle |
| 3 | **Variable Assigner** | ✅ | ✅ | 4 | 4 | **4** | 新增变量赋值节点, 支持修改上游变量的值, 用于数据清洗/格式转换 |
| 4 | **Template/Jinja2 转换** | ✅ | ❌ | 5 | 3 | **4** | 新增 Template 节点, 内置 Jinja2 渲染引擎, `{{var.deep.path}}` 深度对象访问 |
| 5 | **Human Input** | ✅ | ❌ | 3 | 4 | **3** | 新增人工输入节点, 暂停流水线等待用户填写表单, 复用已有 HITL 基础设施 |
| 6 | **Variable Aggregator** | ✅ | ✅ | 3 | 3 | **3** | 多分支输出聚合成单个列表/对象 |
| 7 | **Database/SQL** | ❌ | ✅ | 3 | 2 | **2** | SQL 查询节点, 需先建设数据库连接池基础设施 |
| 8 | **文档提取器** | ✅ | ❌ | 2 | 3 | **2** | 从 PDF/Word/Markdown 提取文本 |

#### B. 现有节点能力深化

| # | 节点 | 当前能力 | 目标能力 | 影响 | 可行 | 优先级 |
|---|------|---------|---------|:--:|:--:|:--:|
| 9 | **LLM** | prompt+model+temp+vision | +结构化输出(JSON Schema) +Jinja2模板 +记忆窗口 | 5 | 4 | **5** |
| 10 | **Code** | subprocess.run 单次执行 | +Docker沙箱隔离 +预装依赖(numpy/pandas) +文件/网络策略 | 4 | 3 | **3** |
| 11 | **HTTP** | urllib 直连 | +SSRF代理 +多种认证(Basic/Bearer/OAuth) +SSL配置 +文件上传 | 4 | 3 | **3** |
| 12 | **Knowledge** | KnowledgeManager.search | +重排序 +元数据过滤 +多模态检索 | 3 | 2 | **2** |
| 13 | **所有节点** | retry_count/timeout_sec 仅前端存 | 引擎侧真正读取 node_config.retry_count/timeout_sec 执行 | 5 | 5 | **5** |

---

### 8.2 变量系统现代化 (当前差距: Dify 深度访问 + Coze 自动推导)

| # | 差距 | Dify | Coze | 影响 | 可行 | 优先级 | 方案 |
|---|------|:--:|:--:|:--:|:--:|:--:|------|
| 14 | **Jinja2 模板引擎** | ✅ | ❌ | 5 | 4 | **5** | Prompt/Config 字段全面支持 `{{var.deep.path}}` 深度对象访问, 过滤器 `| upper`, 条件 `{% if %}` |
| 15 | **深度对象访问** | ✅ | ❌ | 5 | 4 | **5** | 变量引用从 `{{Node.var}}` 扩展到 `{{Node.var.field[0].sub}}` |
| 16 | **环境变量隔离** | ✅ | ✅ | 4 | 5 | **5** | 每工作流/应用独立的密钥环境变量, DSL 导出时自动剥离, 支持 OAuth 凭据加密 |
| 17 | **自动类型推导** | ❌ | ✅ | 3 | 3 | **3** | 从节点输出自动推断变量类型 (类似 Coze Variable 引擎), 减少手动标注 |
| 18 | **循环作用域变量** | ✅ | ✅ | 3 | 3 | **3** | 循环容器内自动推导 item/index 变量, 作用域链限定在循环体内 |
| 19 | **对话/会话变量** | ✅ | ❌ | 2 | 2 | **2** | Chatflow 模式下的跨轮次会话变量持久化 |
| 20 | **JSON Schema 输出校验** | ✅ | ✅ | 3 | 3 | **3** | 定义节点输出的 JSON Schema, 运行时自动校验结构 |

---

### 8.3 扩展生态系统建设 (当前差距: 无外部 SDK/插件市场/API 发布)

| # | 差距 | Dify | Coze | 影响 | 可行 | 优先级 | 方案 |
|---|------|:--:|:--:|:--:|:--:|:--:|------|
| 21 | **多语言 SDK** | ❌ | ✅(8种) | 4 | 3 | **4** | Phase1: Python SDK (pypi包, 覆盖 Workflow/Bot/Chat/Dataset API)。Phase2: Go/JS SDK |
| 22 | **插件/扩展 API** | ✅ | ✅ | 5 | 2 | **4** | 定义标准化插件接口: plugin.yaml → PluginLoader → 动态注册到 SkillRegistry/ToolRegistry。前端插件渲染沙箱 |
| 23 | **发布为 API 端点** | ✅ | ✅ | 4 | 3 | **4** | 工作流发布后自动生成 REST API (POST /v1/workflows/{id}/run), 含 API 密钥管理 |
| 24 | **插件市场/商店** | ✅ | ✅ | 3 | 1 | **2** | 社区贡献通道 (GitHub PR + 审核), 在线搜索/安装插件 |
| 25 | **MCP Server 暴露** | ✅ | ✅ | 3 | 4 | **3** | 将 aiPlat 能力通过 MCP 协议暴露给 Claude Desktop/Cursor/Zed |
| 26 | **Webhook 触发器** | ✅ | ✅ | 3 | 4 | **3** | 外部系统通过 Webhook URL 触发工作流执行 |

---

### 8.4 协作与生产特性 (当前差距: 无协作/弱日志/弱版本)

| # | 差距 | Dify | Coze | 影响 | 可行 | 优先级 | 方案 |
|---|------|:--:|:--:|:--:|:--:|:--:|------|
| 27 | **WebSocket 实时协作** | ✅ | ✅ | 4 | 2 | **3** | WebSocket 广播节点增删改事件, 多光标位置同步, 评论/批注 |
| 28 | **节点执行日志** | ✅ | ✅ | 4 | 4 | **4** | 执行后可视化 per-node 输入/输出/耗时/token/错误, 支持复制/导出 |
| 29 | **工作流版本管理** | ✅ | ✅ | 3 | 4 | **4** | 从"模板版本号"升级为完整版本历史(草稿→发布→回滚), 支持 release notes |
| 30 | **Code/HTTP/Knowledge 走 syscall** | N/A | N/A | 4 | 4 | **4** | Code→sys_tool_call(通过CodeExecutionTool), HTTP→sys_tool_call(通过HttpTool), Knowledge→sys_tool_call(通过KbTool)。统一走 Trace/Context/Resilience 三 Gate, 补齐 trace_id 和审计日志 |
| 31 | **RBAC 权限模型** | ✅ | ✅ | 3 | 3 | **3** | 工作流/项目级别的 Owner/Editor/Viewer 角色, 前端按角色显示操作按钮 |
| 32 | **灰度发布** | ❌ | ✅ | 2 | 1 | **1** | 多版本并行, 按流量比例路由 |
| 33 | **移动端支持** | 有限 | ✅ | 2 | 1 | **1** | 小程序/移动端画布查看器 (只读) |

---

### 8.5 按阶段汇总执行计划

#### Phase 1: 追平核心体验 (优先级 5 → 4 周)

```
节点系统: 循环容器 | 多条件 If-Else | Template(Jinja2) | Variable Assigner
          参数提取器 | 问题分类器 | 列表操作器
节点深化: LLM 结构化输出+Jinja2+记忆窗口 | retry/timeout 引擎侧执行 | HTTP超时分段
变量系统: Jinja2 模板引擎 | 深度对象访问 {{a.b[0].c}} | 环境变量隔离 | 变量默认值 | 文件类型变量
扩展生态: 发布为 API 端点 | Python SDK | Webhook触发器
安全补缺: Code/HTTP/Knowledge 走 syscall 通道
```

**验收标准**: 节点数 7→14, Prompt 支持 `{{var.path}}`, 工作流可通过 REST API 调用

#### Phase 2: 补短板 (优先级 4 → 4 周)

```
节点系统: Human Input | Variable Aggregator | Start(输入定义) | End(输出定义)
节点深化: Docker 沙箱(Code) | SSRF 代理+多认证(HTTP) | 错误分支(橙色线)
变量系统: JSON Schema 输出校验 | 循环作用域变量 | 运行时变量检查器 | 系统变量补全(workflow_id/run_id)
生产特性: 节点执行日志(可视化) | 工作流版本管理(Git) | 外部追踪集成(OpenTelemetry→Langfuse)
扩展生态: MCP Server 暴露 | 变量选择器UI(内联下拉)
架构补强: 可观测性(OTel导出) | 代码执行隔离(Docker可选) | 网络隔离(HTTP→syscall+代理)
```

**验收标准**: Code/HTTP 节点安全隔离, 执行日志可视化, 16 种节点, OTel 追踪可接入 Langfuse

#### Phase 3: 扩大生态 (优先级 3 → 4 周)

```
节点深化: 重排序+多模态(Knowledge)
变量系统: 变量值历史 | 变量值导出
生产特性: WebSocket 协作 | 对话变量
 扩展生态: 多语言 SDK (Go/JS) | RBAC
架构补强: 向量检索(lancedb可选接口) | 水平扩展(uvicorn workers)
```

**验收标准**: SDK 覆盖 Python/Go/JS, 多人可协作编辑, 向量检索可按需接入

#### 长期愿景 (优先级 1-2)

```
文档提取器 | 灰度发布 | 移动端 SDK | E2E 测试框架
```

---

### 8.6 各维度目标状态

| 维度 | 当前 | Phase1 | Phase2 | Phase3 |
|------|:--:|:--:|:--:|:--:|
| 节点类型数 | 10 | 14 | 16 | 16 |
| 变量访问深度 | 1层 | 任意层 | 任意层+校验 | 任意层+校验+推导 |
| SDK 语言数 | 0 | 1 (Python) | 1 | 3 (Python/Go/JS) |
| 安全审计覆盖 | 6/10 节点 | 10/10 节点 | 10/10 节点 | 10/10 节点 |
| 可观测性 | trace_id | trace_id | OTel+Langfuse | OTel+Langfuse |
| 代码隔离 | subprocess | subprocess | Docker可选 | Docker可选 |
| 网络隔离 | 直连 | syscall | SSRF代理 | SSRF代理 |
| 协作能力 | 无 | 无 | 无 | 实时协作 |
| 生态开放度 | 内部 | API 发布 | 插件 API | 插件 API + GitHub 仓库 |

---

## 9. 逐项采纳分析

> 每项按 aiPlat 的架构约束 (1文件画布/FastAPI单体/配置驱动引擎/安全深度优先) 独立判断。
> **采纳** = 应纳入路线图, **不采纳** = 与 aiPlat 定位冲突或成本远超收益。

---

### 9.1 节点系统 — 新增类型

#### 1. 循环/迭代容器 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, aiPlat 无。数组处理是工作流刚需 |
| **架构兼容** | 前端可扩展现有 NodeResizer 实现容器节点。后端 pipeline_engine 已有子图执行基础 (`_exec_single_stage` 可递归) |
| **不与现有优势冲突** | 不削弱 HITL/记忆/Git 任何能力 |
| **实现路径** | 前端: 容器节点(可拖入子节点) + BatchVariableSelector。后端: `node_type='loop'` 路由, 子 stages 数组递归执行, 自动推导 item/index 变量 |
| **风险** | 容器节点的前端交互复杂度较高, 需要突破当前 stageNode inline 渲染模式, 可能迫使画布拆分为多文件 |

#### 2. 多条件 If-Else → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | 当前 Condition 仅支持单 `eval(expr)`, Dify 支持 AND/OR 多条件+多 ELIF 分支 |
| **架构兼容** | 前端 Condition 已有 True/False 双 Handle, 扩展到第 3/第 N 个 Handle 是自然延伸 |
| **实现路径** | 前端: 条件规则列表 UI (field/op/value + AND/OR) → 每个分支独立 Handle。后端: `node_config.rules[]` 逐条求值 |

#### 3. Variable Assigner → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有。数据清洗/格式转换是常见工作流步骤 |
| **架构兼容** | 当前已有 output_variables 声明基础设施, Assigner 是其执行侧延伸: 声明式输入→转换→输出 |
| **实现路径** | 新增 `node_type='assigner'`, 配置 `assignments: [{target, expression}]`, 后端 eval 赋值 |

#### 4. Template/Jinja2 → ✅ 采纳 (但分步)

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 有, Coze 无, aiPlat 无。这是变量系统现代化的关键支撑 |
| **架构兼容** | Jinja2 (Python) 天然兼容。但完整 Template 节点需要在前端嵌入模板编辑器+实时预览 |
| **实现路径** | Phase 1: 先让 LLM/Agent 的 prompt 字段支持 `{{var.path}}` (Jinja2 引擎在 `_build_prompt` 中渲染)。Phase 3: 独立 Template 节点, 含可视化编辑器 |

#### 5. Human Input → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | aiPlat 已有更强大的 HITL 机制 (pause/resume/approve/reject), 不仅是简单输入, 而是完整的审批→修改→恢复闭环。Human Input 节点是"弱化版 HITL"——只收集输入不审批。重复建设 |
| **如果要做** | 复用现有 HITL 基础设施, Human Input 节点作为 `hitl_phase` 的特化模式, 前端渲染表单而非审批按钮 |
| **优先级** | 降低至 Phase 3, 等 HITL 使用反馈后再决定 |

#### 6. Variable Aggregator → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 功能可由循环容器(`output_aggregation`) + Assigner 节点组合实现。增设独立节点类型增加前端维护成本(每种新类型 ~50行 stageNode + ~30行 config + ~30行后端) |
| **如果要做** | 等循环容器+Assigner 落地后评估, 看用户是否需要独立 Aggregator |

#### 7. Database/SQL → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 需新建数据库连接池/凭证管理/连接加密/查询沙箱一整条基础设施链。aiPlat 当前无数据库层(状态全部 JSON文件+SQLite)。加上后与"单进程简洁部署"定位冲突 |
| **替代方案** | 通过 Tool 节点调用 `sys_tool_call` → 数据库查询 Tool(如已有 `skill_tools.py`), 不另建节点类型 |

#### 8. 文档提取器 → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | PDF/Word 解析依赖重型外部库 (PyMuPDF/pdfplumber/python-docx), 增加部署复杂度。功能可由 Knowledge 节点的 `kb_provider.py` 回调实现 |
| **替代方案** | 在 Knowledge 节点增加"上传文档→自动解析→索引"流程, 复用现有 `KBIngestCallback` |

---

### 9.2 节点系统 — 能力深化

#### 9. LLM: 结构化输出 (JSON Schema) → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 支持 JSON Schema 可视化编辑+AI生成+校验, aiPlat 仅自由文本 prompt |
| **架构兼容** | `sys_llm_generate` 已支持 `response_format`, 后端零改动。前端加 JSON Schema 编辑器(轻量级 textarea + jsonschema 校验库) |
| **实现路径** | LLM config 增加 `output_schema` 字段 (JSON textarea), engine 读取 `node_config.output_schema` → `response_format={"type":"json_schema","json_schema":...}` |

#### 10. Code: Docker 沙箱 → ✅ 采纳 (但简化)

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 有 Docker 沙箱, 预装 numpy/pandas。aiPlat 仅 `subprocess.run` 无隔离 |
| **架构兼容** | 沙箱核心功能 (`_sandbox_worker.py`) 已有代码路径(动态生成), 但未落地。直接上 Docker 太重(需 docker daemon 依赖) |
| **实现路径** | 先走 syscall 通道 (`sys_tool_call` → CodeExecutionTool, 已有), 增加资源限制 (memory/cpu/timeout 通过 `subprocess` + `resource` 模块)。Docker 沙箱作为可选增强(`sandbox_mode='docker'`), 通过 `AIPLAT_SANDBOX_DOCKER_ENABLED` 开关 |

#### 11. HTTP: SSRF 代理 + 多认证 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 有专用 ssrf_proxy 容器 + 6种认证, aiPlat 裸 `urllib.request` |
| **架构兼容** | SSRF 代理实现简单 (HTTP_PROXY 环境变量), 多认证在 `node_config` 中加字段即可 |
| **实现路径** | 前端: Method/Auth Type/Basic User+Pass/Bearer Token/SSL Verify 字段。后端: `node_config.auth` → `requests`/`httpx` 库替代 `urllib`, 走 `HTTP_PROXY` |

#### 12. Knowledge: 重排序 + 多模态 → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 重排序需额外 embedding 模型部署, 多模态需图像 embedding pipeline。当前 Knowledge 基础设施 (基于 SQLite+JSON) 不支持这些 |
| **如果要做** | 等 Knowledge 模块升级到向量数据库 (如 Chroma/Milvus) 后再加 |

#### 13. 所有节点: retry/timeout 引擎侧执行 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | 前端有 retry_count/timeout_sec 字段, 引擎完全不读取 (用全局 `max_retry_attempts` + `stage_timeout_seconds`) |
| **架构兼容** | 引擎已有 per-stage 超时 (`_exec_stage` 的 `stage_timeout_seconds`) 和重试 (`_retry_loop`)。只需加一行代码从 `node_config` 读取 |
| **实现路径** | `pipeline_engine.py` 中 `_exec_stage`: 读取 `node_config.get('retry_count', config.max_retry)` + `node_config.get('timeout_sec', config.stage_timeout)` |

---

### 9.3 变量系统

#### 14. Jinja2 模板引擎 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 有, aiPlat 无。`{{var.path}}` 深度访问 + 过滤器 `| upper` + 条件 `{% if %}` 是变量引用的标准范式 |
| **架构兼容** | Python Jinja2 库零依赖, pipeline_engine 的 `_build_prompt` 中加 `jinja2.Template(prompt).render(ctx)` 即可 |
| **实现路径** | Phase 1: `_build_prompt()` 中检测 `{{` 和 `{%`, 自动调用 Jinja2 渲染 (喂入上游 artifact 上下文)。前端变量选择器生成 `{{Node.var.path}}` 语法 |

#### 15. 深度对象访问 `{{a.b[0].c}}` → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 支持, aiPlat 仅 `{{Node.var}}` 一层 |
| **架构兼容** | 依赖 Jinja2 (项14)。若不用 Jinja2, 也可用简易 Python path resolver (`.split('.')` + `[n]` 索引) |
| **实现路径** | 配套 Jinja2 引擎, 或独立 `resolve_path(state, "Node.var.field[0].sub")` 工具函数 |

#### 16. 环境变量隔离 → ✅ 采纳 (但简化)

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify 每个应用有独立环境变量, DSL 导出时自动剥离, aiPlat 无 |
| **架构兼容** | aiPlat 的全局配置走环境变量 (`AIPLAT_*`), 无应用级密钥概念。但可通过 `~/.aiplat/workflow_secrets/{name}.json` 实现 |
| **实现路径** | 新增 `node_config` 支持 `env: {KEY_NAME: "..."}`, 启动时写入临时环境变量, 执行后清除。DSL 导出时自动 strip |

#### 17. 自动类型推导 → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 自动推导在 Python 动态类型下天然工作——引擎不需要前端类型标注。aiPlat 当前的手动类型选择 (str/num/bool/obj/arr) 是文档性而非强制性的。Coze 的类型推导用于 Go/TypeScript 编译检查, aiPlat 无此需求 |
| **替代方案** | 保持当前手动类型标注。引擎运行时自由传递 Python 对象, 不依赖类型声明 |

#### 18. 循环作用域变量 (item/index) → ✅ 采纳 (依赖项 1)

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, 循环内需要 item/index 自动变量 |
| **架构兼容** | 依赖循环容器实现。循环内子阶段 prompt 自动注入 `loop.item` / `loop.index` 变量 |
| **实现路径** | 循环容器执行时, 为每个迭代构建 `{"loop.item": array[i], "loop.index": i}` 上下文 |

#### 19. 对话/会话变量 → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | Chatflow 不是 aiPlat 当前主要使用模式 (偏向构建型流水线而非对话型 ChatGPT)。加入后需建设 ConversationService + 会话管理 UI, 跨度大 |
| **如果要做** | Phase 3, 等 Workflow Canvas 稳定后再扩展到 Chatflow 模式 |

#### 20. JSON Schema 输出校验 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, 运行时校验节点输出结构 |
| **架构兼容** | 前端: JSON Schema textarea。后端: engine 在存储 artifact 前 `jsonschema.validate(output, schema)` |
| **实现路径** | `node_config.output_schema` → `_exec_stage` 完成后校验→失败则触发 `failure_strategy` |

---

### 9.4 扩展生态系统

#### 21. 多语言 SDK → ✅ 采纳 (Python 优先)

| 理由 | 说明 |
|------|------|
| **差距量化** | Coze 有 8 种, Dify 无(仅 REST), aiPlat 无 |
| **架构兼容** | aiPlat 的 API 层 (`aiPlat-platform/api/routers/builder.py`) 已有完整项目 CRUD + 启动/审批/回滚。SDK 是薄封装 |
| **实现路径** | Phase 1: Python `aiplat-client` (pypi), 封装 Workflow/Bot/Chat REST API + SSE streaming。Phase 2: Go/JS |

#### 22. 插件/扩展 API → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | Dify 的 Plugin Daemon (独立 Docker 容器) 和 Coze 的 Plugin Store 是重型基础设施。aiPlat 已有 Skill/Tool 机制, 其本质就是"扩展 API"——Skill 通过 SKILL.md 注册, Tool 通过 ToolRegistry 注册 |
| **替代方案** | 将现有 SkillRegistry/ToolRegistry 文档化, 提供 CLI `aiplat skill create` / `aiplat tool install` 等命令, 降低创建门槛。不另建插件运行时 |

#### 23. 发布为 API 端点 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, 工作流发布后自动生成 REST endpoint |
| **架构兼容** | `projectApi.start()` 已有, 包装为 `POST /v1/workflows/{id}/run` + API key 管理 |
| **实现路径** | 新增 `workflow_run` 端点, 生成 API key (JWT with scope), Swagger 自动文档 |

#### 24. 插件市场 → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 插件市场需要: 审核流程/打包标准/版本兼容性矩阵/社区管理/文档网站。aiPlat 当前是单人/小团队项目, 建市场投入产出比极低 |
| **替代方案** | GitHub 上建 `aiplat-plugins` 仓库, 社区 PR 贡献 Skill/Tool, README 索引。不建在线商店 |

#### 25. MCP Server → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, 将平台能力暴露给外部 AI 客户端 |
| **架构兼容** | aiPlat 已有 MCP infra (`aiPlat-infra/infra/mcp/`), 只需加 MCP Server 端 (当前主要是 Client 端) |
| **实现路径** | 新增 `aiPlat-mcp-server` (Python, 独立包), 暴露 tools: `list_workflows`, `run_workflow`, `get_state`, `approve`, `reject` |

#### 26. Webhook 触发器 → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有, 外部系统通过 HTTP 触发工作流 |
| **架构兼容** | 在现有 `builder_project_service.py` 加 `trigger_workflow(project_id, payload)` 入口, 路由层暴露 Webhook URL |
| **实现路径** | `POST /webhooks/{project_id}` → `projectApi.create(name)` → `projectApi.start(id)`, payload 注入 prompt |

---

### 9.5 协作与生产

#### 27. WebSocket 实时协作 → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 需要: WebSocket server + 操作转换(OT)/CRDT + 冲突解决 + 多光标同步。这是 aiPlat 1文件画布架构的最大挑战——当前 `useState` 模式不支持多用户并发修改 |
| **如果要做** | 必须先拆画布为多文件 (Reducer/Dispatcher/SocketStore), 与 aiPlat"1文件"定位冲突。建议 Phase 3 评估: 用户需求是否真的需要? 如果只需异步协作(非实时), 可以通过 Git merge 实现 |
| **替代方案** | Phase 2: 异步协作 (save→git push→其他用户 git pull→reload)。不加实时 WebSocket |

#### 28. 节点执行日志 (可视化) → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 都有可视化执行日志, aiPlat 仅 graph_trace 文本 |
| **架构兼容** | `_graph_trace` 已有数据, 缺少前端展示 |
| **实现路径** | 执行完成后, Output 标签展示 per-node 卡片: 输入(截取200字)/输出(截取500字)/耗时/token/错误。复用已有 `_graph_trace[{node,status,ts,output,error}]` |

#### 29. 工作流版本管理 → ✅ 采纳 (但简化)

| 理由 | 说明 |
|------|------|
| **差距量化** | Dify/Coze 有完整发布/回滚/历史, aiPlat 仅模板版本号 |
| **架构兼容** | 利用已有 Git 闭环: 每次保存 → `git commit`, 每次发布 → `git tag`。前端显示历史 commit 列表 |
| **实现路径** | 工具栏加 "历史" 按钮 → `git log --oneline` 工作流文件 → 点击恢复。不用自建版本数据库 |

#### 30. Code/HTTP/Knowledge 走 syscall → ✅ 采纳

| 理由 | 说明 |
|------|------|
| **差距量化** | 安全审计覆盖已补 (Code/HTTP/Knowledge 已走 syscall) |
| **架构兼容** | Code→CodeExecutionTool, HTTP→HttpTool, Knowledge→KbQueryTool 均已存在。只需在 pipeline_engine 中路由到 `sys_tool_call` 而非直连 |
| **实现路径** | `node_type='code'` → `sys_tool_call('code_execute', {language, snippet})`。HTTP/Knowledge 同理。零新增代码, 仅改路由 |

#### 31. RBAC 权限模型 → ⚠️ 暂缓采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | RBAC 需: 用户系统/角色表/权限中间件/前端鉴权 UI。aiPlat 当前无用户系统(目标是小团队单体部署) |
| **替代方案** | Phase 2: 通过 `AIPLAT_API_KEY` + `AIPLAT_ADMIN_KEY` 环境变量实现简单的 API 级别权限区分。不加角色/用户表 |

#### 32. 灰度发布 → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 灰度发布需要: 多版本并行部署/流量路由/版本切换/指标对比。这是云平台级别的基础设施, 与 aiPlat 单进程定位不兼容 |
| **替代方案** | 利用 Git 分支+Git tag 实现工作流版本切换 (非灰度, 是手动切换) |

#### 33. 移动端支持 → ❌ 不采纳

| 理由 | 说明 |
|------|------|
| **不采纳原因** | 移动端画布编辑器的开发成本极高(响应式布局/触摸交互/手势识别/移动性能), 且与 aiPlat 当前面向开发者的定位不符 |
| **替代方案** | 移动端只读查看器 (响应式 CSS), 不建移动端编辑器 |

---

### 9.6 汇总

| 决策 | 项数 | 明细 |
|:--:|:--:|------|
| ✅ **采纳** | **20** | 循环容器, 多条件IfElse, Assigner, Template, LLM结构化输出, Docker沙箱(简化), SSRF+多认证, retry/timeout引擎侧, Jinja2, 深度对象访问, 环境变量(简化), Schema校验, Python SDK, 发布API, MCP Server, Webhook, 节点日志(可视化), 版本管理(Git), syscall安全, 循环作用域变量 |
| ⚠️ **暂缓** | **8** | Human Input(有HITL替代), Aggregator(组合实现), Knowledge重排序(需向量DB), 对话变量(非核心模式), 插件API(有Skill/Tool替代), 实时协作(与1文件架构冲突), RBAC(无用户系统), 灰度发布(云平台级) |
| ❌ **不采纳** | **5** | Database节点(基础设施过重), 文档提取器(外部库依赖), 自动类型推导(Python不需要), 插件市场(社区规模不足), 移动端(定位不匹配) |

### 9.7 不采纳项替代方案汇总

| 不采纳项 | 替代方案 |
|---------|---------|
| Database 节点 | 通过 Tool 节点调用数据库查询 Tool |
| 文档提取器 | Knowledge 节点增加上传→解析→索引流程 |
| 自动类型推导 | 保持手动标注, Python 动态类型不依赖 |
| 插件市场 | GitHub `aiplat-plugins` 仓库 + README 索引 |
| 移动端 | 响应式 CSS 只读查看器 |
| 实时协作 | Git push/pull 异步协作模式 |
| 插件 API | Skill/Tool 注册 CLI (`aiplat skill create`) |
| 灰度发布 | Git branch + tag 手动切换 |

---

## 10. 对比表逐项采纳分析

> 规则: 对照 Section 4(三方圆桌对比) 的每一行 + Section 5(差距清单) 的每一项。
> 凡 aiPlat 处于落后地位的, 逐条给出「采纳/不采纳/暂缓」判决 + 核心理由。

---

### 10.1 执行引擎 (对照 §5.1)

#### 引擎架构 (Flask+Celery / Go Hertz+Eino / FastAPI+ReActLoop)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 FastAPI + ReActLoop 是主动选择, 非落后项。单进程架构带来部署极简和调试便利。若要追 Coze 的性能, 可考虑在 FastAPI 外挂 `uvicorn[standard]` 多 worker, 而非换语言。Celery 任务队列是异步模式, 与 aiPlat 同步执行理念不同——不追 |

#### 工作流编排 (DSL+Celery / compose.NewGraph() / PipelineEngine)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | PipelineEngine 的编排能力(拓扑排序/并行/依赖解析)已足够。Eino 的 `compose.NewGraph()` 更灵活, 但那是 Go 生态。Dify 的 Celery 队列模式增加了部署复杂度(task queue + result backend)。维持 PipelineEngine, 在需要更复杂编排时扩展 `depends_on` 和条件路由 |

#### Agent 模式 (FC+ReAct / ChatModelAgent / ReActLoop)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 ReActLoop 是全手工控制, 可控性最强, 这是优势而非劣势。Dify 的 Agent 节点通过配置选择策略, 更易用但灵活性受限。维持当前 ReActLoop, 前端可加"Agent 模式"下拉简化配置 |

#### 循环/迭代 → ✅ 采纳 (已分析, 见 §9.1-1)

#### 条件分支 (多条件 vs eval 单条件) → ✅ 采纳 (已分析, 见 §9.1-2)

#### 并行执行 → ⬜ 不适用 (三方一致)

#### HITL → ⬜ 不适用 (aiPlat 领先)

#### 错误处理 → ⬜ 不适用 (三方各有特色, aiPlat 的 fail/skip/fallback 机制更丰富)

---

### 10.2 节点丰富度 (对照 §5.2)

#### 节点总数 (21 vs 15+ vs 7)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | "总数"不是目标。关键是有多少种是**真正需要**的。aiPlat 的 13 种覆盖了 90% 工作流场景(Agent/LLM/Code/HTTP/Condition/Knowledge/Tool)。追到 15-21 种会导致画布文件膨胀(每种新类型 ~30 行 stageNode + ~20 行 config + ~20 行后端), 与"1文件简洁"定位冲突。已新增 3 种(list/assigner/template)到 10 种，循环容器为下一目标, 不必追平数量 |

#### AI 节点 (Dify:5 vs Coze:2 vs aiPlat:3)

| 判 | 理由 |
|:--:|------|
| **问题分类器** → ❌ 不采纳 | Dify 用 LLM 做文本分类→路由到不同分支。aiPlat 的 Condition 节点 + LLM 节点组合可实现同样效果。独立分类器节点是 Dify 设计偏好, 非通用刚需 |
| **参数提取器** → ❌ 不采纳 | 同理, 从自然语言提取结构化参数是 LLM 节点的能力(通过 prompt 指令 + JSON Schema输出)。不另建节点 |

#### 逻辑节点 (Dify:3 vs Coze:3 vs aiPlat:1)

| 判 | 理由 |
|:--:|------|
| **迭代+循环** → ✅ 采纳 (已分析, §9.1-1) |
| **多条件 IfElse** → ✅ 采纳 (已分析, §9.1-2) |
| **Batch** → ❌ 不采纳 | Coze 的 Batch 节点是批量处理模式, 本质是循环的特化。aiPlat 用循环容器实现后, Batch 作为节点级配置项(`iteration_mode: sequential|parallel`)即可, 不另建节点 |

#### 数据节点 (Dify:4 vs Coze:3 vs aiPlat:2)

| 判 | 理由 |
|:--:|------|
| **Template** → ✅ 采纳 (已分析, §9.1-4) |
| **Variable Assigner** → ✅ 采纳 (已分析, §9.1-3) |
| **Variable Aggregator** → ⚠️ 暂缓 (已分析, §9.1-6) |
| **Database** → ❌ 不采纳 (已分析, §9.1-7) |

#### 集成节点 (Dify:3 vs Coze:3 vs aiPlat:2)

| 判 | 理由 |
|:--:|------|
| **文档提取器** → ❌ 不采纳 (已分析, §9.1-8) |
| **Plugin/Tool** → ⚠️ 暂缓 | aiPlat 已有 Tool 节点 + Skill 系统。Dify/Coze 的插件生态更成熟, 但那是社区规模的差距, 非技术差距。采纳 MCP 暴露+SDK 即可补 API 层面的开放度 |

#### 交互节点 (Dify:2 vs Coze:3 vs aiPlat:0)

| 判 | 理由 |
|:--:|------|
| **Human Input** → ⚠️ 暂缓 (已分析, §9.1-5) |
| **Answer 节点** → ❌ 不采纳 | Dify 的 Answer 节点用于 Chatflow 中直接返回结果, aiPlat 的构建型流水线通过 output_artifact 存储结果。不需要 |
| **Start/End + Input/Output** → ⚠️ 暂缓 | Coze 的 Start/End 节点含 JSON Schema 入参校验。aiPlat 的流水线入口通过 API 参数传入, 不依赖画布节点。若需前端可视化入参, 可加到 launch modal |

---

### 10.3 变量系统 (对照 §5.3)

#### 变量声明 (Start节点 / Assign节点 / 每节点output_variables)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | 三方各有特色: Dify 在 Start 集中声明, Coze 用 Assign 节点散落, aiPlat 每节点声明输出。aiPlat 的模式最直观——每个节点声明"我能产出什么", 下游通过作用域链发现。维持 |

#### 类型系统 (无标注 / 自动推导 / 手动选择)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的手动类型选择已满足需求。Coze 的自动推导用于 TypeScript/Go 的编译检查, aiPlat 的 Python 运行时不需要。Dify 无类型标注是短板。维持当前并深化 str/num/bool/obj/arr 的文档性标注 |

#### 引用语法 ({{var}}深度访问 / 选择器UI / {{Node.var}}点击插入)

| 判 | 理由 |
|:--:|------|
| **深度 `.` 访问** → ✅ 采纳 | `{{var.field[0].sub}}` 刚需 (§9.1-15) |
| **选择器 UI** → ⚠️ 暂缓 | Coze 的变量选择器 UI(输入框内联下拉)体验更好, 但实现复杂度高(需光标位置检测+浮动面板+键盘导航)。当前 aiPlat 的侧栏点击插入已可工作, 等作用域链落地后再优化 |

#### 作用域 (全局+节点+对话 / 全局+节点+循环item/index / BFS层级树)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 BFS 层级树是三方中最直观的作用域可视化。Dify 有对话变量(chatflow模式), Coze 有循环作用域。前者的 chatflow 不是 aiPlat 主模式(§9.1-19), 后者的循环作用域等循环容器后再加(§9.3-18) |

#### 系统变量 (8种 / ✓ / 5种)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** | Dify 有 8 种系统变量, aiPlat 目前 5 种。缺 `sys.workflow_id`、`sys.workflow_run_id`、`sys.dialogue_count`。前两者在流水线执行上下文中天然存在(start 时注入), 只是前端未展示。补 2 种: 总成本 ~10 行 |

#### 环境变量 (应用级DSL剥离 / ✓ / 无)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** (简化) | 已分析 §9.3-16。核心: `node_config` 支持 `env: {KEY: val}`, DSL 导出时自动 strip |

#### 模板引擎 (Jinja2 / 无 / 无)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** | 已分析 §9.3-14。Phase 1: Prompt 字段支持 Jinja2 渲染 |

---

### 10.4 扩展与定制 (对照 §5.4)

#### 插件/工具 (市场+Daemon / 商店 / Skill+Tool)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 Skill(24)+Tool(10+) 机制已成熟。Dify 的 Plugin Daemon 是 Docker 级隔离, 更安全但更重。aiPlat 不需要追插件市场(§9.4-24), 但需要追 SDK(§9.4-21)。维持当前, 通过 CLI + SDK + GitHub 仓库扩大生态 |

#### 自定义节点 (需写插件 / FlowGram Material / 后端路由)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的新增节点方式是三方中最简单的: 前端 pallete+stageNode+config, 后端 pipeline_engine 一条 if 路由。FlowGram Material 是前端组件注册系统, aiPlat 的 inline stageNode 已足够。维持 |

#### Hook 系统 → ⬜ 不适用 (aiPlat 独有)

#### MCP → ⬜ 不适用 (三方均有)

#### SDK (仅REST / 8语言 / 仅REST)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** (Python优先) | 已分析 §9.4-21。不追 8 语言——Python SDK 覆盖 80% 用户, Go/JS 按需 |

#### DSL/模板 (YAML+版本 / 版本 / JSON+版本)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 JSON 模板+版本号已可用。Dify 的 YAML DSL 更适合跨实例移植, aiPlat 通过 JSON 导出/导入已实现同等效果。不追求 Dify 的复杂版本控制(发布/回滚/历史)——用 Git 替代 |

#### AGENT.md → ⬜ 不适用 (aiPlat 独有)

#### 记忆系统 (TokenBuffer / 用户级 / 3层)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 的 3 层记忆是三方中最深的。Dify 的 TokenBufferMemory 仅做上下文窗口持久化, Coze 的用户级记忆是简单的历史对话缓存。维持并深化: 将记忆接入工作流画布的 Output 标签展示 |

---

### 10.5 生产就绪度 (对照 §5.5)

#### 部署复杂度 (Docker/K8s / Docker/K8s / 单进程)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | 单进程是 aiPlat 的主动选择, 非落后。不追 Docker Compose 化——会增加部署复杂度。维持 `python -m aiplat` 一行启动 |

#### 可观测性 (仪表板+Langfuse / Coze Loop / trace+graph+HealthReport)

| 判 | 理由 |
|:--:|------|
| **外部追踪集成** → ✅ 采纳 | Langfuse/LangSmith 集成可通过将 `_graph_trace` 导出为 OpenTelemetry 格式实现, 成本 ~100 行。Coze Loop 是独立平台, 不追 |
| **内置仪表板** → ⚠️ 暂缓 | Dify 的内置仪表板(消息/用户/token)是管理端功能, 不在画布范围内。Phase 3 评估: 是否在 Overview 页面加入工作流运行统计 |

#### 日志 (节点级+可视化 / Loop自动捕获 / graph_trace+溯源)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** (可视化) | 已分析 §9.5-28。不追 Coze Loop 的自动捕获(那是独立平台)。核心: graph_trace 前端可视化 |

#### 协作 (WebSocket实时+评论 / Space隔离 / 无)

| 判 | 理由 |
|:--:|------|
| ⚠️ **暂缓** (已分析 §9.5-27) | 实时协作与 1 文件画布架构冲突严重。Phase 2 用 Git push/pull 异步协作替代 |

#### 版本管理 (发布/回滚/历史 / commit/发布/灰度 / 模板版本号)

| 判 | 理由 |
|:--:|------|
| ✅ **采纳** (但简化) | 已分析 §9.5-29。用 Git 替代自建版本数据库 |

#### 安全 (沙箱+SSRF+JWT / OAuth+PAT+SSO / 6层深度)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 领先。SSRF 代理 + 多认证在 §9.2-11 中已列采纳 |

#### CI/CD (无 / 无 / Git auto-commit/rollback)

| 判 | 理由 |
|:--:|------|
| ⬜ **不适用** | aiPlat 独有 |

---

### 10.6 综合评分维度 (对照 §5.6)

| 维度 | 当前 | 判 | 理由 |
|------|:--:|:--:|------|
| 节点丰富度 | ★★★ | **投入提升** | 追到 11+ 种 (循环/IfElse/Assigner/Template) |
| 执行引擎深度 | ★★★★★ | 维持 | 已是最高 |
| 变量系统 | ★★★★ | **投入提升** | Jinja2+深度访问+环境变量 |
| 扩展生态 | ★★★★ | **投入提升** | SDK+发布API+MCP Server |
| 生产就绪度 | ★★★ | **投入提升** | 日志可视化+版本管理+syscall安全 |
| 代码简洁性 | ★★★★★ | 维持 | 核心竞争力 |
| 安全深度 | ★★★★★ | 维持 | 已是最深 |
| AI 记忆/学习 | ★★★★★ | 维持 | 已是最深 |

---

### 10.7 差距清单逐项再判 (对照 §5)

> 综合 §8 + §9 分析, 对 Section 5 原 14 项的最终裁定:

| # | 差距 | §5 原判 | 最终 | 理由摘要 |
|---|------|:--:|:--:|------|
| 1 | 循环容器 | 新增 | ✅ | 数组处理刚需, 递归执行 |
| 2 | Jinja2 | 新增 | ✅ | Prompt 渲染标准, Python 零依赖 |
| 3 | Assigner | 新增 | ✅ | 数据转换刚需, 声明式 |
| 4 | Human Input | 新增 | ⚠️ | 已有更强HITL, 不重复 |
| 5 | WebSocket协作 | 新增 | ⚠️ | 与1文件架构冲突, Git异步替代 |
| 6 | 多条件IfElse | 新增 | ✅ | 扩Handle+规则数组 |
| 7 | 环境变量 | 新增 | ✅ | JSON存密钥, DSL strip |
| 8 | 节点日志 | 新增 | ✅ | graph_trace前端可视化 |
| 9 | SDK | 新增 | ✅ | Python优先, pypi |
| 10 | syscall通道 | 补缺 | ✅ | 改路由, 零新增代码 |
| 11 | 插件市场 | 低优 | ❌ | 社区不足, GitHub替代 |
| 12 | 发布API | 低优 | ✅ | REST endpoint+API key |
| 13 | 灰度发布 | 低优 | ❌ | 云平台级, Git分支替代 |
| 14 | 移动端 | 低优 | ❌ | 定位不匹配 |

---

### 10.9 为什么节点种类必须增加 —— 用户场景驱动的重新评估

> 原判 "11 种足够" 是基于代码行数约束的保守估算。以用户实际工作流场景重新审视后, **采纳范围应扩大**。

---

#### 每一个被拒节点, 看用户能不能不用它完成同样的工作

| 节点 | 原来判定 | 实际场景 | 不用这个节点的话... | 新判 |
|------|:--:|------|------|:--:|
| **参数提取器** | ❌ | "从用户提交的 PDF 需求中提取项目名称/预算/截止日期" | 用户需要在 LLM 节点里手写 JSON Schema prompt + 后置 Code 节点做 `json.loads`。3 步变成 1 步的差距 | ✅ |
| **问题分类器** | ❌ | "用户输入→判断是技术支持问题还是销售咨询→路由到不同工作流" | Condition 节点只能做表达式求值, 无法做语义分类。必须前置 LLM 节点→再 Condition。而 Dify 的 Classifier 是一键配置的 | ✅ |
| **Template/Jinja2** | ✅ | "把 HTTP 返回的 JSON 转成 LLM 能理解的 Markdown 表格" | 需写 Code 节点 Python 代码。Template 节点可视配置 `{{item.name}} \| {{item.price}}`, 无需编程 | ✅ |
| **Variable Assigner** | ✅ | "过滤上游输出中 price>100 的条目" | Code 节点 5 行 Python。Assigner 节点一个下拉选择字段+一个条件表达式, 非开发者也能用 | ✅ |
| **列表操作器** | ❌ | "取搜索结果的前 10 条" | Code 节点 `data[:10]`。一行代码, 但对于非开发者是巨大的心理门槛。Dify 的 List Operator 是拖拽配置 | ✅ |
| **Human Input** | ⚠️ | "生成初稿后请项目经理审核通过再继续" | aiPlat 已有 HITL 机制(approve/reject)。但 HITL 需要配置 `hitl_phase`, 不如 Human Input 节点直观——拖一个节点到画布上就能暂停 | ✅ |
| **循环容器** | ✅ | "对搜索结果每条调用 LLM 做摘要" | 没有循环只能手工拆分或外部脚本 | ✅ |
| **多条件 If-Else** | ✅ | "分数≥80 通过, 60-79 修改, <60 驳回" | 单 eval 无法表达多分支 | ✅ |

---

#### 关键洞察

**"组合可实现" ≠ "不需要独立节点"**

| 原则 | 说明 |
|------|------|
| **降低非开发者门槛** | 每增加一个专用节点, 就减少一批不需要写 Code 节点的用户 |
| **减少工作流复杂度** | 1 个 Classifier 节点 = LLM 节点 + Condition 节点 + prompt 手写。Dify 用户铺出来的工作流更短 |
| **节点丰富度直接影响竞争力** | 用户在 Dify(21 种) 和 aiPlat(15 种) 之间选择时, 节点数量是第一印象 |
| **增加的代码量可控** | 每种新节点: 前端 ~40 行 (palette+stageNode+config), 后端 ~20 行 (pipeline_engine 路由)。10 种新节点 = 600 行, 仍在单文件可控范围内 |

---

#### 修正后的节点目标

| 阶段 | 目标 | 新增节点 |
|------|:--:|------|
| **当前** | 7 | agent / llm / code / http / condition / knowledge / tool |
| **Phase 1** | **14** | +循环容器 / +多条件IfElse / +Template(Jinja2) / +VariableAssigner / +参数提取器 / +问题分类器 / +列表操作器 |
| **Phase 2** | **16** | +HumanInput / +VariableAggregator |
| **不追** | — | Database(基础设施过重) / 文档提取器(KB增强替代) |

---

#### 修正后的 §4.6 综合评分预期

| 维度 | 当前 | Phase1后 | Phase2后 |
|------|:--:|:--:|:--:|
| 节点丰富度 | ★★★ | ★★★★ | ★★★★☆ |
| 节点类型数 | 10 | 14 | 16 |

#### 对 §9.2 原判的修正

| 节点 | 原判 | 修正 | 原因 |
|------|:--:|:--:|------|
| 参数提取器 | ❌ | ✅ | LLM+RAG 流水线刚需, 3步→1步 |
| 问题分类器 | ❌ | ✅ | 语义路由刚需, Condition 无法替代 |
| 列表操作器 | ❌(未列) | ✅ | 非开发者门槛, Code 节点吓退用户 |
| Human Input | ⚠️ | ✅ | HITL 太复杂, 画布级 Human Input 更直观 |
| Batch | ❌ | ❌ 维持 | 循环的 `mode=parallel` 已覆盖 |
| Answer | ❌ | ❌ 维持 | Chatflow 专属, 非构建型流水线需要 |
| Database | ❌ | ❌ 维持 | 基础设施过重, Tool 节点调用替代 |
| 文档提取器 | ❌ | ❌ 维持 | KB 回调增强替代 |

---

### 10.10 最终统计 (含 §10.9 修正)

| 裁决 | 数量 | 典型 |
|:--:|:--:|------|
| ✅ 采纳 | **22** | 循环/IfElse/Assigner/Template/提取器/分类器/列表操作器/HumanInput/Jinja2/深度访问/环境变量/Schema校验/SDK/发布API/MCP/Webhook/日志可视化/版本管理/syscall安全/结构化输出/SSRF+认证/retry引擎侧 |
| ⚠️ 暂缓 | **5** | Aggregator/实时协作/RBAC/Knowledge重排序/对话变量 |
| ❌ 不采纳 | **7** | Database/文档提取器/插件市场/灰度发布/移动端/自动类型推导/Batch |
| ⬜ 不适用(非落后项) | **14** | 引擎架构/HITL/Hook/AGENT.md/记忆系统/Git/安全深度/自定义节点/MCP/DSL/部署复杂度 |

> **48 个对比点**: 22 采纳 + 5 暂缓 + 7 不采纳 + 14 不适用。
> 
> 关键修正: 节点目标从 11→**16 种** (Phase1: 7→14, Phase2: 14→16)。
> "组合可实现"≠"不需要独立节点"——每增加一个专用节点, 就服务一批不需要写 Code 的用户。

---

## 11. 遗漏补充：节点与变量系统全覆盖分析

> 此前 §8-§9 的分析有遗漏。以下补全: Dify 的全部 21 种节点 + 变量系统的 12 项子能力, 逐项判采纳/不采纳/暂缓。

---

### 11.1 节点系统全覆盖 (Dify 21 节点 vs aiPlat)

#### A. 流程控制节点 (Dify: Start/End/Answer 3种, aiPlat: 0种)

| 节点 | Dify能力 | aiPlat当前 | 判 | 理由 |
|------|---------|----------|:--:|------|
| **Start (用户输入)** | 定义输入变量名+类型+默认值, 启动工作流 | launch modal | ✅ | 画布上可视化输入定义比弹窗中的表单更直观。实现: 拖 Start 节点到画布→右侧 panel 定义参数(名/型/必填/默认值)→启动时自动注入 prompt |
| **Start (触发器)** | Webhook URL + 定时 cron | `projectApi.start()` | ✅ | Webhook 触发器已在 §9.4-26 采纳。前端: Start 节点可选 mode=`manual|webhook|cron` |
| **End/Output** | 定义输出变量+JSON Schema, 工作流返回值 | 无 (隐式通过 output_artifact) | ✅ | 显式的 End 节点让用户清楚工作流的"出口"。实现: End 节点从上游 artifact 映射到输出字段, 支持 JSON Schema 校验 |
| **Answer** | Chatflow 中直接返回文本 | 无 (构建型流水线不需要) | ❌ | Chatflow 不是 aiPlat 主模式 |

#### B. AI 节点 (Dify:5, 全部分析过)

| 节点 | 当前判 | 是否需要修正 |
|------|:--:|------|
| LLM | ✅ (结构化输出+Jinja2+Vision+记忆窗口) | 维持 |
| Agent | ⬜ 不适用 (aiPlat 更灵活) | 维持 |
| 知识检索 | ✅ (已实现) | 维持 |
| 问题分类器 | ✅ (§10.9已修正) | 维持 |
| 参数提取器 | ✅ (§10.9已修正) | 维持 |

#### C. 逻辑节点 (Dify:3, aiPlat:1, 已全部分析)

| 节点 | 当前判 |
|------|:--:|
| If-Else 多条件 | ✅ |
| 迭代 (数组遍历) | ✅ (循环容器) |
| 循环 (条件循环) | ✅ (循环容器的 while 模式) |

#### D. 数据节点 (Dify:4, aiPlat:2, 需补 ListOperator)

| 节点 | 当前判 | 修正 |
|------|:--:|------|
| Code | ⬜ 已有 | 维持 |
| Template (Jinja2) | ✅ | 维持 |
| Variable Assigner | ✅ | 维持 |
| Variable Aggregator | ⚠️ 暂缓 | 维持 (等循环容器+Assigner落地后评估) |
| **List Operator** | ✅ (§10.9已修正) | 维持 |

#### E. 集成节点 (Dify:3, 全部已分析)

| 节点 | 当前判 |
|------|:--:|
| HTTP Request | ✅ (SSRF+多认证) |
| Tool | ⬜ 已有 |
| 文档提取器 | ❌ |

#### F. 交互节点 (Dify:1, 补分析)

| 节点 | Dify能力 | 判 | 理由 |
|------|---------|:--:|------|
| Human Input | 暂停工作流, 等待用户填写表单后继续 | ✅ | §10.9 已修正。比 HITL 配置更直观 |

#### G. 未覆盖的 Dify 能力

| 能力 | Dify实现 | aiPlat是否缺 | 判 | 理由 |
|------|---------|:--:|:--:|------|
| **文件变量** | 上传文件作为变量在节点间传递 (HTTP响应→文件, Knowledge→文件) | ❌ | ✅ | 当前 HTTP/Knowledge 输出文本, 无法传二进制。场景: "下载一个 PDF → 传给 Knowledge 节点索引"。实现: `output_artifact` 支持 `{"type":"file","path":"...","mime":"..."}` |
| **节点级超时独立配置** | 每个 HTTP/Code 节点独立设置连接/读/写超时 | ❌ (仅全局 timeout_sec) | ✅ | 已在 §9.2-13 采纳, 补 per-node 超时分段 |
| **错误分支 (橙色线)** | 失败后走独立错误处理路径 | ❌ (仅全局 failure_strategy) | ✅ | 每个节点增加 Error Handle (橙色端口), 失败时走独立路径而非全流程终止 |

---

### 11.2 变量系统全覆盖 (Dify 12 项 vs aiPlat)

#### A. 变量定义与类型

| 能力 | Dify | Coze | aiPlat | 判 | 理由 |
|------|:--:|:--:|:--:|:--:|------|
| 输入变量定义 (名/型/默认值) | ✅ Start节点 | ✅ Input节点 | ❌ (仅 launch modal) | ✅ | 随 Start 节点一起实现 |
| 输出变量定义 (JSON Schema) | ✅ End节点 | ✅ Output节点 | ✅ output_variables (手动) | ✅ | 加 JSON Schema 校验 (§9.3-20) |
| 文件类型变量 | ✅ | ❌ | ❌ | ✅ | HTTP响应/KB检索结果可作为文件变量传递 |
| 数组类型变量 | ✅ | ✅ (循环item) | ✅ (output_variables type=array) | ⬜ 已有 |
| 对象类型变量 | ✅ 深度访问 | ✅ | ✅ (output_variables type=object) | ⬜ 已有 |

#### B. 变量作用域与生命周期

| 能力 | Dify | Coze | aiPlat | 判 | 理由 |
|------|:--:|:--:|:--:|:--:|------|
| 全局变量 (工作流级) | ✅ sys.* | ✅ | ✅ sys.* (5种) | ✅ | 补 sys.workflow_id/run_id (§9.3) |
| 节点输出变量 | ✅ 自动暴露 | ✅ 自动暴露 | ✅ output_variables + 作用域链 | ⬜ 已有, 且更直观 |
| 环境变量 (密钥隔离) | ✅ 应用级 | ✅ | ❌ | ✅ | 采纳 §9.3-16 |
| 对话变量 (跨轮次) | ✅ Chatflow | ❌ | ❌ | ⚠️ | Chatflow 非主模式 (§9.3-19) |
| 循环作用域变量 | ✅ item/index | ✅ item/index | ❌ | ✅ | 等循环容器落地后加 (§9.3-18) |
| 变量默认值 | ✅ Start节点设 | ✅ | ❌ | ✅ | `output_variables` 加 `default` 字段 |

#### C. 变量引用与操作

| 能力 | Dify | Coze | aiPlat | 判 | 理由 |
|------|:--:|:--:|:--:|:--:|------|
| 模板语法 `{{var}}` | ✅ Jinja2 | ❌ | ⚠️ `{{Node.var}}` (无深度) | ✅ | Jinja2 §9.3-14 |
| 深度对象访问 `{{a.b[0].c}}` | ✅ | ❌ | ❌ | ✅ | §9.3-15 |
| 变量选择器 UI (内联下拉) | ✅ | ✅ | ⚠️ 侧栏点击插入 | ⚠️ | 内联下拉体验更好但实现复杂, Phase 2 |
| 变量值预览 (运行时) | ✅ | ✅ | ❌ (仅 Output 标签看 artifact) | ✅ | 执行时鼠标悬停节点→显示当前变量值的 tooltip |
| 变量赋值/修改 | ✅ Assigner节点 | ✅ Assign节点 | ❌ | ✅ | 随 Assigner 节点实现 |

---

### 11.3 变量系统的"运行时可见性" — 被忽略的关键维度

| 能力 | Dify | Coze | aiPlat | 判 | 理由 |
|------|:--:|:--:|:--:|:--:|------|
| **运行时变量检查器** | ✅ variable-inspect, 执行中实时看每个节点变量值 | ✅ CozeLoop trace 中查看 | ❌ | ✅ | 这是调试工作流的核心需求。用户需要知道"HTTP 返回了什么""LLM 输出了什么"。实现: 2s 轮询已有的 `_graph_trace`, 在节点 tooltip 中展示当前值 |
| **变量值历史** | ✅ 每次运行记录完整变量快照 | ✅ | ❌ | ⚠️ | 存储成本高, Phase 2 评估 |
| **变量值导出** | ✅ 运行结果可导出为 JSON/CSV | ❌ | ❌ | ⚠️ | Phase 3, 在 Output 标签加"导出"按钮 |

---

### 11.4 补充后的最终采纳清单 (合并 §9 + §10 + §11)

| 类别 | 项数 | 明细 |
|------|:--:|------|
| **新增节点** | **10** | 循环容器 / 多条件IfElse / Template(Jinja2) / VariableAssigner / 参数提取器 / 问题分类器 / 列表操作器 / HumanInput / Start(输入定义) / End(输出定义) |
| **节点深化** | **7** | LLM结构化输出+Jinja2+Vision+记忆窗口 / Code沙箱 / HTTP SSRF+多认证+超时分段 / Knowledge检索增强 / 错误分支(橙色线) / retry+timeout引擎侧 / 文件变量支持 |
| **变量系统** | **8** | Jinja2模板 / 深度对象访问 / 环境变量隔离 / JSON Schema校验 / 循环作用域 / 变量默认值 / 运行时变量检查器 / 文件类型变量 |
| **扩展生态** | **4** | Python SDK / 发布API / MCP Server / Webhook触发器 |
| **生产特性** | **4** | 日志可视化 / 版本管理(Git) / syscall安全补缺 / 外部追踪集成 |
| **不采纳** | **7** | Database / 文档提取器 / 插件市场 / 灰度发布 / 移动端 / 自动类型推导 / Batch |
| **暂缓** | **5** | Aggregator / 实时协作 / RBAC / Knowledge重排序 / 对话变量 |
| **不适用(领先)** | **14** | HITL / Git闭环 / Hook / 3层记忆 / 5级压缩 / CLAUDE.md / Self-improvement / 安全深度 / 1文件简洁 / 等 |

### 11.5 修正后的三阶段路线 (合并 §10 新增项)

#### Phase 1: 追平核心 (14 节点) — 4 周

```
新增节点: 循环容器 / 多条件IfElse / Template(Jinja2) / VariableAssigner
          参数提取器 / 问题分类器 / 列表操作器
节点深化: LLM结构化输出+Jinja2+记忆窗口 | retry/timeout引擎侧 | HTTP超时分段
变量系统: Jinja2模板 | 深度对象访问 | 环境变量隔离 | 变量默认值 | 文件类型变量
扩展生态: 发布API | Python SDK | Webhook触发器
安全补缺: Code/HTTP/Knowledge 走 syscall
架构补强: 网络隔离(HTTP→syscall)
```

#### Phase 2: 补短板 (16 节点) — 4 周

```
新增节点: HumanInput / Start(输入定义) / End(输出定义)
节点深化: Code Docker沙箱 | HTTP SSRF+多认证 | 错误分支(橙色线)
变量系统: JSON Schema校验 | 循环作用域 | 运行时变量检查器 | 系统变量补全
生产特性: 日志可视化 | 版本管理(Git) | 外部追踪集成(OpenTelemetry→Langfuse)
扩展生态: MCP Server | 变量选择器UI(内联下拉)
架构补强: 可观测性(OTel) | 代码隔离(Docker可选) | 网络隔离(SSRF代理)
```

#### Phase 3: 扩大生态 — 4 周

```
节点深化: Knowledge重排序+多模态
变量系统: 变量值历史 | 变量值导出
生产特性: WebSocket协作 | RBAC | 对话变量
 扩展生态: Go/JS SDK
架构补强: 向量检索(lancedb可选) | 水平扩展(uvicorn workers)
```

### 11.6 各维度目标状态 (含架构)

| 维度 | 当前 | Phase1 | Phase2 | Phase3 |
|------|:--:|:--:|:--:|:--:|
| 节点类型数 | 10 | 14 | 16 | 16 |
| 变量访问深度 | 1层 | 任意层 | 任意层+校验 | 任意层+校验+推导 |
| SDK 语言数 | 0 | 1 (Python) | 1 | 3 (Python/Go/JS) |
| 可观测性 | trace_id | trace_id | OTel+Langfuse | OTel+Langfuse |
| 代码隔离 | subprocess | subprocess | Docker可选 | Docker可选 |
| 网络隔离 | 直连 | syscall | SSRF代理 | SSRF代理 |
| 安全审计覆盖 | 3/7 | 6/7 | 7/7 | 7/7 |
| 协作能力 | 无 | 无 | 无 | 实时协作 |

---

## 更新记录

| 日期 | 内容 |
|------|------|
| 2026-05-16 | 基于 Web 调研 + 代码级分析的 Dify/Coze/aiPlat 三方深度对比 |
| 2026-05-16 | Section 7 重写 + Section 8 (34项逐条采纳分析) + Section 9 (逐表逐项分析) |
| 2026-05-16 | Section 9.9 修正 (节点数 11→16, 用户场景驱动) |
| 2026-05-16 | Section 10 补充 (节点全覆盖21→12项分析 + 变量系统12项全覆盖 + 运行时可见性) |
