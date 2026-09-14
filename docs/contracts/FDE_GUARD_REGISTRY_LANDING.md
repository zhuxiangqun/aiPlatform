# FDE 守卫与 Registry 落地说明

| 字段 | 值 |
|------|-----|
| 版本 | v1.1（盘点已填；待评审签字） |
| 日期 | 2026-09-14 |
| 状态 | Phase 0 前置文档；**未评审通过前不默认改代码** |
| 关联方案 | [`docs/architecture/plans/fde-workbench-evolution-plan.md`](../architecture/plans/fde-workbench-evolution-plan.md) |
| 关联契约 | [`docs/contracts/FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) |
| 关联审计 | [`aiPlat-core/core/harness/schemas/audit_schema.v1.yaml`](../../aiPlat-core/core/harness/schemas/audit_schema.v1.yaml) |
| 存量扫描 | [`docs/contracts/domain_literals_scan.md`](./domain_literals_scan.md) |

---

## 0. 本文档解决什么问题

方案 §6.2 / §6.3 写了守卫与 Registry 的**设计意图**。本文把意图接到**现有**引擎：

- `scripts/architecture_guard.py` + `arch_guard_rules*`
- `AsyncActionRegistry` + `ActionContractModel`
- `ActionStore.action_audit` / `pending_approvals`
- Pipeline HITL（`PipelineEngine` / `pipeline_stage` / `stage_handoff`）

**防止两种失控：**

1. 新建 `core/tools/architecture_guard` → 第二套守卫  
2. 新建 `FdeActionRegistry` → 第二套执行入口  

**原则：扩展已有能力，不新建包、不新建库、不新建执行栈。**

---

## 1. 现有基础设施盘点（已核对仓库，2026-09-14）

### 1.1 守卫

| 项 | 现状 |
|----|------|
| 主入口 CLI | `scripts/architecture_guard.py`（文本 / `--json` / `--quick`） |
| Shell 包装 | `scripts/architecture_guard.sh`（CI 调用此脚本） |
| 规则引擎 | `aiPlat-core/core/management/arch_guard_base.py`（`ArchRegistry` / `ArchYAMLRule` / `ArchRule`） |
| 声明式规则 | `aiPlat-core/core/management/arch_guard_rules.yaml`（约 **193** 条） |
| 复杂规则包 | `aiPlat-core/core/management/arch_guard_rules/*.py`（自动发现） |
| FDE §98 已落地 | YAML：`fde_no_hardcoded_action_branch` / `fde_no_parallel_fde_api` / `fde_no_workbench_direct_harness`；Python：`fde_workbench.py`（`FdeDomainLiteralsAstCheck` warning、`FdeWorkbenchForbiddenFrontendCheck` error） |
| 检查类型 | `grep_forbidden` / `grep_required` / `grep_graph_import` / `cmd_output` / `file_*` + Python ArchRule（AST 可写在 `*.py`） |
| CI | `.github/workflows/architecture-guard.yml` → `bash scripts/architecture_guard.sh` |
| pre-commit | `scripts/pre-commit-hook.sh` 调 `--quick` |
| baseline ratchet | `scripts/baselines/architecture_guard_baseline.txt` |

**必须复用：** 规则加载器、报告格式、CI / pre-commit、baseline。  
**允许：** 在 `arch_guard_rules.yaml` 增规则；在 `arch_guard_rules/` 增 ArchRule。  
**禁止：** `core/tools/architecture_guard/`、平行规则目录、绕过 CI。

### 1.2 Action 执行

| 项 | 现状 |
|----|------|
| 主类 | `AsyncActionRegistry` @ `aiPlat-core/core/harness/ontology_engine/action_registry.py` |
| 合同模型 | `ActionContractModel` @ `.../infrastructure/action_contract.py` |
| 注册 | `register(contract: ActionContractModel) -> None`；已挂 `action_namespace` 非空时的 `validate_action_contract` |
| 执行 | `async execute(action_id, entity_ref, params, actor="system", role="", _bypass_approval=False) -> Dict` |
| 7 步管线 | mutex → 校验 → 实体 → 约束 → approval/`pending_approvals` → handler → audit → 释放 |
| 新字段（过渡） | `action_namespace: str = ""`、`eval_gate: str = ""`（空=legacy，跳过强校验） |
| 校验模块 | `.../infrastructure/action_audit_validate.py`（`validate_action_contract` / `build_audit_record` / `map_audit_to_action_store`） |
| 内置 handler 例 | `builtin_handlers.accept_order`；注册 id=`customer_action:lock-service:accept_order`，别名 `accept_order`（D3 已执行） |
| PolicyGate | 执行路径内有约束/审批/throttle；RuntimeGuard 审计形状 soft；产品门继续观察 |
| HITL（Action） | `pending_approvals` + `require_approval` / stake lock |
| HITL（Pipeline） | `PipelineEngine` + `pipeline_stage.py`（`stage.hitl`、`_hitl_resolved_*`、`approve_session`）+ `stage_handoff.py` |

**必须复用：** `AsyncActionRegistry` 唯一执行入口。  
**禁止：** `FdeActionRegistry`；harness 内 `if action == "accept_order"`；绕过 Registry 写库。

### 1.3 审计与审批存储

| 项 | 现状 |
|----|------|
| 类 | `ActionStore` @ `.../infrastructure/action_store.py` |
| 审计表 | `action_audit`（aiosqlite，追加写 INSERT） |
| 现有列 | `audit_id, action_id, entity_id, domain_id, from_state, to_state, actor, role, params, result_status, constraint_type, effect_summary, compensation, entity_snapshot, created_at` |
| 审批表 | `pending_approvals`（`lock_id, action_id, entity_ref, params, actor, status, locked_until, resolved_at, resolver, resolve_reason, requested_at`） |
| 查询 | `list_audit(entity_id="", domain_id="", limit=50)` |
| 索引 | `(entity_id, domain_id)`、`(action_id)`、`pending status` |

**必须复用：** 唯一写入点 `insert_audit`。  
**允许：** 加列（NULL）、加索引、params/entity_snapshot JSON 嵌入 schema 字段（Phase 1）。  
**禁止：** 平行 `FdeAuditStore`；handler 内直接 INSERT。

### 1.4 Pipeline 挂起 / 恢复（方案审查补齐）

| 项 | 路径 |
|----|------|
| 状态类型 | `PipelineState`（TypedDict）@ `pipeline_engine.py` |
| 引擎 | `PipelineEngine` + `PipelineStateMixin` @ `pipeline_state.py` |
| 阶段 HITL | `pipeline_stage.py`：`stage.hitl`、暂停快照、`failure_strategy` |
| Schema 门 HITL | `stage_handoff.py`：`append_hitl_audit`、`GATE_ON_FAIL_HITL` |
| 恢复 | `approve_session` / `_resume_event` / `_hitl_resolved_{stage.id}` |

> 说明：仓库**没有**独立文件名 `ApprovalStore`；Action 侧审批 = `ActionStore.pending_approvals`；Pipeline 侧 = 引擎 state + hitl audit。方案中「ApprovalStore」均指上述二者，不新建第三套。

### 1.5 安全审查入口（Phase 4A）

| 项 | 现状 |
|----|------|
| Facade | `core.api.core_facade.run_security_review_dry(**kwargs)` |
| HTTP | `POST .../diagnostics/code-intel/security-review-dry`（`apps/misc/api/code_intel.py`） |
| 参数（已用） | `force`, `max_paths`, `phase_c_enabled`（或 env `AIPLAT_SECURITY_PHASE_C=1`） |
| 流水线 | plan → trace → critique → report →（可选）evidence + merge |
| 证据落盘 | `~/.aiplat/cache/security_evidence/`（fallback `aiPlat-core/tmp/security_evidence/`），schema `regression_evidence.v1` |

---

## 2. 五条守卫规则映射（已接到现有引擎）

| 规则意图 | 分析稿 id | 仓库落点 | Week 1 级别 | 目标 |
|----------|-----------|----------|-------------|------|
| 域字面量 | `domain_literals` | `arch_guard_rules/fde_workbench.py` → `FdeDomainLiteralsAstCheck`（code=`fde_domain_literals`） | **error** | —（已升） |
| 禁 IDE 组件 | `workbench_forbidden_components` | 同文件 `FdeWorkbenchForbiddenFrontendCheck` | **error** | error |
| 禁硬编码 Action | `no_hardcoded_action_branch` | YAML `fde_no_hardcoded_action_branch` §98 | **warning** | error |
| 禁平行 FDE API | `no_parallel_fde_api` | YAML `fde_no_parallel_fde_api` §98 | **warning** | error |
| 禁直导 harness | `no_workbench_direct_harness` | YAML `fde_no_workbench_direct_harness` §98（与 §94 互补） | **error** | error |

### 2.0 路径修正（强制 — 防守卫扫空）

| 规则 / 检查 | 正确 scope | 错误（禁止） |
|-------------|------------|--------------|
| 前端 IDE / 假进度 / Agent 拓扑 | `aiPlat-management/frontend/src/pages/Diagnostics/**/*.{ts,tsx}` | `aiPlat-platform/platform/apps/fde/**/*.{ts,tsx}`（路径不存在） |
| 后端禁直导 harness | `aiPlat-platform/apps/fde/**/*.py` | `aiPlat-platform/platform/apps/fde/**` |
| 已实现前端守卫 | `fde_workbench.py` → `FdeWorkbenchForbiddenFrontendCheck` **已扫 Diagnostics** | — |
| 已实现后端守卫 | YAML `paths: ["aiPlat-platform/apps/fde"]` **已正确** | — |

待建规则（`workbench_no_fake_progress` / `workbench_no_agent_topology`）**必须**用上表前端路径；合入前用开工清单 §B 验收。

详见 [`FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md`](./FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md)。

### 2.1 检查器能力对照

| 分析稿 check type | 现有支持方式 |
|-------------------|--------------|
| `ast_string_literal` | Python `ArchRule`（已用 AST，见 `fde_workbench.py`） |
| `ast_if_compare` | 可新增 ArchRule；当前用 `grep_forbidden` 近似 |
| `ast_import` | ArchRule 或 grep（§94 / §98 已用 grep） |
| `regex_import` / `regex_route` | `grep_forbidden`（YAML） |

**不需要**新建 `ast_string_literal` 通用引擎；FDE 规则用现有扩展点即可。

### 2.2 存量扫描（Phase 0 产出）

见 [`domain_literals_scan.md`](./domain_literals_scan.md)。摘要（2026-09-14）：

- harness 内 `"fde-delivery"|"lock-service"|"supply-chain"` **约 10 处**（含 docstring/示例）
- 排除 builtin / domain_router / ontology_loader / action_audit_validate 后，主要在：`ontology_branch.py`（示例）、`prompt_loader.py`（域 prompt 默认表）、`graph_*.py` docstring、`ontology_validator.py` 示例、`recon_subgraph.py`
- **升级条件：** 行为分叉类字面量清零（示例/docstring 可 `# noqa: domain-literal` 或改为常量）后，`fde_domain_literals` → **error** — **已满足（2026-09-14）**
- **是否阻塞 Phase 1：** 不阻塞（保持 warning）；**阻塞 Phase 5**（多客户）前必须升 error 且清零 — **Phase 5 前置已关闭**

---

## 3. ActionRegistry 校验接线

### 3.1 注册（已部分落地）

```text
AsyncActionRegistry.register(contract)
  └─ if contract.action_namespace:
       validate_action_contract(...)  # action_audit_validate.py
```

校验内容（namespace 非空时）：前缀一致、customer 禁用平台跟踪域、高风险须 `require_approval`、`eval_gate` ∈ audit_schema。

### 3.2 执行（Phase 2 待接完整审计形状）

现有 `execute` 已写 `insert_audit`（单列 `entity_snapshot`）。Phase 2 目标：

1. 保持 7 步顺序  
2. 对 `action_namespace=customer_action`：用 `build_audit_record` → `map_audit_to_action_store` 再 `insert_audit`  
3. Phase 1 可先把扩展字段打进 `params` JSON（`schema=audit.v1`），避免立刻改表阻塞存量  

### 3.3 与 PolicyGate / HITL 接线顺序（竖切）

| 顺序 | 动作 | 依赖 |
|------|------|------|
| 1 | customer_action 强制 `require_approval` | ActionContract |
| 2 | 走现有 `pending_approvals` | ActionStore |
| 3 | 前后快照写入 audit 形状 | Ontology / entity dict |
| 4 | rollback_handler / compensation | accept_order 先做 |

---

## 4. audit_schema ↔ ActionStore 映射

**文件状态：** `aiPlat-core/core/harness/schemas/audit_schema.v1.yaml` **已存在**（Phase 1 冻结语义；非从零新建）。

### 4.1 映射表

| audit_schema.v1 字段 | 现有 `action_audit` | 动作 |
|----------------------|---------------------|------|
| `audit_id` | `audit_id` | 已有 |
| `timestamp` | `created_at` | 已有（语义对齐） |
| `actor_type` | `role`（过渡） | Phase 1：params JSON 内写 `actor_type`；Phase 2 可加列 |
| `actor_id` | `actor` | 已有 |
| `approver_id` | — / `pending_approvals.resolver` | Phase 1：params JSON；Phase 2 加列 |
| `action_namespace` | — | Phase 1：params JSON；Phase 2 加列 |
| `action_name` | `action_id` | 已有（存完整名） |
| `domain_id` | `domain_id` | 已有 |
| `target_entity_type` | — | Phase 1：params 或 snapshot；Phase 2 加列 |
| `target_entity_id` | `entity_id` | 已有 |
| `input_params_hash` | — | Phase 1：params.`params_hash` |
| `input_params_snapshot` | `params` | 已有（脱敏约定） |
| `before_state_snapshot` | `entity_snapshot` 嵌套 | Phase 1：`{"before":...,"after":...}` |
| `after_state_snapshot` | 同上 | 同上 |
| `result_status` | `result_status` | 已有（枚举对齐时注意别名） |
| `result_message` | `effect_summary` | 已有 |
| `pipeline_run_id` | — | Phase 1：params JSON；Phase 2 加列 |
| `evidence_ref` | — | Phase 1：params JSON |
| `policy_gate_decision` | — | Phase 1：params JSON |
| `rollback_ref` | `compensation` / 新列 | 过渡用 compensation 文本 |
| `retention` | — | Phase 1：params JSON |

**策略：** Phase 1 = **加列允许 NULL 或 JSON 嵌入**（优先嵌入，降低迁移风险）；Phase 2 lock-service 强制完整率 100%；不改 `insert_audit` 签名，只扩展 record 内容。

### 4.2 建议索引（Phase 2 后）

```sql
-- 在现有 idx_audit_entity / idx_audit_action 之外
-- CREATE INDEX IF NOT EXISTS idx_action_audit_run ON action_audit(json_extract(params,'$.pipeline_run_id'));
-- 或加列 pipeline_run_id 后再建 B-tree 索引
```

### 4.3 查询增强（设计，未强制本周实现）

- 现有：`list_audit(entity_id, domain_id)`  
- 建议：`query_by_entity` / `replay_entity` 作为 ActionStore 方法（方案层）；实现排 Phase 1/2  

---

## 5. 存量 Action 命名空间迁移

| 状态 | 注册校验 | 执行 | 审计 |
|------|----------|------|------|
| `action_namespace=""` | 跳过 | legacy 7 步 | 现有列 |
| 已声明 | 强校验 | 目标：完整 audit 形状 | schema 字段齐 |

**accept_order 迁移步骤（方案）：** 加 namespace → 改 id 前缀 → HITL/high → eval_gate → 快照 → rollback；旧 id 作别名至 Phase 3。

**平台跟踪域常量（决策相关）：** `PLATFORM_TRACKING_DOMAINS` / 建议唯一常量 `PLATFORM_TRACKING_DOMAIN = "fde-delivery"`（允许赋值，禁止 Compare 行为分叉）。

---

## 6. Phase 落地顺序（文档验收，非默认可写码）

### Phase 0

| 步骤 | 产出 | 验收 |
|------|------|------|
| 1 | 本 Landing §1 盘点 | TODO 清零（本节已填） |
| 2 | 五条规则已在现有目录 | §98 可加载 |
| 3 | `domain_literals_scan.md` | 分布量化 |
| 4 | CI 跑主守卫含 §98 | 报告可生成 |
| 5 | **不做** Action 迁移 / 加列 / PolicyGate 大改 | — |

### Phase 1–2

见演进方案；本 Landing 为接线说明书。

---

## 7. 回滚与风险

| 变更 | 回滚 |
|------|------|
| YAML / ArchRule | 删规则或降 severity |
| params JSON 嵌入 | 忽略未知键 |
| 加列 | DROP COLUMN（仅在未依赖查询时） |
| register 钩子 | namespace 空则跳过 |
| Action 改名 | 别名映射 |

| 风险 | 缓解 |
|------|------|
| 平行 guard/Registry | 本文件 + PR 勾选契约 |
| 加列阻塞存量 | NULL 或先 JSON |
| 守卫误报 | Week 1 warning；扫描报告分类 |
| 审计填不满 | Phase 2 完整率 100% 硬门 |

---

## 8. 文档地图

```
docs/architecture/plans/fde-workbench-evolution-plan.md
docs/contracts/FDE_WORKBENCH_CONTRACT.md
docs/contracts/FDE_GUARD_REGISTRY_LANDING.md          ← 本文
docs/contracts/domain_literals_scan.md
aiPlat-core/core/harness/schemas/audit_schema.v1.yaml
（Pipeline）core/harness/execution/pipeline_engine.py + pipeline_stage.py + stage_handoff.py
（审批）ActionStore.pending_approvals
（安全）core_facade.run_security_review_dry + regression_evidence.v1
```

---

## 9. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-14 | 初版短文：映射表与反平行原则 |
| v1.1 | 2026-09-14 | 按评审意见扩写：盘点填实、审计映射、Pipeline/审批澄清、4A 入口、存量扫描链接 |
