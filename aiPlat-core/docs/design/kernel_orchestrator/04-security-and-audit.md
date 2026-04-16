# 04｜安全、审批与审计（Security / Approval / Audit）

状态：草案（审批/审计主链路已对齐实现；脱敏与 CI 仍待补齐后再冻结）  
更新时间：2026-04-16

---

## 0. 现状对齐（As-Is vs To-Be）

已实现（As-Is，代码已落地）：
- RBAC：`core/apps/tools/permission.py` + `PolicyGate` 在 `sys_tool_call` 前强制校验
- 审批：
  - `ApprovalManager` 已支持请求生命周期（pending/approved/rejected/expired…）
  - 审批请求已持久化：ExecutionStore `approval_requests` 表（跨重启可恢复）
  - 触发点收敛到 PolicyGate（配合 `AIPLAT_SYSCALL_ENFORCE_APPROVAL=true`）
- 审计：
  - syscall 级别事件表：ExecutionStore `syscall_events`（含 `approval_request_id` 关联索引）
  - agent/skill 执行记录：`agent_executions` / `skill_executions`（含 metadata_json）
  - 审批审计聚合 API：`GET /approvals/{id}` 返回 related（agent_executions + syscall_events）
- 风险标签：
  - ToolConfig.metadata 已补充 `risk_level/risk_weight`（用于审批记录与队列优先级）

未实现/仍需补齐（冻结前置条件）：
- 脱敏策略（args/output masking、文件内容 hash/摘要落库）
- 不可绕过 CI 静态扫描（pre-commit + CI job），目前仍存在绕过点（agents/mcp server）
- 默认策略强制（例如 DANGEROUS 默认 deny + allowlist + 审批）：目前更多是“标签+队列排序”，未形成统一强制策略体系

## 1. 目标

- 让安全与合规成为 Kernel 的一等公民：任何路径不可绕过
- 把“权限+审批+审计”与 sys_tool/sys_llm/sys_skill 深度绑定
- 形成可验证的 CI 约束，防止未来回归分叉

---

## 2. 安全资产分类（建议）

资产类别：
- Agent（执行策略主体）
- Skill（可复用子程序）
- Tool（对外部世界的副作用 / I/O）
- MCP（外部工具提供者/插件协议）

建议 Tool/Skill 增加危险等级标签（可落到 ToolConfig.metadata）：
- `SAFE`：无副作用或可逆
- `SENSITIVE`：读敏感数据/写文件/执行代码/外部网络
- `DANGEROUS`：数据库写入/系统命令/大规模删除/权限变更

As-Is（已落地示例）：
- `core/apps/tools/code.py`：`metadata.risk_level="dangerous", risk_weight=40`
- `core/apps/tools/database.py`：`metadata.risk_level="dangerous", risk_weight=50`
- `core/apps/tools/base.py::FileOperationsTool`：`metadata.risk_level="sensitive", risk_weight=30`
- `core/apps/tools/http.py/browser.py/webfetch.py`：已补充 risk 标签（用于审批队列优先级）

默认策略（建议）：
- SAFE：默认允许（但仍记录审计）
- SENSITIVE：默认需要审批或至少强审计
- DANGEROUS：默认禁止，除非明确白名单 + 审批

---

## 3. 权限模型（RBAC）与接入点

As-Is：
- `core/apps/tools/permission.py` 已提供 PermissionManager/RBAC

To-Be：
- PolicyGate 在 sys_tool.call 之前强制执行：
  - `check_permission(user_id, tool_name, EXECUTE)`
- 扩展：可对 skill/agent 也做 EXECUTE 权限（同一套 PermissionManager）

As-Is 映射：
- `core/harness/syscalls/tool.py`：sys_tool_call 内部强制 `PolicyGate.check_tool(...)`
- `core/harness/infrastructure/gates/policy_gate.py`：内部调用 `PermissionManager.check_permission(...)`

---

## 4. 审批模型（默认：同步阻塞 + 可恢复）

默认执行语义（Phase 1）：
- 命中审批规则：返回 `ExecutionResult(status="approval_required")`
- 上层平台审批后：重新调用 execute（携带 approval_token 或 checkpoint 引用）

可恢复执行需要的数据（必须落库）：
- run_id / trace_id
- 原始 ExecutionRequest（或可重建的引用）
- 已执行到哪一步（step_count）
- 审批请求内容（tool_name/args/理由/危险等级）

As-Is 依赖：
- `core/harness/infrastructure/approval/*`

To-Be 约束：
- 审批只能由 PolicyGate 触发与判断
- Tool/Engine 不得自己实现审批逻辑（避免分叉）

As-Is 映射（已落地）：
- 审批触发：`core/harness/infrastructure/gates/policy_gate.py`
- 审批持久化：`core/services/execution_store.py`（`approval_requests` 表，schema v8）
- 审批 API（运营与集成）：
  - `GET /approvals/pending`（支持排序/分页/priority_score）
  - `GET /approvals/{request_id}`（附带 related 审计信息）
  - `POST /approvals/{request_id}/approve|reject`
- 可恢复执行（resume）：
  - agent 执行遇到 `approval_required` 会 PAUSED 并返回 `approval_request_id`
  - `POST /agents/executions/{execution_id}/resume`：批准后从 `loop_state_snapshot` 继续（无快照则 replay）
  - PolicyGate 支持 `_approval_request_id`：已批准则放行（resume 语义）

---

## 5. 审计字段与落库要求（ExecutionStore）

必须记录（建议最小集合）：
- 请求：user_id/session_id/request_id
- 决策：plan_type/engine/fallback_chain + explain
- prompt：prompt_template/prompt_version + 压缩摘要（不要落全量敏感内容）
- 工具调用：tool_name/args（脱敏策略）/结果摘要/latency/错误
- 审批：命中规则、审批状态、审批人、审批时间
- trace：trace_id + spans 摘要

脱敏策略（待评审定义）：
- 对 args/output 中的敏感字段做 masking
- 对文件内容只落 hash/摘要

As-Is（已落地表与关联）：
- `agent_executions`：
  - `metadata_json`（schema v7）
  - `approval_request_id`（schema v9，用于一跳关联审批）
- `skill_executions`：
  - `metadata_json`（已对齐写入/读取）
- `syscall_events`（schema v6 + v9）：
  - 记录 kind/name/status/args/result/error
  - `approval_request_id` 列与索引（便于审计聚合）
- `approval_requests`（schema v8）：
  - request 生命周期持久化（跨重启）

---

## 6. MCP 安全接入策略（作为 ToolProvider）

目标：
- MCP 工具必须以 Tool 的形态进入 ToolRegistry，并继承同样的 Policy/Trace/Retry 语义

约束：
- MCP client 调用只允许发生在 Tool 实现内部（通过 sys_tool 触发）
- 禁止 Agent/Engine 直接操作 MCP client

As-Is 风险提示：
- 当前 `core/apps/mcp/server.py` 的 `tools/call` 分支仍存在直接 `tool.execute(...)` 的调用点，严格意义上可绕过 PolicyGate/TraceGate（需按 02 文档的静态扫描清零要求修复）。

---

## 7. CI/Hook 规则（防绕过）

建议最少三类扫描：

1) server 层禁止直接执行：
- 禁止 `agent.execute(`、`loop.run(`、`graph.run(`、`tool.execute(`、`adapter.generate(`

2) orchestration 层禁止副作用：
- 禁止 `tool.execute(`、`adapter.generate(`、`skill.execute(`

3) engines 层禁止绕过 syscalls：
- 禁止 `tool.execute(`、`adapter.generate(`、`skill.execute(`

建议提供：
- pre-commit hook（本地阻止）
- CI job（合入阻止）

> 验收口径与可执行扫描命令详见：`02-syscalls-and-gates.md` / 6.2。

---

## 8. 评审检查清单

- [ ] 危险等级与默认策略是否合理且可落地？
- [ ] approval_required 的恢复执行字段是否定义齐全？
- [ ] 审计字段是否满足合规与回放需求，同时满足脱敏要求？
- [ ] CI 规则是否能有效阻止绕过？
