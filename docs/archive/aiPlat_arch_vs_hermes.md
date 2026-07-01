---
title: aiPlat Core 执行链路 vs Hermes Agent 架构对照
date: 2026-04-18
audience: 内部研发（平台/后端/前端/架构）
status: draft
---

# 1. 目标与结论（TL;DR）

本文对照 **aiPlat（你的系统）** 与 **Hermes Agent** 的架构，给出：

1) 模块职责边界对照  
2) 关键接口定义（执行入口、工具/技能、观测）  
3) 执行数据流（从请求到 trace/links）  
4) 最小重构切入点（最小 PR 列表 + 影响面）  

核心结论：你们已经具备 Hermes 最关键的骨架——`harness/syscalls/*` 是天然的 **执行 choke point**。下一步最小重构应优先把 **Prompt/Context 组装** 与 **Toolset/Registry 治理** 两个子系统从业务逻辑中抽离，让执行核心稳定、可扩展、可观测。

---

# 2. 现状架构图 vs Hermes 架构图（对照）

## 2.1 aiPlat（现状）

```text
                 ┌──────────────────────────────────────┐
                 │ aiPlat-management (UI + management api)│
                 │  - Diagnostics/Links/Trace pages       │
                 │  - /diagnostics/links/core/ui (proxy)  │
                 └───────────────┬───────────────────────┘
                                 │ HTTP proxy
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ aiPlat-core                                                           │
│  core/server.py  (FastAPI 路由)                                       │
│   ├─ /workspace/agents/{id}/execute  ─┐                               │
│   ├─ /workspace/skills/{id}/execute  ─┼─> Workspace*Manager           │
│   ├─ /tools/... (tool execute等)      ┘                               │
│   ├─ /traces/... /executions/... (diagnostics API)                    │
│   └─ lifespan(): attach KernelRuntime(trace_service, execution_store) │
│                                                                      │
│  harness/integration.py  (HarnessIntegration.execute)                 │
│   ├─ start_trace() + upsert_execution()                               │
│   ├─ EngineRouter -> LoopEngine                                       │
│   └─ agent.execute(AgentContext)                                      │
│                                                                      │
│  apps/agents/base.py + apps/agents/react.py                           │
│   └─ harness/execution/loop.py (ReActLoop/BaseLoop)                   │
│        ├─ syscalls/llm.py   (sys_llm_generate)                        │
│        ├─ syscalls/tool.py  (sys_tool_call + PolicyGate)              │
│        └─ syscalls/skill.py (sys_skill_call)                          │
│                                                                      │
│  services/trace_service.py + services/execution_store.py              │
└──────────────────────────────────────────────────────────────────────┘
```

## 2.2 Hermes Agent（参考）

```text
            ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
            │ CLI (cli.py)   │   │ Gateway/IM     │   │ Cron/ACP/etc  │
            └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
                    │                   │                   │
                    └──────────┬────────┴──────────┬────────┘
                               ▼
                     ┌────────────────────┐
                     │ AIAgent (run_agent)│  ← 唯一执行核心
                     │  - loop/tool calls │
                     │  - fallback/retry  │
                     │  - compression     │
                     └───────┬────────────┘
                             │
         ┌───────────────────┼────────────────────┐
         ▼                   ▼                    ▼
┌────────────────┐  ┌─────────────────┐  ┌────────────────────┐
│ Prompt Builder  │  │ Context Engine  │  │ Tool Runtime        │
│ prompt_builder  │  │ context_*       │  │ registry+toolsets   │
│ SOUL/MEM/skills │  │ compress/caching│  │ + MCP discovery     │
└────────────────┘  └─────────────────┘  └────────────────────┘
          │                                         │
          ▼                                         ▼
   Persistent Memory                           tools/* + mcp_tool
  (~/.hermes/memories)                         (all registered)
```

---

# 3. 模块职责对照（aiPlat ↔ Hermes）

| 关注点 | aiPlat（现状） | Hermes（参考） | 建议 |
|---|---|---|---|
| 执行核心 | `harness/integration.py` + `LoopEngine` + `BaseAgent/ReActLoop` | `run_agent.py` 的 `AIAgent` | 继续强化 `harness` 为唯一执行核心，入口只做适配 |
| 工具治理 | apps/tools 侧 registry + UI 配置为主 | `tools/registry.py` + `toolsets.py`（运行时过滤） | 抽出“运行时工具清单生成器”（toolset/policy） |
| Prompt/上下文 | 分散在 agent/skill/执行流程 | `agent/prompt_builder.py` 分层组装 + 缓存策略 | 增加 `PromptAssembler` 子系统（稳定层/临时层） |
| 上下文压缩 | 目前更多依赖前端简化与 trace | `ContextEngine` 可插拔 + `ContextCompressor` | 抽象 `ContextEngine` 接口，为未来 RAG/LCM 做铺垫 |
| 观测 | `trace_service` + `execution_store` + Links 页 | session DB + trajectories + observability hooks | 让“失败原因”在 core 层产出并在 Links 默认展示 |
| 多入口 | core HTTP + management proxy | CLI/Gateway/Cron/ACP 同核 | 为 cron/gateway 预留“入口适配层”接口 |

---

# 4. 关键接口定义（建议形成内部“平台契约”）

## 4.1 执行入口（ExecutionRequest）

建议将“入口适配”统一收敛为一个结构（你们现有 `ExecutionRequest` 已接近）：

```json
{
  "execution_id": "exec-xxx",
  "kind": "agent|skill|tool",
  "target_id": "代码审核",
  "payload": {
    "session_id": "default",
    "messages": [
      {"role": "user", "content": "..." }
    ],
    "input": {"message": "..."},
    "context": {"k": "v"},
    "_resume_loop_state": {}
  },
  "options": {
    "toolset": "safe|write|web|browser|mcp-xxx",
    "dry_run": false
  }
}
```

约束建议：
- `messages` 是统一入口；`input` 仅作为兼容层（你们已在 harness 做了兜底）
- `context` 与 `_resume_loop_state` 明确区分：业务变量 vs loop 快照

## 4.2 syscalls（平台内核的 choke point）

你们的 syscalls 已经是正确方向，建议进一步定义成契约：

- `sys_llm_generate(model, prompt, trace_context) -> LLMResult`
- `sys_tool_call(tool, tool_args, user_id, session_id, trace_context) -> ToolResult`
- `sys_skill_call(skill, params, ...) -> SkillResult`

契约要求：
- **每次 syscall 必须产出 span + syscall_event**（fast-fail 也要有）
- 所有错误统一映射为 `error_code + error_message`（用于 Links 简版展示）

## 4.3 观测接口（Links 需要的最小字段）

Links 页面最低需要：
- trace：`trace_id, status, start_time, duration_ms, spans[]`
- executions：`execution_id, type, status, duration_ms, error(一句话)`
- graph_runs/lineage：可选

你们已经补齐 `error` 字段返回并在前端展示（见后文 PR 列表）。

---

# 5. 执行数据流（从点击执行到 Links 可见）

## 5.1 Agent 执行（Happy Path）

```text
UI 执行按钮
  -> core/server.py  POST /workspace/agents/{id}/execute
      -> WorkspaceAgentManager.get_agent()
      -> get_harness().execute(ExecutionRequest)
          -> HarnessIntegration._execute_agent()
              -> execution_store.upsert_agent_execution(status=running)
              -> trace_service.start_trace()
              -> TraceGate.start("agent.execute")
              -> EngineRouter.route_agent() -> LoopEngine.execute_agent()
                  -> agent.execute(AgentContext)
                      -> ReActLoop.run()
                          -> sys_llm_generate()  [span + syscall_event]
                          -> sys_tool_call()     [span + syscall_event]
                          -> ... loop ...
              -> TraceGate.end("agent.execute")
              -> execution_store.upsert_agent_execution(status=completed/failed, error=...)
          -> 返回给 UI（execution_id、status、可选 output/error）
```

## 5.2 早失败（你们之前出现 spans=[] 的根因）

早失败常见于：
- model/tool/skill 缺失或不可执行（在 start_span 之前 raise）
- payload 不含 messages，loop 无法拿到任务（极快失败）

你们已通过以下最小修复避免黑盒：
- sys_llm/tool/skill **先 start span 再校验**（fast-fail 也写 span/event）
- agent.execute 外围加 `agent.execute` span
- payload 只有 input 时自动生成 messages

---

# 6. 最小 PR 列表（切入点与影响面）

下面按“收益最大/侵入最小”排序。

## PR-0：观测补齐（已完成）

**目标：** 失败不再黑盒，Links 默认可见“一句话错误”。  

已完成变更：
- `obs: ensure spans + errors for fast-fail executions`  
  - 影响文件：  
    - `aiPlat-core/core/harness/integration.py`  
    - `aiPlat-core/core/harness/syscalls/llm.py`  
    - `aiPlat-core/core/harness/syscalls/tool.py`  
    - `aiPlat-core/core/harness/syscalls/skill.py`
- `ux: show execution error in diagnostics links`  
  - 影响文件：  
    - `aiPlat-core/core/services/execution_store.py`  
    - `aiPlat-management/frontend/src/pages/Diagnostics/Links/Links.tsx`

影响面：
- 仅增强可观测性与输入兜底；对既有成功路径行为无破坏

## PR-1：抽出 PromptAssembler（建议优先做）

**目标：** 统一 Prompt/Context 组装，形成“稳定层 + 临时层”，为 B 模式自动注入项目约束、未来压缩/RAG 打底。

建议新增文件：
- `aiPlat-core/core/harness/prompt/assembler.py`
- `aiPlat-core/core/harness/prompt/project_context.py`（读取 `AGENTS.md` / `AIPLAT.md`）
- （可选）`aiPlat-core/core/harness/prompt/injection_scan.py`（注入扫描）

改动点（最小）：
- 在 `sys_llm_generate()` 调用前（或在 LoopEngine 里）统一调用 assembler，生成 prompt

影响面：
- 仅集中 prompt 入口；agent 逻辑不需要重写

## PR-2：引入 Toolset（运行时工具清单生成器）

**目标：** 将“工具可用性/允许工具集合”从 UI 配置升级为运行时治理；MCP 也作为 toolset 纳入最小白名单。

建议新增文件：
- `aiPlat-core/core/harness/tools/toolsets.py`
- `aiPlat-core/core/harness/tools/registry.py`（或封装你们现有工具注册）

改动点（最小）：
- `LoopEngine` 构造 AgentContext 时注入 `available_tools = ToolsetResolver.resolve(...)`
- `sys_tool_call` 在 PolicyGate 前使用 toolset 进行快速拒绝（fail-fast + error_code）

影响面：
- Agent/Skill 不再自己关心“到底有哪些工具可用”，降低耦合

---

# 7. 建议的重构顺序（最小可落地）

1) PR-1 PromptAssembler（统一上下文注入）  
2) PR-2 Toolset/Registry（统一运行时工具治理）  
3) （可选）ContextEngine 抽象（为压缩/RAG/检索做可插拔）  

---

# 7B. 完整路线图 PR 列表（中/大改）

> 本节是“从最小切入点扩展到 Hermes 同款能力”的中长期路线图。它刻意按 **可并行** 的子系统拆分，每个 PR/阶段都尽量有可验收的产出。  
> 建议以 3~6 个月为时间尺度推进（取决于团队人力与上线窗口）。

## Roadmap-0：基础契约统一（中改，打地基）

### PR-R0-1：统一 ExecutionRequest/ExecutionResult 契约
**目标：** 所有入口（Agent/Skill/Tool/未来 cron/gateway）返回一致的结构，前端无需做 N 套适配。  
**内容：**
- 执行返回统一：`execution_id, status, output, error{code,message}, trace_id`  
- 失败原因规范化：error code 枚举 + message（用于 Links/弹窗简版结果）
- 为 tool 执行补齐 `execution_id/trace_id`（使 Tool Modal 也能“查看诊断详情”）
**影响面：** core API 返回结构、前端 services 与执行弹窗

### PR-R0-2：syscalls 事件模型规范化 + 可搜索
**目标：** tool/llm/skill 每次 syscall 产出统一事件（可聚合、可检索、可统计）。  
**内容：**
- syscall_event schema：`kind,name,status,start/end,duration,args,error,span_id`
- 统一落盘 + 索引（按 execution_id/trace_id/agent_id/tool_name）
**影响面：** execution_store、diagnostics API、Links 展示

---

## Roadmap-1：Prompt/Context 子系统（中改 → 大改）

### PR-R1-1：PromptAssembler 完整化（稳定层缓存 + 临时层 overlay）
**目标：** 提升一致性与成本可控性，避免“每个 agent 各拼各的”。  
**内容：**
- `PromptAssembler.build()` 输出：`stable_system_prompt` + `ephemeral_overlay`
- stable prompt 具备缓存 key（按 agent_id+prompt_version+workspace_context_hash）
- overlay 用于预算警告、工具可用性提示、风控提示等
**影响面：** sys_llm_generate / loop_engine 调用 prompt 入口

### PR-R1-2：项目上下文文件（AGENTS.md/AIPLAT.md）支持 + 注入扫描
**目标：** B 模式“自动读仓库”变成平台能力，而不是用户手工粘贴。  
**内容：**
- 约定上下文文件优先级与查找策略（类似 Hermes：repo root 向上/向下）
- 注入扫描（ignore previous instructions / 隐形字符 / exfil pattern）
- 对命中高危的上下文文件：阻断或降级（可配置）
**影响面：** file_operations + PromptAssembler + diagnostics（记录阻断原因）

### PR-R1-3：ContextEngine 插拔（压缩/检索/RAG 的抽象层）
**目标：** 为长会话/大工程任务提供稳定的上下文管理能力。  
**内容：**
- 抽象接口：`should_compact()` / `compact()` / `get_status()`
- 默认实现：压缩（类似 Hermes：先清理旧 tool 输出，再结构化总结）
- 可选实现：RAG（向量检索）、LCM（lossless context management）
**影响面：** loop、trace（压缩 span）、store（lineage）

---

## Roadmap-2：Tool Runtime 治理（中改 → 大改）

### PR-R2-1：Tool Registry 收敛 + Toolset（能力包）体系化
**目标：** 工具治理从“配置表 + UI”升级为“运行时可解释策略”。  
**内容：**
- 工具注册统一入口（schema/handler/check）
- toolset：`safe_readonly` / `write_repo` / `web` / `browser` / `mcp-*` 等
- check_fn：依赖/鉴权缺失时自动从可用工具集合剔除，并返回原因
**影响面：** tool registry、LoopEngine 注入工具集合、前端向导（选择 toolset）

### PR-R2-2：MCP 风险分级与强制最小权限
**目标：** 让 MCP 在 prod 可控可审计（尤其 stdio）。  
**内容：**
- server 级：transport/stdio prod 放行策略统一检查
- tool 级：allowed_tools 最小白名单强制（默认拒绝）
- 描述/错误脱敏与注入扫描（记录到 trace/syscall_event）
**影响面：** MCP 管理、PolicyGate、diagnostics 展示

### PR-R2-3：文件工具工程化（去重/限额/一致性检测）
**目标：** 降 token、降失败率、提升安全性。  
**内容：**
- 重复读取去重（path+offset+limit+mtime）
- 二进制/设备文件/敏感路径防护
- write/patch 前 mtime 校验（外部改动提示）
**影响面：** file_operations、工具返回结构、提示文案

---

## Roadmap-3：多入口与长期运行（大改，可分阶段）

### PR-R3-1：Jobs/Cron（定时任务）成为一等公民
**目标：** 让“计划任务”走同一执行链路，并能投递到多渠道。  
**内容：**
- job 定义：schedule + execution_request_template + delivery
- 执行使用同一 HarnessIntegration（带 trace/execution_id）
- 失败重试/死信与审计
**影响面：** 新服务/表、gateway/通知、diagnostics

### PR-R3-2：Gateway（IM/机器人）入口适配层
**目标：** Slack/飞书/企业微信等入口不复制逻辑，只做 session 路由。  
**内容：**
- 入口适配：消息 → session_id → ExecutionRequest
- 权限与用户绑定（pairing）
- 统一投递执行过程与最终结果
**影响面：** 新模块，需与现有 Auth/tenant 打通

---

## Roadmap-4：学习闭环（大改，视业务优先级）

### PR-R4-1：Skill 生态升级为“技能包”（渐进披露 + 自修复）
**目标：** 把 SOP/示例从“UI 提示”升级为“可维护资产”。  
**内容：**
- skill index（轻量）/ skill view（全文）/ reference files（引用）
- patch/edit 的版本化与审计
- 自动化生成：任务完成后建议沉淀 skill（可开关）
**影响面：** skill_manager、前端技能库、存储与权限

### PR-R4-2：Memory（长期记忆）与 Session Search（跨会话检索）
**目标：** 降低用户重复输入，提升 agent 跨会话连续性。  
**内容：**
- memory（严格容量、结构化条目）
- session_search（全文检索 + 摘要）
- 注入策略：冻结快照 + 下次会话生效（保证缓存稳定）
**影响面：** 存储、隐私与权限、prompt assembler

---

# 7C. 路线图落地建议（组织与验收）

建议每个 Roadmap PR 都具备：
- 可观测：span + syscall_event + execution.error
- 可验收：前端默认简版可见（成功/失败/一句话原因）
- 可回滚：不改变既有执行契约或提供兼容层

# 8. 附：你们 core 执行主链路的关键路径（便于新人快速上手）

- API 入口：`aiPlat-core/core/server.py`

- API 入口：`aiPlat-core/core/server.py`
- 统一执行入口：`aiPlat-core/core/harness/integration.py`
- 引擎路由：`aiPlat-core/core/harness/execution/router.py`
- 执行引擎：`aiPlat-core/core/harness/execution/engines/loop_engine.py`
- Loop：`aiPlat-core/core/harness/execution/loop.py`
- Agents：`aiPlat-core/core/apps/agents/base.py`、`aiPlat-core/core/apps/agents/react.py`
- syscalls：`aiPlat-core/core/harness/syscalls/llm.py`、`tool.py`、`skill.py`
- Trace：`aiPlat-core/core/services/trace_service.py`
- ExecutionStore：`aiPlat-core/core/services/execution_store.py`
