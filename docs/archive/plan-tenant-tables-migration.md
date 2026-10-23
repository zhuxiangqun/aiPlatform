# Tenant 表迁移方案（P0-A3）

> 状态：**✅ 已完成（2026-08-18/19，PR #20）** · 目标：tenant_quotas/tenant_policies/tenant_usage 表 DDL + CRUD 从 core 迁至 platform
> 原则：**不改公共 API/调用语义**（消费方调用方式不变，仅 store 来源变化）；**零数据迁移**（同库同表，仅代码位置变化）
> 宪法依据：`tests/constitution/test_kernel_agnostic.py::TestNoQuotaEnforcementInCore` + `test_layer_ownership.py::TestPlatformResponsibilitiesNotInCore`（当前靠 DEPRECATED marker 豁免）

## 1. 现状分析

### 1.1 违规点（宪法违规 A3/A4）

| 位置 | 内容 | 类型 |
|---|---|---|
| `core/services/execution_store_schema.py:26-43` | tenant_quotas / tenant_usage / tenant_policies DDL | 表定义 |
| `core/services/execution_store/schema.py:1504/1728/2453/2481` | tenant_policies / tenants / tenant_quotas / tenant_usage_ledger DDL | 表定义 |
| `core/services/execution_store/quota_mixin.py:22-193` | get/upsert_tenant_quota + add/get/list_tenant_usage | 完整 CRUD |
| `core/services/execution_store/audit_mixin.py:256-346` | get/upsert/list_tenant_policies | 完整 CRUD |

### 1.2 消费方（迁移后必须仍可用）

**platform（经 KernelRuntime.execution_store 门面访问）**：
- `platform/api/routers/quota.py`（get/upsert_tenant_quota、list_tenant_usage）
- `platform/api/routers/policy.py`（list_tenant_policies）
- `platform/api/routers/tenant_policies.py`（已迁移的 router，list_tenant_policies）
- `platform/api/routers/ops_exports.py`（tenant_usage CSV 导出）
- `platform/apps/learning/api/learning_releases.py`、`platform/api/routers/onboarding.py`

**core（进程内运行时消费）**：
- `core/harness/infrastructure/gates/policy_gate.py`（4 处 get_tenant_policy）
- `core/harness/syscalls/llm.py`（add_tenant_usage 记账）
- `core/policy/engine.py`（_load_tenant_policy_snapshot 注入读取）
- `core/api/routers/runs.py` / `plugins.py` / `diagnostics.py`
- `core/harness/integration/{tool,skill,agent}.py`、`core/apps/ops/exporter.py`

### 1.3 保留 core 的（非 tenant 概念）

- `quota_mixin.py` connector_delivery 6 方法（connector 投递基础设施）
- `audit_mixin.py` audit_logs（审计基础设施，tenant_id 仅字段）
- `cost_tracker.py` `_tenant_usage`（内存统计同名变量，非 DB）

## 2. 目标形态

```
platform 层（拥有权）
  ├─ TenantStore（DDL + CRUD）→ 操作 execution_store 同库
  └─ 启动时 set_tenant_store() 注入

core 层（消费）
  ├─ TenantStoreProtocol（接口定义）→ core/services/tenant_store_protocol.py
  ├─ get_tenant_store() / set_tenant_store()（注册表，未注入返回 None）
  └─ policy_gate / llm.py / policy engine 等经协议读取/记账
```

**依赖方向合规**：core 定义协议（不 import platform），platform 实现并注入。消费方 `get_tenant_store()` 在 core 内解析。

## 3. 实施步骤（风险递增）

### Phase A：core 协议 + 注册表（零风险，先行验证机制）
- 新建 `core/services/tenant_store_protocol.py`：
  - `TenantStoreProtocol`（typing.Protocol）：8 方法签名（get/upsert_tenant_quota、add/get/list_tenant_usage、get/upsert/list_tenant_policies）
  - `set_tenant_store(store)` / `get_tenant_store()` 全局注册表
  - 未注入时 `get_tenant_store()` 返回 None（消费方已有 `if store and hasattr(...)` 模式，零破坏）

### Phase B：platform 实现 TenantStore（中风险）
- 新建 `aiPlat-platform/services/tenant_store.py`（**实际路径：`aiPlat-platform/tenants/tenant_store.py`**）：
  - 与 execution_store 同 DB 文件（db_path 复用）
  - DDL：从 core 迁移 5 张表（tenants/tenant_quotas/tenant_usage/tenant_usage_ledger/tenant_policies）（**最终范围收窄为 3 张：tenant_quotas/tenant_usage_ledger/tenant_policies，见 §7 迁移范围最终界定**）
  - CRUD：从 quota_mixin + audit_mixin 迁移 8 方法（方法体原样剪切）
  - `ensure_schema()`：建表（IF NOT EXISTS，与现有库兼容）
- 接线：platform server 启动时创建 TenantStore + `set_tenant_store()` 注入（**实际：`apps.fde/__init__.py` 挂载时注入**）
- **保留**：core 的 ExecutionStore 仍可访问这些表（同库，兼容期），但不再负责 DDL/CRUD 定义

### Phase C：core 消费方改注入（高风险，逐文件）
- policy_gate.py：`store.get_tenant_policy` → `get_tenant_store().get_tenant_policy`（保留 runtime 路径）
- llm.py：`store.add_tenant_usage` → `get_tenant_store().add_tenant_usage`
- runs.py / plugins.py / diagnostics.py / integration/* / exporter.py 同模式
- policy/engine.py：`_load_tenant_policy_snapshot` 的 store 参数改为 `get_tenant_store()` fallback

### Phase D：core 删除（低风险，最后）
- `execution_store_schema.py`：删 tenant_* DDL（保留 onboarding_evidence 等非 tenant）
- `execution_store/schema.py`：删 tenant_* DDL
- `quota_mixin.py`：删 5 个 tenant 方法（保留 connector_delivery）
- `audit_mixin.py`：删 3 个 tenant_policy 方法（保留 audit_logs）
- 移除全部 DEPRECATED marker

### Phase E：验证（每 Phase 后）
```
1. python3 -m py_compile 变更文件
2. pytest tests/constitution/test_kernel_agnostic.py::TestNoQuotaEnforcementInCore -q
3. pytest tests/constitution/test_layer_ownership.py -q
4. bash scripts/pre-commit-engine-guard.sh（引擎守卫）
5. pytest tests/integration/test_tenant_policies_api.py（platform API 回归）
6. bash scripts/architecture_guard.sh
7. CI 全量（24 项）
```

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 数据迁移丢失 | **零数据迁移**：同库同表（IF NOT EXISTS），仅代码位置变化 |
| core 运行时拿不到 tenant store（未注入） | 注册表 fallback None + 消费方保留 `if store` 守卫；platform 启动必注入 |
| 单例生命周期（测试/多进程） | `set_tenant_store()` 幂等；AIPLAT_HOME 测试环境在 fixture 注入 |
| SQLite 并发（TenantStore 与 ExecutionStore 同库） | 已有 PRAGMA WAL；写入走各自连接，SQLite 行锁 |
| 消费方遗漏（15 文件） | 迁移后 grep `tenant_quotas\|tenant_policies\|get_tenant_quota` 全仓验证清零（core 侧） |
| 宪法测试从豁免变真过 | Phase D 完成后跑全量宪法，期望 0 failed |
| platform router 的 `rt.execution_store` 路径断裂 | router 改为 `get_tenant_store()`（经 core 注册表）或保留 execution_store 兼容（deprecated） |

## 5. 收益

- 宪法违规 A3/A4 清零：core 不再管理 tenant 业务表
- 移除 4 处 DEPRECATED marker，宪法测试从"marker 豁免"变"真过"
- 多租户治理归属 platform（职责清晰），core 保持内核无关（§5.29）
- 零公共 API 破坏：platform router 对外接口不变

## 6. 决策记录

- **connector_delivery / audit_logs 留 core**：执行基础设施（非 tenant 业务概念）
- **onboarding_evidence 留 core**：不在 P0-A3 范围（最小改动面），后续单独评估
- **tenants 主表**：初判随迁移（schema.py:1728，与 tenant_quotas 同源）；**最终保留 core**（见 §7 迁移范围最终界定，与 2026-08-19 基线一致）
- **cost_tracker._tenant_usage**：内存同名变量，不迁移

## 7. 实施记录

- 2026-08-18：方案定稿（本文档）。
- **Phase A（协议 + 注册表）**：`core/services/tenant_store_protocol.py`（TenantStoreProtocol 8 方法 + set/get_tenant_store 注册表）；CoreFacade re-export。
- **Phase B（platform TenantStore）**：`aiPlat-platform/tenants/tenant_store.py`（3 表 DDL + 8 方法，方法体从 core mixin 原样剪切）；`apps.fde/__init__.py` 挂载时注入。
- **Phase C（core 消费方 9 文件）**：policy_gate(4)/llm(1)/policy engine(1)/runs(2)/plugins(1)/diagnostics(1, 顺带修复 `since`→`day_start` 存量 bug)/integration×3/exporter(1) 全部 `get_tenant_store() or store` 注入优先。
- **Phase D（core 删除）**：`execution_store_schema.py` + `schema.py`（v24/v35 保留版本号删建表 SQL）+ `quota_mixin.py`（5 tenant 方法）+ `audit_mixin.py`（3 tenant_policy 方法）；DEPRECATED marker 更新为迁移记录。
- **Phase E（验证）**：宪法 143 passed（tenant 测试从 marker 豁免变真过）；引擎守卫 R1-R4；architecture_guard 全绿；新库共存冒烟（ExecutionStore + TenantStore 同库）；CRUD 闭环；registry 登记 TenantStore/TenantStoreProtocol；acceptance 1.16。
- **platform 侧**：quota/policy/tenant_policies router `_store` 改注入优先；tenant_policies audit_log 保留 execution_store；onboarding/learning 用局部 `tstore`（避免覆盖混合 store 变量）。

### 迁移范围最终界定

| 项 | 决策 |
|---|---|
| 迁移表 | tenant_quotas / tenant_usage_ledger / tenant_policies（3 张） |
| 迁移 CRUD | 8 方法（quota 5 + policy 3） |
| 保留 core | audit_logs / connector_delivery / tenants 主表 / onboarding_evidence / cost_tracker 内存变量 |
| 数据 | 零迁移（同库同表 IF NOT EXISTS） |
