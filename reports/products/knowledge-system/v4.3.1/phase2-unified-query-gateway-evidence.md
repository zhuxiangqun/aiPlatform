---
doc_type: Report
title: Phase 2 — 统一 Query Gateway 证据（N06 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / 统一 Query Gateway（N06 deepen）证据

> 实施权威：附录 N N06 partial 加深。  
> **未宣称** MaterialsChat 全入口收敛 / N06 certified；仅 Core
> `fact` + `object_set` + `wiki` + `index` 路由轴 → 附录 F.1 信封 + 门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 路由轴声明 fact/object_set/wiki/index | pass | `test_routes_declare_fact_object_set_wiki_index` |
| fact 路由 F.1 命中 | pass | suite `fact_route_f1_ok` |
| object_set 路由 F.1 信封 | pass | suite `object_set_route_f1_ok` |
| wiki 路由 F.1（N21 abstain 映射） | pass | suite `wiki_route_f1_ok` |
| index 路由 F.1（KB N21 abstain 映射） | pass | suite `index_route_f1_ok` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_query_gateway_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `unified_query_gateway` / `run_unified_query_gateway_suite` / `evaluate_unified_query_gateway_gate` |
| Facade | `fact_ledger_unified_query_gateway` + suite/gate + routes helpers |
| Wiki/Index | `query_wiki_with_abstain` / `query_kb_with_abstain` → `_n21_to_f1_envelope` |

## 明确未做

- MaterialsChat / 其它应用入口全量收敛到统一 Gateway
- N06 / 附录 N 全量认证 / 关闭 ADR 例外
