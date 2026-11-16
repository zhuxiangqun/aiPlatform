---
doc_type: Report
title: Phase 2 — Interface 最小切片证据（W5）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Interface（W5）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W5。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §C.4。  
> **未宣称**附录 N 全量符合；仅证明「接口兼容性校验」+ L1 permissions 最小切片。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 `required_permissions` → 硬拦 | pass | `policy_denied`；`test_policy_denied_without_permission` |
| implementer 声明 + 形状覆盖 → ok | pass | seed `Trackable` + `InstallOrder.status`；`test_compatible_ok` / `test_seed_loads_via_get_interface_registry` |
| 未在 implementers → 拒绝 | pass | `not_an_implementer`；`test_not_an_implementer` |
| 缺必填 property → incompatible | pass | `shape_mismatch`；`test_incompatible_missing_property` |
| 未注册 id | pass | `not_found`；`test_not_found` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_interface_contract_phase2.py -v
# 预期：6 passed
```

实测（2026-11-16）：`6 passed in 0.17s`。

## 接线

| 入口 | 路径 |
|------|------|
| 契约 | `harness/infrastructure/interface_contract.py` → `InterfaceContractModel` |
| 注册表 | `interface_registry.py` → `register` / `check_compatibility` / YAML 装载 |
| 试点 seed | `workspace_seeds/interfaces/lock_service_trackable.yaml` |
| ObjectType | `workspace_seeds/ontologies/lock-service-object-types.json`（InstallOrder） |
| CoreFacade | `check_interface_compatibility` + re-export |
| HTTP | `POST /api/platform/apps/fde/interfaces/{id}/check-compatibility` |

## 明确未做（后续）

- ObjectSet / SDK（见独立切片）
- 管理端 Interface draft→review→publish
- 字段级 ACL；父类继承替代
- 附录 N 全量符合
