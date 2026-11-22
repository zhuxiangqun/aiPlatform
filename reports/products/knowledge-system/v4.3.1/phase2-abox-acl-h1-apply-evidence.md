---
doc_type: Report
title: Phase 2 — ABox ACL H.1 apply_h1_policy（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 薄导入（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `masked_properties` 之上。  
> **未宣称** N07/N22 certified / 完整 H.1 策略编辑器（effect/principals 矩阵 UI）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| apply + to_h1 往返 | pass | `test_apply_h1_policy_roundtrip` |
| resource/effect 校验 | pass | `test_apply_h1_policy_rejects_mismatch_and_bad_effect` |
| HTTP + 薄 UI | pass | `test_put_route_and_panel_wire_h1_policy` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_apply_phase2.py -v
# 实测 2026-11-20：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `apply_h1_policy` ← effect/principals/actions/condition/masked_properties |
| Facade | `apply_graph_h1_policy` |
| HTTP | `PUT …/entities/{id}` body.`h1_policy`（优先） |
| UI | `AboxAclPanel`「应用 H.1」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- H.1 薄导出列表 → 见 `phase2-abox-acl-h1-list-evidence.md`
- 完整 H.1 策略编辑器（矩阵式 effect/principals/actions UI）
- `$gt` / `$regex` / 嵌套布尔表达式
