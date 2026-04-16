# 01｜核心契约与数据模型（Contracts & Types）

状态：草案（Phase 1 已对齐实现；Phase 4+ 评审通过后冻结）  
更新时间：2026-04-16

> 本文用于定义 **Kernel 契约（Contracts）**，但需要分期冻结：
>
> - **Phase 1（已实现）**：只冻结最小可用的 `ExecutionRequest/ExecutionResult`（保证“单入口 execute”可上线）。
> - **Phase 4+（待实现/待评审冻结）**：再冻结完整的 4 核心对象（ExecutionRequest / PromptContext / ExecutionPlan / ExecutionResult）与 syscalls 的结构化输入输出。
>
> 这样做的原因：当前仓库代码中 `core/harness/kernel/types.py` 仍是 Phase-1 minimal（见下文 1.2），如果现在按“完整冻结契约”验收会与实现不一致。

---

## 1. 代码落点（To-Be）

### 1.1 Phase 1（As-Is）落点

- `core/harness/kernel/types.py`：**已存在**（Phase-1 minimal）
- `core/harness/integration.py`：Kernel 单入口执行与返回结构（run_id/trace_id）

### 1.2 Phase 4+（To-Be）落点

建议扩展并最终冻结在：`core/harness/kernel/types.py`

并提供：
- `to_dict()/from_dict()`（用于落库/回放）
- pydantic/typing 方案二选一（建议：pydantic v2 以便 API 层复用；Kernel 内部可用 dataclass）

---

## 2. Phase 1：最小契约（已对齐实现）

> 目的：支撑 **“唯一入口：HarnessIntegration.execute”** 的迁移（见 05-migration-and-acceptance.md / Phase 1）。

### 2.1 ExecutionRequest（Phase 1 minimal）

代码对应：`core/harness/kernel/types.py::ExecutionRequest`

当前字段：
- `kind: Literal["agent","skill","tool","graph"]`
- `target_id: str`
- `payload: dict`
- `user_id/session_id/request_id`

### 2.2 ExecutionResult（Phase 1 minimal）

代码对应：`core/harness/kernel/types.py::ExecutionResult`

当前字段：
- `ok: bool`
- `payload: dict`
- `error: str | None`
- `http_status: int`
- `trace_id/run_id: str | None`

> 注：Phase 1 minimal 不包含 `status=approval_required` 的统一 ResultStatus 枚举；当前是由各执行路径在 payload/status 或 error 中表达，Phase 4+ 会统一收敛。

---

## 3. Phase 4+：完整契约（待实现/待冻结）

> 下述结构是 To‑Be 设计目标。**在代码实现完成并评审冻结前，不应作为“当前必须满足”的验收硬条件**。

## 3.1 ExecutionRequest（系统执行请求）

### 语义
来自 API/上层平台的“系统调用请求”。Kernel 会据此构建 PromptContext 并执行。

### 字段（建议最小集）
- `request_id: str`（若上层不传，Kernel 生成）
- `user_id: str`
- `session_id: str | None`
- `messages: list[Message]`（原始消息）
- `query: str | None`（可由 messages 推断）
- `preferred_agent: str | None`（指定 agent 类型/ID，若为空由 Orchestrator 决策）
- `tool_allowlist/tool_denylist: list[str] | None`
- `skill_allowlist/skill_denylist: list[str] | None`
- `attachments: list[Attachment] | None`（文件/URI/引用）
- `runtime: RuntimeHints`（模型、温度、预算、max_steps、timeout）
- `metadata: dict[str, Any]`

（待补充：Message/Attachment/RuntimeHints 的具体结构）

---

## 3.2 PromptContext（可执行上下文）

### 语义
Kernel 统一组装后的“执行上下文”。引擎只能消费 PromptContext，不得绕过自行拼装。

### 字段
- `messages: list[Message]`（已裁剪/压缩）
- `system_instructions: str`（系统提示、安全约束）
- `tool_schemas: list[ToolSchema]`
- `skill_schemas: list[SkillSchema]`
- `artifacts: dict[str, Any]`（文件摘要、检索结果、记忆召回、中间产物）
- `budgets: BudgetSpec`
  - `token_budget`
  - `compact_threshold`
  - `max_steps`
  - `timeout_ms`
- `prompt_template: str`（模板名）
- `prompt_version: str`（版本，用于回放）

---

## 3.3 ExecutionPlan（用户态编排输出）

### 语义
Orchestrator 的输出，只描述“怎么执行”，不直接执行副作用。

### 字段
- `plan_id: str`
- `plan_type: PlanType`（quick/reasoning/planning/parallel/hybrid/conservative）
- `engine_hint: EngineHint`（loop/langgraph/agentloop/auto）
- `steps: list[PlanStep]`（推理步骤/子任务，允许为空）
- `fallback_chain: list[EngineHint]`（如 ["langgraph","loop","quick"]）
- `constraints: dict[str, Any]`（禁用工具、预算上限、必须审批等）
- `explain: str`（必须记录：为何选这条路径）

---

## 3.4 ExecutionResult（Kernel 返回）

### 字段
- `status: ResultStatus`（completed/failed/approval_required/cancelled）
- `output: Any | None`
- `error: str | None`
- `trace_id: str`
- `run_id: str`
- `plan: ExecutionPlan | None`（用于回放）
- `token_usage: TokenUsage | None`
- `latency_ms: int | None`
- `tool_calls: list[ToolCallRecord]`（审计）
- `skill_calls: list[SkillCallRecord]`
- `metadata: dict[str, Any]`（压缩摘要、审批状态、fallback 轨迹等）

---

## 3.5 Syscalls 契约

> syscalls 由 Kernel 提供，任何实际副作用必须经过 syscalls。

### 6.1 sys_llm.generate
- 输入：`LLMRequest`
  - `messages` / `system` / `tools` / `output_contract` / `model_params` / `trace_context`
- 输出：`LLMResult`
  - `content` / `tool_calls` / `token_usage` / `latency_ms` / `raw`

### 6.2 sys_tool.call
- 输入：`ToolCall`
  - `name` / `args` / `user_id` / `session_id` / `trace_context` / `timeout_ms`
- 输出：`ToolResult`（沿用 harness.interfaces.ToolResult，并补齐审计字段）

### 6.3 sys_skill.call
- 输入：`SkillCall`
  - `name` / `args` / `user_id` / `session_id` / `trace_context` / `timeout_ms`
- 输出：`SkillResult`

---

## 4. 错误模型与状态机（Phase 4+ 冻结）

### 4.1 错误分类（建议）
- `INVALID_REQUEST`：入参不合法
- `POLICY_DENY`：权限不足/策略拒绝
- `APPROVAL_REQUIRED`：需要审批
- `TOOL_ERROR`：工具执行失败（含可重试/不可重试）
- `LLM_ERROR`：模型调用失败
- `TIMEOUT`：超时
- `INTERNAL`：未知错误

### 4.2 可重试标记
每个错误必须标注：
- `retryable: bool`
- `fallback_recommended: bool`

---

## 5. 版本策略（Phase 4+ 冻结）

- 新增字段：必须是可选字段，并保持默认行为不变
- 字段变更：通过 `vNext` 结构或双写字段过渡
- 旧执行记录回放：必须可用（至少保证 schema 兼容解析）

---

## 6. 评审检查清单

- [ ] ExecutionRequest 最小集能覆盖现有 API 入参？
- [ ] PromptContext 足以让 Loop/Graph 不再自行拼装？
- [ ] ExecutionPlan 能表达 RANGEN 的关键路径（Quick/Reasoning/Parallel/Hybrid）？
- [ ] ExecutionResult 满足审计/回放/评估所需字段？
- [ ] syscalls 入参出参能支撑 gates 的不可绕过实现？
