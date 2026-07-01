---
title: 现有系统架构图 vs Hermes vs Claude Code vs OpenClaw（对照）
date: 2026-04-18
---

> 目标：把 **aiPlat（你的现有系统）**、**Hermes Agent**、**Claude Code**、**OpenClaw** 用“同一套视角”画成架构图，并给出关键模块/数据流/扩展点对照，便于你评估：哪些是同构能力、哪些是你缺的、哪些是你更强的。

## 0. 一句话结论（面向架构决策）

- **aiPlat**：典型“平台内核（harness+syscalls）+ 管理面（management）”的服务化架构，优势是 **可观测/可治理/可做多租户**，短板主要在“端侧体验/多端入口”的产品化整合需要继续补齐。  
- **Hermes / OpenClaw**：典型“个人 Agent 产品”路线，强调 **多入口（CLI+IM+移动端）**、**长会话记忆与检索**、**技能自进化**；其中 **OpenClaw 的 Gateway(WS) 控制面更像一个本地控制平面**。  
- **Claude Code**：更像“IDE/终端里的 agentic coding shell”，核心是 **工作流插件（commands/agents/hooks）**，对外扩展依赖插件生态与 MCP，而不是自带一个完整的长期运行控制平面。

---

## 1) 四套系统的“同一张对照架构图”

> 说明：这张图用同一套分层：**入口层 → 执行内核 → 工具/技能 → 存储/观测 → 交付/通道**。

```mermaid
flowchart TB
  %% ---------------- aiPlat ----------------
  subgraph A[aiPlat（你的系统）]
    A_UI[aiPlat-management<br/>UI + management proxy] --> A_API[aiPlat-core FastAPI<br/>/workspace/* /tools /gateway /jobs]
    A_API --> A_H[HarnessIntegration<br/>统一执行入口]
    A_H --> A_L[LoopEngine / Agents(ReActLoop)]
    A_L --> A_SC[syscalls: llm/tool/skill<br/>choke point + policy/approval]
    A_SC --> A_TR[TraceService]
    A_SC --> A_DB[ExecutionStore(SQLite)<br/>executions/syscalls/jobs/learning/memory]
    A_API --> A_J[Jobs Scheduler + Delivery DLQ]
    A_API --> A_GW[Gateway Execute + Pairings/Tokens<br/>Slack adapters]
  end

  %% ---------------- Hermes ----------------
  subgraph H[Hermes Agent]
    H_ENT[入口：CLI/TUI + Gateway(IM)] --> H_RUN[AIAgent / run_agent.py<br/>tool-calling loop]
    H_RUN --> H_P[Prompt Builder<br/>identity+skills+context files]
    H_RUN --> H_CTX[ContextCompressor<br/>+ session_search]
    H_RUN --> H_TS[Toolsets<br/>capability packs]
    H_RUN --> H_TOOLS[Tools: terminal/browser/file/web/skills/memory/cron]
    H_RUN --> H_STORE[本地持久化：skills/memory/sessions<br/>(含 FTS session search)]
  end

  %% ---------------- Claude Code ----------------
  subgraph C[Claude Code]
    C_ENT[入口：Terminal/IDE/GitHub @claude] --> C_CORE[Claude Code Core<br/>agentic coding runtime]
    C_CORE --> C_PLUGIN[Plugin system<br/>commands/agents/hooks/MCP]
    C_CORE --> C_TOOLS[内置工具：代码库理解/执行 routine tasks<br/>（通过工具调用/集成实现）]
    C_PLUGIN --> C_HOOK[Hooks（例如 PreToolUse）<br/>做安全与行为约束]
  end

  %% ---------------- OpenClaw ----------------
  subgraph O[OpenClaw]
    O_GATE[Gateway Daemon (WebSocket)<br/>控制面 + 通道连接] --> O_RPC[WS RPC: agent / agent.wait / send / sessions.*]
    O_RPC --> O_LOOP[Agent Loop<br/>context assembly → model → tool → persistence]
    O_LOOP --> O_Q[Command Queue<br/>per-session lane 序列化]
    O_LOOP --> O_SK[Skills snapshot + system prompt build]
    O_GATE --> O_NODE[Nodes (role=node)<br/>camera/screen/canvas/system.run]
    O_LOOP --> O_APPR[Exec approvals<br/>request/resolve + events]
    O_LOOP --> O_STORE[Sessions/usage/logs/…<br/>（Gateway 作为控制平面）]
  end
```

---

## 2) 逐系统“内部架构图”（更细一层）

### 2.1 aiPlat（现有系统）

```mermaid
flowchart LR
  UI[management UI] --> MAPI[management api/proxy]
  MAPI --> CORE[core/server.py FastAPI]

  CORE --> AG[/workspace/agents/{id}/execute]
  CORE --> SK[/workspace/skills/{id}/execute]
  CORE --> TL[/tools/{name}/execute]
  CORE --> GW[/gateway/execute + adapters]
  CORE --> JOB[/jobs/* + scheduler]

  AG --> H[HarnessIntegration.execute]
  SK --> H
  TL --> H
  GW --> H
  JOB --> H

  H --> LOOP[LoopEngine/ReActLoop]
  LOOP --> SC[syscalls(llm/tool/skill)]

  SC --> STORE[ExecutionStore]
  SC --> TRACE[TraceService]

  STORE --> LINKS[Diagnostics Links/Syscalls/Jobs/Learning UI]
```

特点（抽象）：
- 你是“服务化内核”：**HTTP API 是主入口**，所有执行收敛到 harness，syscalls 是强制治理点。  
- Observability-first：trace + syscall_events + executions 是一等公民。  

### 2.2 Hermes（NousResearch/hermes-agent）

```mermaid
flowchart LR
  ENT[CLI/TUI + Messaging Gateway] --> AGENT[AIAgent (run_agent.py)]
  AGENT --> PB[prompt_builder.py<br/>identity+skills+context files scan]
  AGENT --> CC[ContextCompressor]
  AGENT --> TS[toolsets.py<br/>capability packs]
  TS --> TOOLS[tools/* + model_tools.py]
  AGENT --> MEM[memory + session_search]
  AGENT --> SK[skills/* (create/patch/manage)]
  AGENT --> CRON[cron/*]
  MEM --> STORE[~/.hermes storage]
  SK --> STORE
```

关键词：
- “**个人产品**”取向：多入口、跨会话记忆、技能自进化、cron、广泛通道。  
- Toolsets 是能力包（按场景装配工具集合）。  

### 2.3 Claude Code（anthropics/claude-code）

```mermaid
flowchart LR
  USER[Developer] --> CLI[claude (terminal/IDE)]
  CLI --> CORE[Claude Code runtime]
  CORE --> PLUG[Plugins (.claude-plugin)<br/>commands/agents/hooks/skills/.mcp.json]
  PLUG --> HOOK[Hooks（例：PreToolUse）]
  CORE --> DEVOPS[Git/代码工作流自动化]
  CORE --> MCP[MCP servers（通过插件配置）]
```

关键词：
- **工作流插件化**：官方仓库提供了 feature-dev、code-review、security-guidance 等插件样例（命令/agent/hook 组合）。  
- 更偏“开发者工具”，而不是“长驻控制平面 + 多端路由”。

### 2.4 OpenClaw（openclaw/openclaw）

```mermaid
flowchart TB
  CH[Channels] --> GW[Gateway daemon<br/>WebSocket control plane]
  UI[CLI/Web UI/macOS App] -->|WS connect(role=operator)| GW
  NODE[Nodes iOS/Android/macOS] -->|WS connect(role=node)| GW

  GW --> RPC[WS RPC: agent / sessions.* / tools.* / approvals.*]
  RPC --> LOOP[Agent Loop]
  LOOP --> Q[Command Queue<br/>session lane serialization]
  LOOP --> PI[Embedded agent runtime<br/>(pi-agent-core)]
  LOOP --> APPR[Exec approvals events]
  LOOP --> STORE[Session persistence]
  GW --> CANVAS[Canvas host / A2UI]
```

关键词：
- **Gateway 是控制平面**（WS 协议、角色/权限、节点能力、pairing）。  
- Agent loop 具备完整“生命周期/队列/streaming/审批”设计，适合本地常驻产品形态。  

---

## 3) 核心模块对照表（你做设计决策最常用）

| 维度 | aiPlat | Hermes | Claude Code | OpenClaw |
|---|---|---|---|---|
| 主要形态 | 服务化平台（core+management） | 个人 Agent 产品（CLI+Gateway） | 终端/IDE coding agent | 个人 Agent 产品（Gateway 控制面） |
| 入口层 | HTTP API + UI | CLI/TUI + IM Gateway | CLI/IDE/GitHub | WebSocket Gateway + 多客户端 |
| 执行内核 | HarnessIntegration + LoopEngine + syscalls | AIAgent tool-loop | 核心 runtime + plugins | agent loop（串行化 + streaming） |
| 工具治理 | toolset policy + sys_tool_call 统一管控 | toolsets 能力包 | hooks + 插件约束 | tools.effective + approvals + sandbox 模式 |
| “技能/工作流” | skill packs + workspace skills | skills 自进化、可 patch | plugins（commands/agents/hooks） | skills snapshot + plugins/hooks |
| 记忆/检索 | long_term_memory + memory_messages(FTS) | memory + session_search(FTS) | （更多依赖产品侧/插件能力） | sessions.* + usage/logs + compaction |
| 多端/通道 | Gateway adapters（逐步扩展） | IM 通道非常丰富 | 非重点 | 通道 + node 能力非常丰富 |
| 观测/审计 | trace + syscall_events + DLQ/learning artifacts | insights/trajectory 等 | 更多偏“本地工具体验” | lifecycle/stream/events + 协议层治理 |

---

## 4) 你现有系统 vs 这三者：最关键的“架构差异点”

### 4.1 “控制面”差异：HTTP 管理面 vs WS 控制平面
- aiPlat：控制面偏 **HTTP + 管理 UI**（更适合多租户平台与企业后端形态）。  
- OpenClaw：控制面是 **WS + role/scope**，强在“本地常驻多客户端 + node 能力”。  

### 4.2 “扩展单位”差异：Skill vs Plugin vs Toolset
- Hermes：以 skill 为主要积累单位（经验→技能）。  
- Claude Code：以 plugin 为主要扩展单位（命令/agent/hook/MCP）。  
- aiPlat：两者都有：**skill**（workspace skills/skill packs）+ **toolset/policy**（执行治理）。  

### 4.3 “多入口适配”差异：入口适配层是否一等公民
- Hermes/OpenClaw：入口（IM/CLI/cron/设备）是产品核心能力。  
- aiPlat：入口层正在补齐（gateway pairing/auth + slack adapter 已有），但如果要对标 OpenClaw 的“多客户端控制平面”，需要更系统化的 **channel/session/run 语义**。

---

## 5) Sources（开源仓库）

- Hermes Agent（NousResearch）：https://github.com/NousResearch/hermes-agent  
- Claude Code（Anthropic）：https://github.com/anthropics/claude-code  
- OpenClaw：https://github.com/openclaw/openclaw  

