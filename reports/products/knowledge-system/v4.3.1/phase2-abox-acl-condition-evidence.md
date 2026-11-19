---
doc_type: Report
title: Phase 2 — ABox ACL H.1 condition 最小匹配（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 preview-as-role 之上。  
> **未宣称** N07/N22 certified / 完整 H.1 策略编辑器 / 运算符表达（仅等值）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| match 等值 | pass | `test_match_abox_condition_basics` |
| condition 门控 deny | pass | `test_check_entity_acl_condition_gates_deny` |
| ObjectSet/Facade/HTTP | pass | `test_object_set_and_facade_wire_condition` |
| 薄 UI | pass | `test_abox_panel_wires_condition` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_phase2.py -v
# 实测 2026-11-20：4 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `match_abox_condition` + `set_entity_acl(condition=)` + `check_entity_acl(attrs=)` |
| ObjectSet / link.traverse | 传实例 attrs |
| HTTP | `PUT …/graph/acl/.../entities/{id}` body.condition |
| UI | `AboxAclPanel` condition JSON |
| Preview | payload 兼 attrs；返回 `condition_matched` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 完整 H.1 策略编辑器（principals/effect/actions 矩阵 UI）
- condition 运算符 `$eq/$ne/$in` → 见 `phase2-abox-acl-condition-ops-evidence.md`（仍非表达式语言）
