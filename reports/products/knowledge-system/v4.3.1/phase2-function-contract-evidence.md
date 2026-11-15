---
doc_type: Report
title: Phase 2 — FunctionContract 最小切片证据（W5）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / FunctionContract（W5）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W5。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §C.3。  
> **未宣称**附录 N 全量符合；仅证明「函数默认无副作用」+ L1 permissions 最小切片。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `side_effects=true` 拒绝 | pass | `FunctionRegistry.invoke` → `side_effects_forbidden`；`test_side_effects_forbidden` |
| 缺 `required_permissions` → 硬拦 | pass | `policy_denied` + `missing_permissions`；对齐 Action L1；`test_policy_denied_without_permission` |
| 有权限 + 合法 handler → 纯计算 | pass | seed `platform_function:knowledge:priority_hint` → `score`；`test_invoke_ok_pure_compute` / `test_seed_loads_via_get_function_registry` |
| 未注册 id | pass | `not_found`；`test_not_found` |
| 零 Wiki/Fact 写入 | pass | handler `builtin_functions.priority_hint` 仅算术；无 store/wiki import |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_function_contract_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed in 0.21s`。

## 接线

| 入口 | 路径 |
|------|------|
| 契约 | `harness/infrastructure/function_contract.py` → `FunctionContractModel` |
| 注册表 | `function_registry.py` → `register` / `invoke` / YAML 装载 |
| 试点 seed | `workspace_seeds/functions/lock_service_priority_hint.yaml` |
| handler | `builtin_functions.priority_hint`（白名单模块） |
| CoreFacade | `invoke_function` + re-export `get_function_registry` / `FunctionContractModel` |
| HTTP | `POST /api/platform/apps/fde/functions/{function_id}/invoke`（`X-AIPLAT-SCOPES`→permissions） |

## 明确未做（后续）

- ObjectSet → 见 `phase2-objectset-evidence.md`（本批另切片）
- SDK / Interface
- 函数副作用白名单分级（本切片一律禁副作用）
- 字段级 ACL；管理端 Function publish 流水线
- 附录 N 全量符合
