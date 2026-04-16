# aiPlat-core 内核化改造｜严格按文档逐条验收报告

更新时间：2026-04-16  
验收基线文档：`docs/design/kernel_orchestrator/*`（00~05 + README）

> 说明：本文以“设计文档方案”作为唯一验收标准，**逐条对照**当前仓库代码现状，给出 PASS / PARTIAL / FAIL，并附证据（文件与关键片段/调用点）。

---

## 0. 总结结论（按 Phase）

| Phase | 文档目标 | 结论 | 关键原因 |
|---|---|---|---|
| Phase 1 | 单入口 Integration.execute | PASS | server 执行路由已收敛到 `harness.execute()`，Integration 生成 run_id/trace_id 并落库 agent/skill/graph/tool 执行记录 |
| Phase 2 | syscalls 封口（llm/tool/skill）+ “不可绕过” | FAIL | 虽已新增 syscalls 并在 Loop/LangGraph nodes/SkillExecutor/Integration 等接入，但 **静态扫描仍存在多处直接 `_model.generate()`/`tool.execute()`**（见 2.2） |
| Phase 3 | 四大 Gate 下沉（Policy/Trace/Context/Resilience） | PARTIAL | Gate 骨架 + syscalls 接入完成；审批/审计/恢复链路完成；但 **ContextGate/ResilienceGate 仍为最小实现**，且“span 完整率/重试策略/回退链”未按文档量化验收 |
| Phase 4 | ContextAssembler + PromptAssembler 收敛 | FAIL | `core/harness/assembly/*` 不存在；Loop/Graph 仍在自行拼 prompt；未实现 prompt_version 落库契约 |
| Phase 5 | Orchestrator + EngineRouter + fallback 链（只产 plan） | FAIL | `core/orchestration/*`、`core/harness/execution/engines/*`、`router.py` 不存在；ExecutionPlan/PromptContext 契约未落地 |
| Phase 6 | 自学闭环（evaluation/feedback/evolution） | FAIL | 未实现 |

结论：**严格按文档验收：仅 Phase 1 通过；Phase 3 部分通过；其余未通过。**

---

## 1. 文档 00｜总体架构北极星约束（00-architecture.md）

### 1.1 唯一执行入口：`HarnessIntegration.execute(request)`
- 期望（文档）：server 侧所有执行类 route 必须统一转发到 `HarnessIntegration.execute`。
- 结论：PASS
- 证据：
  - `core/server.py` 多个路由使用 `harness = get_harness(); result = await harness.execute(exec_req)`（grep 可见多处）
  - `core/harness/integration.py` 存在 `class HarnessIntegration` 且实现 `async def execute(...)`

### 1.2 系统调用封口：`sys_llm/sys_tool/sys_skill`
- 期望：所有副作用入口必须经 syscalls。
- 结论：FAIL（严格静态扫描）
- 证据见 2.2（Phase 2 静态扫描）。

### 1.3 四大 Gate 必经：Policy/Trace/Context/Resilience
- 期望：Gate 在 Kernel 层强制装配，任何 engine/agent 不拥有独立 Permission/Trace/Retry 逻辑。
- 结论：PARTIAL
- 证据：
  - 已新增：`core/harness/infrastructure/gates/{policy,trace,context,resilience}_gate.py`
  - 已接入：syscalls 内使用 gates（见 syscalls 文件）
  - 不足：ContextGate/ResilienceGate 为最小实现；“EngineRouter + fallback 链”未落地（Phase 5）

---

## 2. 文档 05｜分期迁移与验收（05-migration-and-acceptance.md）

### 2.1 Phase 1（P0）：单入口（Integration.execute）

**验收点 A：100% 执行请求有 run_id/trace_id**
- 结论：PARTIAL（代码支持，但未做 100% 运行时统计验证）
- 证据：
  - `core/harness/integration.py`：agent/skill/graph 逻辑均创建 `trace_id` 并在返回 `ExecutionResult(... trace_id=..., run_id=...)`。

**验收点 B：ExecutionStore 至少记录 request 元信息与最终状态**
- 结论：PASS（agent/skill/graph/tool 均 best-effort upsert）
- 证据：
  - `core/services/execution_store.py`：`agent_executions`、`skill_executions`、`graph_runs` 表与 upsert 方法存在。

**回滚：feature flag 保留旧 handler**
- 结论：FAIL（未发现 feature flag / 旧 handler 回滚开关）
- 证据：
  - 仓库中未找到 `.pre-commit-config.yaml`、`.github/workflows/*`、亦未找到 `feature flag`/`ROLLBACK` 相关实现（需额外实现）

### 2.2 Phase 2（P0）：syscalls 封口（llm/tool/skill）

**验收点 A：新增 syscalls 模块**
- 结论：PASS
- 证据：
  - `core/harness/syscalls/{llm,tool,skill}.py` 存在并被 Loop/LangGraph/SkillExecutor/Integration 引用

**验收点 B：主路径中直接 `tool.execute/adapter.generate/skill.execute` 调用为 0（静态扫描）**
- 结论：FAIL
- 证据（示例，均为仓库现存直接调用）：
  1) `core/apps/agents/plan_execute.py`
     - 直接 `await self._model.generate(...)`（规划与执行步骤）
     - 直接 `await tool.execute({})`
  2) `core/apps/agents/rag.py`
     - 直接 `await self._model.generate(...)`
  3) `core/apps/agents/conversational.py`
     - 直接 `await self._model.generate(messages)`
  4) `core/apps/mcp/server.py`
     - 直接 `await tool.execute(arguments)`（MCP tools/call 分支）
  5)（测试文件）`core/tests/unit/test_tools/test_tool_tracking.py` 也包含 `tool.execute`（可视为允许，但文档要求“静态扫描为 0”则仍不满足）

**验收点 C：syscall 记录 span（哪怕 gate 先最小实现）**
- 结论：PASS（best-effort）
- 证据：
  - `core/harness/infrastructure/gates/trace_gate.py` + syscalls 内 `TraceGate.start/end(...)`

### 2.3 Phase 3（P0）：四大 Gate 下沉 Kernel

**验收点 A：Tool 调用权限检查覆盖率 100%**
- 结论：PARTIAL（sys_tool 内强制 RBAC；但仍有非 sys_tool 的直接 tool.execute 调用点存在，导致整体覆盖率无法声称 100%）
- 证据：
  - `core/harness/syscalls/tool.py`：`PolicyGate.check_tool(...)` + `PermissionManager.check_permission(...)`
  - 反证：见 2.2 中的 `core/apps/mcp/server.py` 直接 `tool.execute(...)`

**验收点 B：敏感操作审批命中可观测**
- 结论：PARTIAL
- 证据：
  - `core/server.py` 注册 `ApprovalRule(rule_id="sensitive-ops", metadata.sensitive_operations=[...])`
  - `core/services/execution_store.py`：`approval_requests`、`syscall_events`、`approval_request_id` 关联索引、`/approvals/*` 审计聚合接口
- 不足：
  - 默认策略（SAFE/SENSITIVE/DANGEROUS 的默认 allow/approve/deny）未完整实现为“策略必经”（目前更多是标签/队列排序用途）

**验收点 C：Trace：syscalls span 完整率 ≥ 99%**
- 结论：FAIL（未做量化统计与集成测试）
- 说明：代码层面具备 span 记录路径，但缺少指标统计与自动验收测试。

**验收点 D：Retry：可重试错误具备统一策略**
- 结论：FAIL（ResilienceGate 为最小 retry/timeout wrapper，尚未形成策略体系与回退链）
- 证据：
  - `core/harness/infrastructure/gates/resilience_gate.py` 仅提供最小 `run(...)`

### 2.4 Phase 4（P1）：ContextAssembler + PromptAssembler
- 结论：FAIL
- 证据：
  - `core/harness/assembly/*` 目录不存在（文档要求新增）
  - `core/harness/infrastructure/gates/context_gate.py` 为占位 no-op
  - `core/harness/kernel/types.py` 仍是 Phase-1 minimal，不含 `PromptContext/prompt_version` 契约

### 2.5 Phase 5（P1）：Orchestrator（只产 plan）+ EngineRouter + fallback
- 结论：FAIL
- 证据：
  - `core/orchestration/*` 不存在
  - `core/harness/execution/engines/*` 不存在
  - `docs/design/kernel_orchestrator/03-engines-and-routing.md` 中要求的 `IExecutionEngine/EngineRouter/fallback_chain` 未落地

### 2.6 Phase 6（P2）：自学闭环
- 结论：FAIL

---

## 3. 文档 01｜核心契约与数据模型（01-contracts.md）

期望：冻结以下契约并落到 `core/harness/kernel/types.py`：
- ExecutionRequest / PromptContext / ExecutionPlan / ExecutionResult
- syscalls 入参出参结构（LLMRequest/ToolCall/SkillCall 与 Result）
- 错误模型、状态机与版本策略

结论：FAIL（当前仅存在 Phase-1 minimal types）

证据：
- `core/harness/kernel/types.py` 仅包含：
  - `ExecutionRequest(kind,target_id,payload,...)`
  - `ExecutionResult(ok,payload,error,http_status,trace_id,run_id)`
- 缺少：
  - `PromptContext`、`ExecutionPlan`、`ResultStatus`、`ToolCallRecord` 等文档冻结结构

---

## 4. 文档 02｜Syscalls 与 Gates 设计（02-syscalls-and-gates.md）

### 4.1 syscalls 与 gates 文件落点
结论：PASS  
证据：对应文件均已存在：  
`core/harness/syscalls/*`、`core/harness/infrastructure/gates/*`

### 4.2 “不可绕过保证”（CI 静态扫描 + 结构约束）
结论：FAIL  
证据：
- 文档要求 pre-commit + CI 扫描规则；仓库未发现：
  - `.pre-commit-config.yaml`
  - `.github/workflows/*`
- 且静态扫描确实发现绕过点（见 2.2）。

---

## 5. 文档 04｜安全、审批与审计（04-security-and-audit.md）

### 5.1 Tool/Skill 危险等级标签（ToolConfig.metadata）
结论：PARTIAL  
证据：
- 已为多工具补充 `ToolConfig.metadata.risk_level/risk_weight`（例如 code/database/file_operations/http/browser/webfetch）
- 但 Skill 侧尚未做同等标签体系与默认策略落地

### 5.2 审批“只能由 PolicyGate 触发与判断”
结论：PARTIAL  
证据：
- `core/harness/infrastructure/gates/policy_gate.py` 已在 sys_tool 前强制调用
- Loop 内的 `_approval_check()` 已在 `AIPLAT_SYSCALL_ENFORCE_APPROVAL=true` 时跳过（避免双重审批）
- 但：仍存在非 sys_tool 的 tool.execute 调用点，可能绕过 PolicyGate（见 2.2）

### 5.3 审计字段与落库要求（ExecutionStore）
结论：PARTIAL  
证据（已实现/增强）：
- `syscall_events`（含 approval_request_id 关联）
- `approval_requests` 持久化
- agent/skill 执行记录持久化（含 metadata_json）
- `/approvals/{id}` 返回 related（agent_executions + syscall_events）
不足（文档要求但未完成）：
- prompt_template/prompt_version 的统一落库与回放
- 脱敏策略（masking/hash/摘要）未实现

### 5.4 CI/Hook 防绕过规则
结论：FAIL（同 4.2）

---

## 6. 建议的“补齐项”清单（为了让验收从 FAIL→PASS）

按优先级排序：

1) **Phase 2 静态扫描归零（硬要求）**
   - 把 `core/apps/agents/{plan_execute,rag,conversational}.py` 内部的 `_model.generate/tool.execute` 全部迁移到 syscalls（或明确移除/隔离为非主链路并在 CI 扫描中豁免目录）
   - `core/apps/mcp/server.py` 的 tools/call 必须改走 `sys_tool_call`（并注入 user_id/session_id）

2) **补齐 CI 静态扫描（不可绕过）**
   - 增加 pre-commit hook + CI job：
     - server/orchestration/engines 层禁止 `tool.execute/adapter.generate/skill.execute`
     - 允许名单：`core/harness/syscalls/*`、测试目录（若决定豁免）

3) **补齐 contracts（01-contracts）**
   - 扩展 `core/harness/kernel/types.py`：引入 PromptContext/ExecutionPlan/ResultStatus + syscall contract types

4) **Phase 4/5/6 按文档补齐模块**
   - `core/harness/assembly/*`
   - `core/harness/execution/engines/*` + `router.py`
   - `core/orchestration/*`
   - evaluation/feedback/evolution

---

## 7. 本报告输出

本报告为“严格按文档”静态验收结论；如需“运行时量化验收”（span 完整率、落库完整率、p95 回归等），需要补充：
- 启动服务并跑集成测试/压测脚本
- 统计 ExecutionStore 与 TraceService 的指标输出

