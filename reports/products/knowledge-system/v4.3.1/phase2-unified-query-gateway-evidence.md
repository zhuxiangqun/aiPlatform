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
> **未宣称** MaterialsChat 全 Agent 出口收敛 / N06 certified；Core
> `fact` + `object_set` + `wiki` + `index` + `materials_chat` 路由轴 → 附录 F.1
> + MaterialsChat RAG 出口挂 `gateway_f1`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 路由轴声明 fact/object_set/wiki/index/materials_chat | pass | `test_routes_declare_fact_object_set_wiki_index_materials` |
| fact 路由 F.1 命中 | pass | suite `fact_route_f1_ok` |
| object_set 路由 F.1 信封 | pass | suite `object_set_route_f1_ok` |
| wiki 路由 F.1（N21 abstain 映射） | pass | suite `wiki_route_f1_ok` |
| index 路由 F.1（KB N21 abstain 映射） | pass | suite `index_route_f1_ok` |
| materials_chat 路由 F.1（N21 RAG enforce） | pass | suite `materials_chat_route_f1_ok` |
| materials_chat_route | pass | suite / gate |
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
| 核心 | `unified_query_gateway` / `materials_chat_to_f1_envelope` / suite/gate |
| Facade | `fact_ledger_unified_query_gateway` + `materials_chat_to_f1_envelope` |
| 生产 | MaterialsChat RAG 出口附加 `gateway_f1` |

## 明确未做

- MaterialsChat trivial/cache_hit 等非 RAG 出口全量走统一 Gateway
- 其它应用入口全量收敛
- N06 / 附录 N 全量认证 / 关闭 ADR 例外
