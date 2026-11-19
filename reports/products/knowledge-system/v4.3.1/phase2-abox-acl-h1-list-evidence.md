---
doc_type: Report
title: Phase 2 — ABox ACL H.1 list_h1_policies（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 薄导出列表（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `apply_h1_policy` 之上。  
> **未宣称** N07/N22 certified / 完整 H.1 策略编辑器。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| list 排序 + 投影 | pass | `test_list_h1_policies_sorted` |
| HTTP + 薄 UI | pass | `test_get_routes_and_panel_wire_h1_list` |
| Facade | pass | `test_facade_exports_list_graph_h1_policies` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_list_phase2.py -v
# 实测 2026-11-20：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `list_h1_policies` ← `entity_acl_to_h1` |
| Facade | `list_graph_h1_policies` |
| HTTP | `GET …/graph/acl/{domain}` 含 `h1_policies`；`GET …/graph/acl/{domain}/h1` |
| UI | `AboxAclPanel` H.1 列表 +「刷新 H.1 列表」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 单实体 H.1 GET → 见 `phase2-abox-acl-h1-get-evidence.md`
- 完整 H.1 策略编辑器（矩阵式 effect/principals/actions UI）
- `$gt` / `$regex` / 嵌套布尔表达式
