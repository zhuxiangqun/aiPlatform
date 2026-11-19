---
doc_type: Report
title: Phase 2 — facade/system/eval/infra GraphIndex 租户证据（N09 Batch K29）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / facade · system · eval · infra tenant（Batch K29）证据

> 实施权威：附录 N N09 partial 加深（CoreFacade 残余、system、wiki_ontology_domains、diagnostics_capability、constraint_validator、dynamic_mapper、rule_validator、semantic_gate）。  
> **未宣称** skills/registry / org_kpi / pipeline_engine / execution router bare load / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 8 目标文件无 bare load | pass | `test_k29_sources_wire_tenant` |
| RuleValidator 解析租户 | pass | `test_rule_validator_init_resolves_tenant` |
| SemanticGate 透传 | pass | `test_semantic_gate_loads_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_facade_system_infra_tenant_k29.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| core_facade 残余 2 处 | `_resolve_graph_tenant()` |
| system / wiki_ontology_domains / diagnostics_capability | `_resolve_graph_tenant()` / 循环内 `tid` |
| constraint_validator / dynamic_mapper / semantic_gate | `_resolve_graph_tenant()` |
| RuleValidator | `__init__(tenant_id=)` → `self._tenant_id` |

## 明确未做

- skills/registry / org_kpi / pipeline_engine / execution router → 见 Batch K30
- N09 / 附录 N 全量认证
