---
doc_type: Report
title: Phase 2 — ABox ACL H.1 get 单实体（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 单实体薄导出（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `list_h1_policies` 之上。  
> **未宣称** N07/N22 certified / 完整 H.1 策略编辑器。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| get + 404 | pass | `test_get_graph_h1_policy_and_404` |
| HTTP + 薄 UI | pass | `test_route_and_panel_wire_entity_h1_get` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_get_phase2.py -v
# 实测 2026-11-20：2 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Facade | `get_graph_h1_policy` ← `entity_acl_to_h1` |
| HTTP | `GET …/graph/acl/{domain}/entities/{id}/h1` |
| UI | 「加载 H.1」+ 列表「加载到编辑区」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 完整 H.1 策略编辑器（矩阵式 effect/principals/actions UI）
- `$gt` / `$regex` / 嵌套布尔表达式
