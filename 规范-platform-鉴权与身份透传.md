---
title: 规范：aiPlat-platform 鉴权与身份透传（企业平台默认）
date: 2026-04-18
scope: aiPlat-platform → aiPlat-app/aiPlat-core/aiPlat-management
status: draft
---

## 1. 总原则（最佳实践默认值）

1) **用户鉴权**：以 **JWT（SSO）为主**（短期 access token + refresh token）。  
2) **服务间鉴权**：优先 **mTLS**；若必须用 token，使用 **service JWT（client credentials）** 或 **服务 API key**（仅代表“机器身份”，不承载复杂用户权限）。  
3) **用户权限与租户归属**：必须由 platform 权威签发（JWT claims 最合适），下游（app/core）只消费、不推断。  
4) **全链路幂等与审计**：platform 生成 `request_id=req_<ulid>` 并透传；所有下游日志/审计必须带 request_id。

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

