---
title: 平台化（多租户/企业）路线：PR 拆解与 2-3 周排期
date: 2026-04-18
scope: aiPlat-core + aiPlat-management（并明确需要新增/对接的 platform/app 服务能力）
---

> 你已经把“执行内核（harness/syscalls）+ 观测（trace/syscalls/executions）+ 学习（learning artifacts）”做成骨架了。  
> 平台化下一阶段的关键：**把 tenant/identity/policy/audit/approval/run lifecycle 做成一等公民**，再把记忆/技能/插件全部挂在这条“治理主链”上。

## 0. 约定：统一名词与 Header

### 0.1 核心上下文（必须贯穿全链路）
- tenant_id：租户
- actor：发起人（user/service），至少要有 `actor_id` + `actor_role`
- session_id：会话（用于串行化 lane、记忆、审计关联）
- run_id：一次执行（对齐你们现有 trace_id / execution_id / run_id 的混用，统一为 run_id）
- trace_id：观测链路
- target：`target_type` + `target_id`（agent/skill/tool/job/gateway）
- entry：`entrypoint`（ui/api/gateway/cron/webhook…）

### 0.2 建议的请求头（先在 management→core proxy 里打通）
- `X-AIPLAT-TENANT-ID: t_xxx`
- `X-AIPLAT-ACTOR-ID: u_xxx`（或从 JWT claim 解析）
- `X-AIPLAT-ACTOR-ROLE: admin|operator|developer|viewer`
- `X-AIPLAT-REQUEST-ID: req_xxx`（幂等/审计）

> 备注：目前前端已有 Platform/Tenant/Auth 页面，但它们调用的是 `/platform/*` 路由（见 `frontend/src/services/platformAppApi.ts`），这些通常属于独立的 **aiPlat-platform** 服务；本文件会明确哪些 PR 在 core/management 内完成，哪些需要 platform/app 服务补齐或对接。

> 更新：当前平台已存在 aiPlat-platform 与 aiPlat-app，且调用链为 **app → platform → core**（app 不直连 core）。更完整的四服务版拆解见：`平台化路线-四服务版PR拆解与排期.md`，以及三份冻结规范：
> - `规范-platform-鉴权与身份透传.md`
> - `规范-app-session_id与conversation_key.md`
> - `规范-core-run_id-trace_id-request_id.md`

---

## 1) PR 列表（14 个 PR，按依赖顺序）

> 每个 PR 都给出：目标 / 代码改动（文件清单）/ DB 迁移 / 测试 / 回滚开关 / 依赖。

### PR-01：Tenant/Actor Context 注入（全链路打底）
**目标**
- core 能从请求获取 tenant/actor，并传入 harness → syscalls → execution_store
- management 代理把 tenant header 透传（先不强制鉴权）

**代码改动（建议）**
- aiPlat-core
  - `core/server.py`：新增依赖注入函数 `get_request_context()`，写入 request.state
  - `core/harness/kernel/execution_context.py`：扩展 ActiveRequestContext（tenant_id/actor_id/actor_role/entrypoint）
  - `core/harness/integration.py`：构造 ExecutionRequest 时写入 metadata/context
  - `core/services/execution_store.py`：关键表补 tenant_id（见迁移）
- aiPlat-management
  - `management/core_client.py`：为所有 core 代理请求增加 tenant header（从 management 自己的 header 透传）
  - `management/api/core.py`：透传 `X-AIPLAT-*` headers
- frontend（最小）
  - `frontend/src/services/apiClient.ts`：允许配置并附带 `X-AIPLAT-TENANT-ID`（先从 localStorage 读取 `active_tenant_id`）

**DB 迁移**
- `ExecutionStore.CURRENT_SCHEMA_VERSION += 1`
- 增加列（best-effort ALTER）：
  - `agent_executions.tenant_id`
  - `skill_executions.tenant_id`
  - `tool_executions.tenant_id`
  - `syscall_events.tenant_id`（你们已做维度扩展，可继续加）
  - `jobs/job_runs/job_delivery_*`（如需要按 tenant 分离 job）

**测试**
- core：新增 `core/tests/integration/test_tenant_context_propagation.py`
- management：新增一个 proxy test（MockTransport 检查 header 透传）
- frontend：`npm run build`

**回滚**
- `AIPLAT_TENANCY_MODE=off|permissive|enforced`（默认 permissive：缺 tenant 时走 `default`）

**依赖**：无

---

### PR-02：Run Contract v2（统一 run_id + 状态机）
**目标**
- 对外统一：`{ ok, run_id, trace_id, status, output, error{code,message}, ... }`
- 状态机对齐：accepted/running/waiting_approval/completed/failed/aborted/timeout

**代码改动**
- aiPlat-core
  - `core/schemas.py`：定义 Run 相关 schema（RunStatus、RunSummary）
  - `core/server.py`：执行类 API 返回统一 RunSummary（agent/skill/tool/gateway/jobs）
  - `core/harness/integration.py`：统一生成 run_id（复用现有 execution_id/run_id）并写入 record
  - `core/services/execution_store.py`：execution 表记录 `status` 与 `error_code`
- aiPlat-management
  - frontend：所有 Execute*Modal 统一消费 `error` 对象（你已做一部分）

**测试**
- core：contract test 覆盖 3 类入口：agent/skill/tool 的成功/失败/approval_required
  - 新增 `core/tests/integration/test_run_contract_v2.py`

**回滚**
- 保留 `error_message/error_detail` 兼容字段（至少 1 个版本周期）

**依赖**：PR-01

---

### PR-03：Run Events（轮询版）+ wait
**目标**
- 平台控制面能“看进度”：run_start/tool_start/tool_end/approval_requested/run_end
- 先做 HTTP polling（企业环境最通用），后续可升级 SSE/WebSocket

**代码改动**
- aiPlat-core
  - `core/services/execution_store.py`
    - 新表：`run_events(run_id, seq, type, payload_json, created_at, tenant_id, trace_id)`
    - API：`append_run_event(...)`、`list_run_events(run_id, after_seq)`
  - `core/harness/integration.py`：写 run_start/run_end
  - `core/harness/syscalls/tool.py`：写 tool_start/tool_end + error_code
  - `core/harness/infrastructure/approval/manager.py`：approval_requested/approved/rejected
  - `core/server.py`：新增
    - `GET /runs/{run_id}`
    - `GET /runs/{run_id}/events?after_seq=...`
    - `POST /runs/{run_id}/wait`（长轮询：等待 end/error 或超时）
- aiPlat-management
  - `management/api/diagnostics.py`：增加 runs 代理（可复用 core proxy）
  - frontend：Links 页加一个 “Run Events” tab（可后置到 PR-06）

**测试**
- core：`core/tests/integration/test_run_events_polling.py`

**回滚**
- 事件写入 best-effort；接口可开关 `AIPLAT_RUN_EVENTS=0`

**依赖**：PR-02

---

### PR-04：Session Lane 队列（per-session 串行）+ queue mode（collect/followup/steer）
**目标**
- 同 session 只允许一个 active run
- 多入口消息不会并发踩状态；为企业 IM/工单系统接入打底

**代码改动**
- aiPlat-core
  - `core/services/execution_store.py`：新增 `session_locks` 或复用现有锁模式（类似 job_run lock）
  - `core/harness/integration.py`：execute 前获取 session lock；排队时写 run.status=queued + run_event=queued
  - `core/server.py`：gateway 入口支持 `queue_mode`（默认 collect）
- aiPlat-management
  - frontend：Diagnostics/Links 增加 queued 原因展示（从 run_events）

**测试**
- core：并发测试（同 session 两个执行，一个 running，一个 queued）

**回滚**
- `AIPLAT_SESSION_QUEUE_ENABLED=0` 直接回到旧行为

**依赖**：PR-03

---

### PR-05：RBAC（最小企业权限模型）
**目标**
- 把“谁能执行什么”变成强约束（tenant+actor+role）
- 覆盖：execute / policy / approvals / gateway tokens / jobs

**代码改动**
- aiPlat-core
  - 新增模块：`core/security/rbac.py`（角色、资源、动作）
  - `core/server.py`：为关键 endpoint 加权限校验（403 + error_code=FORBIDDEN）
  - `core/apps/tools/permission.py`：与 RBAC 对齐（你已存在 permission 工具，可整合）
- aiPlat-management
  - 仅做 UI 提示：未授权时提示“联系管理员申请权限”

**测试**
- core：`test_rbac_denies_execute.py`

**回滚**
- `AIPLAT_RBAC_MODE=warn|enforced`（先 warn-only）

**依赖**：PR-01/02

---

### PR-06：Audit Logs（企业审计台账）
**目标**
- 任何敏感行为都可追责：谁、何时、对哪个资源、做了什么、结果如何、关联 run/trace

**代码改动**
- aiPlat-core
  - `core/services/execution_store.py`：新表 `audit_logs(...)`
  - `core/server.py`：在写操作（创建/删除/更新/execute/approve）写审计
  - `core/harness/syscalls/tool.py`：将关键工具调用写审计（可只写高风险）
- aiPlat-management
  - backend：新增 `/api/core/audit/*` 代理（management/api/core.py 或 diagnostics.py）
  - frontend：新增页面 `pages/Diagnostics/Audit/Audit.tsx`（列表+过滤：tenant/actor/action/run_id）

**测试**
- core：`test_audit_log_on_execute_and_approval.py`
- frontend：build

**回滚**
- `AIPLAT_AUDIT_MODE=best_effort|required`（默认 best_effort）

**依赖**：PR-01/03

---

### PR-07：Policy-as-code（统一策略引擎）
**目标**
- 把各处散落的“deny/warn/approval_required”收敛为统一决策：policy_engine
- 策略可按 tenant 配置并版本化

**代码改动**
- aiPlat-core
  - 新增：`core/policy/engine.py`（输入：tenant/actor/target/tool/args/context；输出：decision+reason_code+metadata）
  - `core/harness/syscalls/tool.py`：工具调用前统一走 policy_engine（替代/增强现有 PolicyGate）
  - `core/harness/context/engine.py`：project context policy 也走 policy_engine（替代 env-only）
  - `core/apps/mcp/runtime.py`：prod/stdio deny 也走 policy_engine（并产出一致审计）
  - `core/server.py`：新增 policy CRUD（tenant 级）
    - `GET/PUT /policy/snapshot`
    - `GET /policy/versions`
- aiPlat-management
  - frontend：新增 `pages/Platform/Policy/Policy.tsx`（或挂在 Tenant 里）

**DB 迁移**
- `policy_snapshots(tenant_id, version, json, created_at, created_by)`

**测试**
- core：`test_policy_engine_decisions.py`

**回滚**
- `AIPLAT_POLICY_ENGINE=0` 回退到旧 gate（但保留审计）

**依赖**：PR-05/06

---

### PR-08：Approval Hub（审批中心产品化 + 回放）
**目标**
- 审批请求标准化（带执行计划 systemRunPlan / filePlan / externalAccess）
- 审批通过后可回放（replay）并继续 run

**代码改动**
- aiPlat-core
  - `core/harness/infrastructure/approval/manager.py`：扩展 ApprovalContext/Request schema
  - `core/server.py`：新增 approvals API（list/get/resolve/replay）
  - `core/services/execution_store.py`：审批表增加 tenant_id/actor_id + 与 run_events 联动
- aiPlat-management
  - 已有 `pages/Core/Learning/Approvals`，建议新增独立 `pages/Platform/Approvals/Approvals.tsx` 做企业审批
  - 或复用现有 Approvals 页，但增加 tenant/actor/plan 展示

**测试**
- core：`test_approval_required_then_resolve_then_resume.py`

**回滚**
- 审批强制由 policy 控制；审批中心仅 UI/API

**依赖**：PR-03/06/07

---

### PR-09：企业版 Memory（分层 + 可控注入）
**目标**
- 记忆必须可解释、可删除、可禁用、可脱敏（合规）

**代码改动**
- aiPlat-core
  - `core/services/execution_store.py`
    - 为 memory_messages 增加 tenant_id、sensitivity、source_run_id
    - 新表：`memory_pins` / `memory_blocks`（可选）
  - `core/harness/assembly/prompt_assembler.py`：把“检索注入”独立成 overlay block，并带引用来源
  - hooks：新增 `HookPhase.RESULT_PERSIST` / `HookPhase.MEMORY_WRITE`（或复用现有 phase 扩展）
- aiPlat-management
  - frontend：增强 `pages/Core/Memory/Memory.tsx`：增加 tenant 过滤、删除、Pin、引用来源展示

**测试**
- core：`test_memory_search_and_prompt_injection_with_sources.py`

**回滚**
- `AIPLAT_MEMORY_AUTO_INJECT=0`（只保留 search API，不注入 prompt）

**依赖**：PR-01/06/07

---

### PR-10：Skill 自进化闭环（审核→发布→灰度→回滚→指标）
**目标**
- 从“能生成草案”升级到“企业可运营”

**代码改动**
- aiPlat-core
  - `core/server.py`：release 发布支持 tenant scope + 灰度策略（user/channel比例）
  - `core/services/execution_store.py`：新增 `release_rollouts`、`release_metrics_snapshots`
  - `core/apps/skills/evolution/*`：把 skill_evolution 草案转成可应用 patch（SOP/frontmatter）
- aiPlat-management
  - 复用 `pages/Core/Learning/Releases`：增加 rollout 配置、指标对比展示
  - ArtifactDetail：对 skill_evolution 增加“一键生成 patch & 走发布”

**测试**
- core：`test_release_rollout_and_metrics_snapshot.py`

**回滚**
- 强制保留 rollback；发布只改“引用版本”，不破坏历史

**依赖**：PR-06/07/09

---

### PR-11：Workflow/Plugin 框架（企业化 Claude Code 路线）
**目标**
- 把“工作流（commands+agents+hooks）”打包分发，并受 policy/审计约束

**代码改动**
- aiPlat-core
  - 新模块：`core/apps/plugins/*`（manifest、install、enable、run）
  - 插件声明：需要 toolset、风险级别、默认 policy
  - 插件运行也写 run_events + audit_logs
- aiPlat-management
  - 新页面：`pages/Core/Plugins/Plugins.tsx`（安装/启停/版本）

**测试**
- core：插件安装、执行、审计写入

**依赖**：PR-07/06

---

### PR-12：Connector 标准化（企业 IM 接入）
**目标**
- Slack/飞书/Teams 等入口统一 connector interface：event → identity/session → run → delivery（含 DLQ）

**代码改动**
- aiPlat-core
  - `core/apps/connectors/*`：slack/feishu skeleton
  - gateway：pairing/tokens 与 tenant/actor 打通（你已有 pairing 表，补 tenant/role）
  - delivery：统一回包模板（ack/stream/final）
- aiPlat-management
  - Gateway 页面：补“connector 配置健康检查 + delivery DLQ”联动入口

**测试**
- core：connector integration test（slack 已有，可扩展到 “identity->session->run->delivery”）

**依赖**：PR-04/05/08

---

### PR-13：Tenant Quotas（并发/成本/工具调用配额）
**目标**
- 企业必须控成本与滥用：并发 run、LLM token、tool call 次数、外部访问次数

**代码改动**
- aiPlat-core
  - `core/services/execution_store.py`：usage ledger（tenant/day）
  - `core/policy/engine.py`：配额超限 → QUOTA_EXCEEDED
  - `core/server.py`：quota 设置/查询 API（tenant 管理）
- aiPlat-management
  - Tenant 页面：显示 usage 与 quota，支持调整

**测试**
- core：`test_quota_exceeded_blocks_run.py`

**依赖**：PR-07/01

---

### PR-14：运维收尾（SLO/健康检查/导出/保留期）
**目标**
- 企业上线必须：健康检查、导出、数据保留期（合规）

**代码改动**
- aiPlat-core
  - `/healthz` 增强：db/queue/dlq/mcp/connector status
  - `execution_store`：按 tenant retention 清理任务（cron/job）
  - 导出：audit_logs/run_events/learning artifacts 导出 API
- aiPlat-management
  - Infra/Monitoring 增加 core 维度：queue depth、dlq depth、approval backlog

**测试**
- integration：export/retention job

**依赖**：PR-06 起

---

## 2) 2-3 周迭代节奏（建议：每个 Sprint 2 周）

> 下面给一个“平台化 MVP → 强化治理 → 生态化”的 3 个 Sprint（6 周）排期。  
> 你如果要压到更快，可以把 Sprint-1 的 PR-01~03 合并成一个“大 PR”，但会牺牲可回滚性与 code review 质量。

### Sprint-1（第 1-2 周）：把“多租户+Run语义+事件流”打通（平台最小可用）
- PR-01 Tenant/Actor Context
- PR-02 Run Contract v2
- PR-03 Run Events + wait

交付验收（Sprint-1）
- management UI 能按 tenant 发起一次执行，并在 Links 中看到 run_id/trace_id
- 能轮询到 run_events（至少 start/end/tool 事件）

### Sprint-2（第 3-4 周）：一致性与治理（队列/RBAC/审计）
- PR-04 Session lane 队列
- PR-05 RBAC 最小模型（先 warn-only）
- PR-06 Audit Logs + 审计 UI

交付验收（Sprint-2）
- 同 session 不并发
- 审计页可查“谁执行了什么、结果如何、关联 run/trace”

### Sprint-3（第 5-6 周）：策略与审批中心（企业真正敢用）
- PR-07 Policy-as-code
- PR-08 Approval Hub（含回放）
- PR-13 Quotas（先 report-only）

交付验收（Sprint-3）
- 策略可配置：deny/approval_required/warn 统一生效
- 审批中心能看到 plan，并能 approve 后恢复 run
- 配额超限有明确 error_code

### Sprint-4+（后续）：记忆/技能/插件/连接器（增强竞争力）
- PR-09 企业 Memory
- PR-10 Skill 自进化运营闭环
- PR-11 Workflow/Plugin
- PR-12 Connector 标准化
- PR-14 运维收尾

---

## 3) 需要你确认/补齐的“外部服务边界”

你现在仓库里明确存在：`aiPlat-core` + `aiPlat-management`。  
但前端已有 `/platform/*` 与 `/app/*` 路由（见 `frontend/src/services/platformAppApi.ts`），这意味着通常还有：
- aiPlat-platform（tenant/auth/gateway routes 等）
- aiPlat-app（channels/sessions 等）

**建议做法（平台化路线）**
- PR-01~08 主要落在 aiPlat-core（执行治理）+ management（控制面）即可。
- platform/app 若暂时不存在，可先在 management 里做“轻量 adapter”（把 tenant/auth 暂时当静态配置），等独立服务就绪再切换。
