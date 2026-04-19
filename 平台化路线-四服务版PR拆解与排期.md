---
title: 平台化（多租户/企业）路线：四服务版 PR 拆解与排期（platform/app/core/management）
date: 2026-04-18
assumptions:
  identity: "用户端 JWT（SSO）为主；服务间 mTLS/服务凭证为主；API key 仅用于机器/集成身份（不承载复杂用户权限）"
  call_direction: "app → platform → core（app 不直连 core）"
  run_id_authority: "core 生成 run_<ulid>；platform 生成 request_id=req_<ulid> 做幂等与审计关联"
  session_rule: "aiPlat-app：ticket_id > thread_id > channel_user_id（企业场景防串话）"
---

> 你说 aiPlat-platform 与 aiPlat-app 都已存在。下面给出“最佳实践版”的四服务责任边界与 PR 拆解（按 2 周一个 Sprint），使平台具备：多租户、可审计、可审批、可灰度、可运营。
>
> **默认采用的最佳答案（可按你现状微调）：**
> 1) **platform** 统一鉴权（推荐 JWT），claims 含 tenant_id/actor_id/roles/scopes；  
> 2) **app → platform → core**：app 负责 channel/session，收到消息后调用 platform；platform 做统一鉴权/限流/路由后再调用 core 执行；  
> 3) **run_id 由 core 生成**：core 对 run lifecycle / run events / approvals / audit 负责权威。

---

## 1. 四服务职责边界（企业平台推荐）

### 1.1 aiPlat-platform（控制面 / 身份与租户权威）
- 租户：tenant CRUD、状态、配额（quota）权威来源
- 身份：用户/角色/权限（RBAC/Scopes）权威来源；签发 JWT 或 API key
- 入口路由：gateway routes、外部入口鉴权与限流策略（northbound）
- 对外输出：标准 claims / headers（tenant_id、actor、scopes、request_id）
- 作为 **统一编排层**：承接 app/management 的调用，按路由/策略转发到 core（避免 app 直连 core）

### 1.2 aiPlat-app（业务面 / 会话与通道权威）
- channels：Slack/飞书/邮件/工单等连接与状态
- sessions：channel_user → session_id（或 thread→session）映射与 session lane 串行化
- delivery：把 **platform 返回的 run 结果**投递回对应 channel/thread（含重试/DLQ）

### 1.3 aiPlat-core（执行内核 / 治理与观测权威）
- 执行：harness/syscalls（llm/tool/skill）统一 choke point
- 治理：policy engine、toolset、审批（approval hub）
- 观测：trace + syscall_events + run_events + executions
- 学习：learning artifacts、release/rollback（面向“能力提升”的发布链）

### 1.4 aiPlat-management（运营运维控制台 / 聚合）
- 聚合平台视图：tenant、auth、channels、sessions、runs、approvals、audit、usage
- 作为“人类操作面”：审批、回放、发布、灰度、回滚

---

## 2. 跨服务统一数据契约（强烈建议先冻结）

相关规范（已冻结默认值）：
- `规范-platform-鉴权与身份透传.md`
- `规范-app-session_id与conversation_key.md`
- `规范-core-run_id-trace_id-request_id.md`

### 2.1 Headers / Claims（platform → app/core → management）
- `tenant_id`
- `actor_id`
- `actor_role`（或 roles/scopes）
- `request_id`（幂等 + 全链路审计）

### 2.2 Run Contract（core 权威输出，app/management 消费）
最小字段：
- `run_id`（core 生成，建议 `run_<ulid>`）
- `trace_id`
- `status`：accepted/running/waiting_approval/completed/failed/aborted/timeout/queued
- `target_type/target_id`
- `session_id`（来自 app）
- `error: { code, message }`
- `output`（可选）

### 2.3 Run Events（core 权威，management 订阅；app 可选订阅用于流式投递）
- `seq`、`type`（run_start/tool_start/tool_end/approval_requested/run_end/queued…）
- `payload`（结构化，且可审计）

---

## 3. PR 拆解（14 个 PR，四服务分别落点）

> 与之前 14 PR 大体一致，但这里把“哪个仓负责什么”明确写死。

### Sprint-1（第 1-2 周）：打通 tenant/identity + run contract + run events（平台最小可用）

#### PR-01（platform）：身份输出标准化（JWT claims / headers）
- **platform**：确保所有 northbound 请求都能获得 tenant/actor/scopes（JWT 推荐）
- **交付**：对 app/core 提供统一中间件或 SDK：`extract_identity()`
- **验收**：在日志中打印 request_id/tenant_id/actor_id（脱敏）

#### PR-02（app+platform+core）：session → platform execute → core（附带 tenant/actor/session）
- **app**：将 channel 消息标准化为 `ExecutionRequest`，携带 session_id，并调用 platform（不直连 core）
- **platform**：鉴权/限流/路由后调用 core；生成并透传 `request_id=req_<ulid>`；并把 run_id/trace_id/status 回传给 app（用于 delivery）
- **core**：执行并写入 execution_store（tenant_id + session_id）
- **验收**：任意 channel 来的一条消息，经 platform 转发后 core 能落库；app 能拿到 run_id 并完成回包

#### PR-03（core+management）：Run Contract v2 + Run Events polling + wait
- **core**：统一 run_id、状态机、run_events 表、events API、wait API
- **management**：新增/增强 Links 页面，展示 run 状态与 events
- **验收**：management 能看到 run 的 tool_start/tool_end/approval_requested 事件

### Sprint-2（第 3-4 周）：一致性 + 企业治理（session lane / RBAC / audit）

#### PR-04（app）：per-session lane 串行化 + queue mode
- **app**：同 session 串行化（collect/followup/steer 最小实现）
- **验收**：同一 thread 连续发 3 条消息不会并发触发 3 个 core run

#### PR-05（platform+core）：RBAC/Scopes（平台权威 + core 强制）
- **platform**：角色/权限模型与签发 scopes
- **core**：关键 endpoint 强制校验 scopes（403 + error_code=FORBIDDEN）
- **验收**：无 scope 的用户不能执行 write_repo / mcp_high_risk 工具集

#### PR-06（core+management）：Audit Logs（企业审计台账）
- **core**：audit_logs 表 + 写入（execute/approve/policy change/release）
- **management**：审计页（tenant/actor/action/run_id 过滤）
- **验收**：能从审计页回溯一次事故 run 的“谁触发、审批人、执行了哪些工具”

### Sprint-3（第 5-6 周）：策略与审批中心（企业敢用）

#### PR-07（platform+core）：Policy-as-code（tenant 级策略版本化）
- **platform**：policy snapshot 作为 tenant 配置的一部分（权威存储可在 platform）
- **core**：policy engine 执行（deny/warn/truncate/approval_required）
- **验收**：某 tenant 开启“外部 HTTP 需审批”，立刻生效且可审计

#### PR-08（core+management）：Approval Hub（计划化审批 + 回放）
- **core**：审批请求必须含 plan（systemRunPlan/filePlan/externalAccess）
- **management**：审批 inbox（approve/reject/replay）
- **验收**：approve 后 run 自动继续；replay 可重放同一 plan

#### PR-09（platform+core）：Quotas（先 report-only 后 enforce）
- **platform**：quota 配置（并发、token/day、tool calls/day）
- **core**：执行时校验并产出 QUOTA_EXCEEDED
- **验收**：超额被拦截且在 management 看到原因与统计

### Sprint-4+（后续增强）：记忆/技能/插件/连接器标准化

#### PR-10（core+management）：企业版 Memory（可解释注入 + 可删除/Pin/禁用）
#### PR-11（core+management）：Skill 自进化闭环（审核→发布→灰度→回滚→指标）
#### PR-12（core）：Hooks/Plugins 框架（Claude Code 风格，但受 policy/audit 约束）
#### PR-13（app）：Connector 标准化（Slack/飞书/工单系统等统一适配层）
#### PR-14（platform+management）：运维收尾（导出/保留期/合规开关）

---

## 4. 你现在就能直接开干的 Sprint-1 “最小接口清单”（推荐）

### platform → app/core
- `GET /whoami`（返回 tenant_id/actor/scopes；用于调试）
- JWT claims：`tid`、`sub`、`roles`、`scopes`

### app → platform（关键：app 不直连 core）
- `POST /api/platform/gateway/execute`（建议由 platform 暴露并路由到 core）
  - app 只负责把 channel/thread 映射成 session_id，并携带最小的执行 payload

### platform → core
- `POST /api/core/gateway/execute`（core 已有）
  - platform 负责注入 tenant/actor/scopes/request_id，并做统一限流与审计入口打点

### core → management（或 management 代理 core）
- `GET /api/core/runs/{run_id}`
- `GET /api/core/runs/{run_id}/events?after_seq=...`
- `POST /api/core/runs/{run_id}/wait`

---

## 5. 需要你确认的唯一“落地变量”（不影响总体顺序）

即使你不回答也能推进，但会影响实现细节：
- platform 的鉴权形态：JWT vs API key（两者都可；JWT 更适合企业统一 SSO）
- app 的 session_id 生成规则：按 channel_user？按 thread？按 ticket_id？
- core 的 run_id 格式：建议 `run_<ulid>`（易排序、可追踪）
