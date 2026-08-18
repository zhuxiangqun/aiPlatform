---
title: 规范：aiPlat-platform 鉴权与身份透传（企业平台默认）
date: 2026-04-18
scope: aiPlat-platform → aiPlat-app/aiPlat-core/aiPlat-management
status: approved
draft_date: 2026-07-04
approved_date: 2026-08-16
---

## 1. 总原则（最佳实践默认值）

1) **用户鉴权**：以 **JWT（SSO）为主**（短期 access token + refresh token）。  
2) **服务间鉴权**：当前实现为 **JWT + API key**（`auth/authenticator.py`，API key 前缀 `apl_`，SHA-256 哈希存储）；**mTLS 为远期目标**（规范推荐，未实现——见 §1.2 消歧说明）。  
3) **用户权限与租户归属**：必须由 platform 权威签发（JWT claims 最合适），下游（app/core）只消费、不推断。  
4) **全链路幂等与审计**：platform 生成 `request_id=req_<ulid>`（`api/rest/routes.py:_get_or_create_request_id` + `utils/ids.py:new_prefixed_id`）并透传；所有下游日志/审计必须带 request_id。

### 1.1 消歧记录（P0-C2，2026-08-16）

| 规范原文 | 代码事实 | 消歧 |
|---|---|---|
| 服务间鉴权"优先 mTLS" | 无 mTLS 实现；`authenticator.py` 仅 JWT + API key | **以代码为准**：当前实现为 JWT/API key；mTLS 降级为远期目标，实现后方可回迁"优先" |
| API key 格式未定义 | `apl_<token_urlsafe(32)>`，SHA-256 哈希入库（`authenticator.py:71-72`） | 补充为规范 |

---

## 2. JWT（用户）推荐 Claims（最小集合）

建议使用短字段名（便于压缩），但下游统一用“标准字段名”读写：

| 标准字段 | JWT claim | 说明 |
|---|---|---|
| tenant_id | `tid` | 租户 ID |
| actor_id | `sub` | 用户 ID（或 subject）|
| roles | `roles` | 角色列表（可选）|
| scopes | `scopes` | 权限列表（推荐）|
| issued_at | `iat` | |
| expires_at | `exp` | |
| token_type | `typ` | 建议：`access` |
| request_id | `rid` | 可选：如果你希望把 rid 写进 token（一般不建议；rid 更适合 header） |

> 推荐做法：`request_id` 不放进 JWT（JWT 是可复用凭证），而是放到每次请求 header。

---

## 3. 标准透传 Headers（platform → app/core）

platform 在转发或调用下游服务时，必须注入/透传：

| Header | 示例 | 说明 |
|---|---|---|
| `X-AIPLAT-REQUEST-ID` | `req_01J...` | platform 生成；全链路幂等/审计 |
| `X-AIPLAT-TENANT-ID` | `t_xxx` | 来自 JWT claims 或 API key 查表 |
| `X-AIPLAT-ACTOR-ID` | `u_xxx` | 来自 JWT claims（sub）或 API key 查表 |
| `X-AIPLAT-SCOPES` | `operator.read,core.execute,...` | 可选；或下游自行解析 JWT（更推荐 platform 注入“已解析身份”） |
| `X-AIPLAT-ACTOR-ROLE` | `admin` | 可选；以 scopes 为准 |

---

## 4. API key（机器/集成）使用边界（强约束）

**允许：**
- 第三方系统（工单系统、企业内部自动化）以 API key 代表“集成身份”访问 platform；
- platform 根据 API key 查出 `tenant_id + actor_id(=service principal) + scopes`，并注入 headers 调用 app/core。

**禁止：**
- 直接用 API key 模拟复杂“用户身份”与细粒度权限（撤权、审计、轮换都很难做对）。

---

## 5. 调试与可观测（建议强制提供）

platform 对外提供：
- `GET /whoami`：返回解析后的 `{ tenant_id, actor_id, scopes, request_id? }`（用于联调/排障）
- 日志必须打印（脱敏）：`request_id/tenant_id/actor_id` + route + latency


---

## 6. Managed Policy — 企业远程托管策略（P1-A6，2026-08-16）

企业管理员可通过 `PUT /api/platform/policy/managed`（仅 admin）设置**托管策略**：

- **语义**：`managed: true` 的策略项（如 `model_whitelist`、`sandbox_required`）由企业远程强制，
  本地 user policy **不可覆盖**；
- **合并规则**：`merge_managed_policy(local, managed)` — managed 键覆盖本地；
  PolicyGate 读策略时优先 managed 项；
- **实现**：`aiPlat-platform/auth/schemas_policy.py::ManagedPolicy` +
  `api/routers/policy.py::PUT /platform/policy/managed`；
- **审计**：managed 策略变更记录 `managed_policy_upsert` 审计事件。

> **对照**：Claude Code 的 Server-managed settings — 企业通过远程配置强制权限/沙箱/模型，本地不可覆盖。

---

## 7. Tenant 数据归属 — 存储所有权（P0-A3，2026-08-18）

多租户治理数据的**存储所有权**在 platform 层（`aiPlat-platform/tenants/tenant_store.py`）：

- **表归属**：`tenant_quotas` / `tenant_usage_ledger` / `tenant_policies` 的 DDL + CRUD 由 platform `TenantStore` 拥有（与 ExecutionStore 同 DB 文件，零数据迁移）；
- **注入**：platform 挂载（`apps.fde`）时 `set_tenant_store()` 经 CoreFacade 注入；core 消费方（policy gate / llm 记账 / policy engine）经 `core.services.tenant_store_protocol` 解析，未注入时 fallback execution_store（零破坏）；
- **保留 core**：`audit_logs` / `connector_delivery` / `tenants` 主表（执行基础设施，非 tenant 业务 CRUD）；
- **宪法**：`TestNoQuotaEnforcementInCore` / `TestPlatformResponsibilitiesNotInCore` 真过（不再依赖 DEPRECATED 豁免）。

> **对照**：多租户治理归属 platform — core 保持内核无关（§5.29），租户数据生命周期由平台统一管理。
