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

---

## 8. 消息渠道适配器（P1-A4，2026-08-18）

消息通道统一抽象位于 app 层（`aiPlat-app/channels/`），platform 仅经管理端点暴露：

- **适配器注册**：`channels/adapter.py::get_channel_adapter(name)` 按 channel name 解析适配器实例（telegram/slack/webchat/discord/wecom/email/dingtalk，`wecom` 为 `wechat` 别名）；
- **扩展适配器**：`channels/adapters/`（Discord/WeCom/Email/DingTalk 4 个），由 `ChannelDispatcher` 合并注册（3 内置 + 4 扩展 = 7 渠道）；
- **测试端点**：`POST /platform/channels/{id}/test` 校验通道有注册适配器（未知通道 fail-loud 422）；
- **身份**：渠道消息经 platform 解析为 `{ tenant_id, actor_id }` 后透传下游（见 §1-2），适配器本身不承载业务逻辑。

> **对照**：Hermes 20+ IM 平台统一 Gateway — aiPlat Gateway 控制面已就绪，适配器层按需扩展。

---

## 9. 管理员 MFA 强制（P0-5 阶段 3，2026-08-18）

admin 角色拥有全权限（9 个独占管理项），**必须启用 MFA**：

- **强制点**：`POST /tenant/api-keys` — admin（`actor_role == admin`）未启用 MFA → 422 `mfa_required`（禁止创建新 API Key）；
- **启用流程**：`POST /platform/auth/mfa/setup`（生成 TOTP 密钥 + 扫码 URI）→ `POST /platform/auth/mfa/verify`（校验后激活 `mfa_enabled`）→ 后续登录/建 key 走 TOTP；
- **实现**：`auth/mfa.py`（RFC 6238 零依赖 TOTP）+ `auth/mfa.py::require_mfa_for_role`；
- **验证**：`pytest aiPlat-platform/tests/test_mfa.py -q`（9 passed，含端点强制/放行）。

> **对照**：Claude Code enterprise 治理基线 — 管理员账号 MFA 是破坏半径控制的最低门槛。

---

## 10. Agent Registry 统一入口（P0-B4，2026-08-19）

- **统一入口**：`get_agent_registry` 经 CoreFacade canonical re-export（`core/api/core_facade.py`，源自 `core/harness/integration.py::get_agent_registry`）；
- **冗余清理**：`get_agent_registry_facade`（旧 CoreFacade 包装，0 调用者 + 重复实现）已删除；`conversations.py` 等收敛到统一命名；
- **约束**：新增平台侧访问 agent registry 的代码一律 `from core.api.core_facade import get_agent_registry`（唯一入口，§10 API 入口唯一性）。

> **对照**：入口唯一性治理 — 同一能力（agent registry）全系统仅一个公共入口，禁止 facade 层维护重复 getter。

---

## 11. P0-A2 收敛回归修复（2026-08-19）

`knowledge-graph/stats` 500 根因为 P0-A2 收敛时部分符号（如 `effective_cycles`）未在 CoreFacade re-export → ImportError。全仓审计后：

- **core 侧** 40 个缺失符号恢复原模块导入（core 内部 api→harness 允许）；
- **platform 侧** 9 个符号（`create_infra_database_client`/`get_rag_evaluator`/`EvalSample`/`list_pending`/`reject`/`get_history`/`evaluate`/`get_alerts`/`compute`/`assemble_field_assessment`/`SystemDiagnostician`）**经 CoreFacade canonical re-export**（platform 必须经 CoreFacade，§92）；
- 约束：**新增 platform 侧经 CoreFacade 访问的符号，必须先确认 CoreFacade 模块级 re-export 存在**（缺失 = 运行时 ImportError = 500）。

---

## 12. L2 导入既有代码端点权限（2026-08-22）

`aiPlat-platform/api/routers/builder.py` 新增 3 个 L2 端点，权限与既有 builder 端点一致：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/import-repo` | `require_builder_access` | 导入 zip（`File`）或 AIPLAT_HOME 内路径（`existing_path`）→ manifest |
| `GET /projects/{id}/imported-files` | `require_builder_access` | 已导入文件清单（勾选 + 修改意图） |
| `GET /import-stats` | `require_builder_access` | skip_pytest_gate 埋点统计（>40% → L3 优先级告警） |

**约束**：
- `existing_path` 白名单限制在 AIPLAT_HOME 内（跨目录导入需管理员确认，复用 `require_admin_access` 模式，L2 设计 §3.5）；
- import-repo 接受任意登录 builder 用户上传 zip —— zip 仅解压到 `~/.aiplat/apps/{pid}/imported/`（zip-slip 防护 + 密钥过滤 + 体积限额），不触碰其他用户/系统路径；
- 统计端点仅返回聚合比率，不含项目明细（避免通过 skip 统计反推他人项目状态）。

---

## 13. L3 增量合并端点权限（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 新增 3 个 L3 合并端点，权限与既有 builder 端点一致：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/merge-preview` | `require_builder_access` | 生成合并预览（流水线新版本 vs imported 原件 diff + 影响面分析） |
| `GET /projects/{id}/merge-previews` | `require_builder_access` | 查询已生成预览 |
| `POST /projects/{id}/merge-apply` | `require_builder_access` | 应用审批通过的合并（逐文件 decisions） |

**约束**：
- `merge-apply` 是**写操作**且**不可逆自动回退**（虽有 deploy.prev 快照），接受任意 builder 用户调用——但**审批门禁在前端强制**（逐文件通过/驳回），后端仅做语法/接口验证拦截（§3.6）；后续如需严格化可升级为 `require_admin_access` 或加 HITL 双签；
- merge-preview 读取 `_final_state` 与 `imported/` 原件，仅限本项目路径（不越权读其他项目）；
- decisions 中未提及的文件一律不应用（默认保留 imported 原件）。

---

## 14. L3 P0 补丁端点权限（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 新增 1 个 L3 影响面分析端点：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/analyze-impact` | `require_builder_access` | 影响面分析（勾选文件 + Python 一阶 import 引用 → auto_added 建议列表） |

**约束**：
- 该端点为**只读分析**（不写文件/状态），接受任意 builder 用户调用；分析结果仅作建议，最终文件集由用户在勾选区决定（取消自动加入文件有二次确认）；
- 不泄露其他项目内容——只分析当前项目 imported/ 内的文件。

---

## 15. L4 多模块端点权限（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 新增 5 个 L4 端点，权限与既有 builder 端点一致：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/modules` | `require_builder_access` | 声明项目模块（modules.json 语义） |
| `GET /projects/{id}/modules` | `require_builder_access` | 模块列表（含隐式 default） |
| `POST /projects/{id}/modules/{module_id}/import-repo` | `require_builder_access` | 模块级代码导入（L2 复用，module_id 路由到 modules/{mid}/imported/） |
| `POST /projects/{id}/cross-module-impact` | `require_builder_access` | 跨模块影响分析（只读） |
| `POST /projects/{id}/module-orchestrate` | `require_builder_access` | 模块编排（依赖顺序触发 rebuild） |

**约束**：
- 模块路径白名单：`module_id` 仅用于 `modules/{mid}/` 子目录路由（服务层 `_module_root` 校验，防 `../` 越界访问其他模块/项目）；
- `module-orchestrate` 触发 rebuild 是写操作，但每模块流水线与单模块 rebuild 同等权限（`require_builder_access`）；若需严格化可升级 `require_admin_access`；
- 跨模块分析只读当前项目内模块代码，不越权读其他项目。

---

## 16. L4 v1.5 跨模块契约门禁端点（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 的 `merge-preview` 端点签名扩展：

| 端点 | 变更 | 权限 |
|---|---|---|
| `POST /projects/{id}/merge-preview` | body 增加可选 `module_id`（默认 default）——多模块项目按模块生成预览 + 跨模块契约检查 | `require_builder_access`（不变） |

**约束**：
- `module_id` 仅路由到当前项目 `modules/{mid}/` 子目录（服务层 `_module_repo` 白名单），不可越权读其他项目/模块；
- 跨模块契约检查（`verify_changed_module_contracts`）只读当前项目各模块的**已导入代码**（静态分析），不触发任何执行；
- `merge_apply` 的 `contract_gate_failed` 阻断不改变权限模型（仍是 `require_builder_access`）——门禁是**工程正确性**约束（依赖方引用断裂禁止合并），非权限约束。

---

## 17. L4.5 迁移端点权限（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 新增 4 个 L4.5 迁移端点：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/migration-preview` | `require_builder_access` | schema diff（imported vs merge 后）→ 迁移 up/down 预览（只读） |
| `GET /projects/{id}/migrations` | `require_builder_access` | 迁移历史 + pending |
| `POST /projects/{id}/migrations/apply` | `require_builder_access` | 应用迁移（destructive 需 `confirmed=true`） |
| `POST /projects/{id}/migrations/{id}/rollback` | `require_builder_access` | 应用 down 回滚 |

**约束**：
- 迁移**默认仅记录状态**，不执行真实 SQL——仅当 `AIPLAT_DB_EXECUTE=true` 时对配置的 DB 执行（安全红线，§3.8）；权限模型不变（工程正确性门禁，非权限约束）；
- destructive 迁移（删列/类型变更/删表）必须 `confirmed=true` 显式确认，否则拒绝（`destructive_migration_requires_confirmation`）；
- `migration-preview` 只读当前项目已导入代码（AST 静态分析），不触发执行、不读其他项目。

---

## 18. L5 发布端点权限（2026-08-23）

`aiPlat-platform/api/routers/builder.py` 新增 5 个 L5 发布端点：

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /projects/{id}/release` | `require_builder_access` | 创建版本化发布（merge 后代码 → releases/v{ts}） |
| `GET /projects/{id}/releases` | `require_builder_access` | 发布历史 + current 指针 |
| `POST /projects/{id}/releases/{v}/canary` | `require_builder_access` | ready → canary（金丝雀验证标记） |
| `POST /projects/{id}/releases/{v}/full` | `require_builder_access` | canary → full（提升全量，current 指针切换） |
| `POST /projects/{id}/releases/{v}/rollback` | `require_builder_access` | 回滚（指针切历史版本） |

**约束**：
- `release`/`full`/`rollback` 为**写操作**（切 current 指针/生成版本产物），但仅影响当前项目自己的 releases/ 目录（版本路径由服务层 `release_root` 固定），不越权写其他项目；
- 迁移先行门禁（pending_migrations → 拒绝发布）是**工程正确性**约束（迁移未应用就发布会 schema 不同步），非权限约束；
- `canary` 为状态标记（v1 无真实流量路由）；`AIPLAT_L5_INFRA_DEPLOY=true` 时 release 会调 infra deploy_service 注册服务（namespace=aiplat-apps）——该 env 默认关闭，需运维显式开启。

---

## 19. L5 v2 端点扩展（2026-08-23）

`POST /projects/{id}/releases/{v}/canary` 签名扩展：

| 端点 | 变更 | 权限 |
|---|---|---|
| `POST .../releases/{v}/canary` | body 增加可选 `canary_weight`（0/10/50/100，路由百分比） | `require_builder_access`（不变） |

**约束**：
- `canary_weight` 是**路由配置表达**（v2 无真实流量路由，权重由部署环境消费）——仅写入当前项目自己的发布记录，无跨项目影响；
- `AIPLAT_L5_INFRA_DEPLOY=true` 时 `create_release` 经 **CoreFacade.deploy_app_service → infra_bridge** 注册服务（namespace=aiplat-apps）——platform 不直导 infra（单向依赖 platform → core → infra）；env 默认关闭。
