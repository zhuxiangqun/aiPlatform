---
doc_type: Report
title: Phase 2 — metric/scoring/scenario/governance CRUD 租户证据（N09 Batch K18）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / metric·scoring·scenario·governance tenant（Batch K18）证据

> 实施权威：附录 N N09 partial 加深（ontology_editor 旁路 CRUD）。  
> **未宣称** N09 certified（governance/maturity 透传见 K19）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 四 CRUD 用 `resolve_request_tenant` | pass | `test_metric_scoring_scenario_governance_source_wires_tenant` |
| scoring `GraphIndex.load(..., tenant_id=)` | pass | `test_scoring_engine_source_loads_tenant_graph` |
| metric SQL 过滤 `tenant_id` | pass | `test_metric_engine_source_filters_tenant_sql` |
| HTTP 透传身份租户 | pass | `test_metric_value_passes_resolved_tenant` / `test_scoring_evaluate_passes_resolved_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_ontology_editor_tenant_k18.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| metric_crud | `resolve_request_tenant` → `compute/get_trend/scorecard(..., tenant_id=)` |
| scoring_crud | `resolve_request_tenant` → `evaluate/evaluate_batch/get_alerts(..., tenant_id=)` → `GraphIndex.load` |
| scenario_crud / governance_crud | `resolve_request_tenant` 回显 `tenant_id`（管线内部更深透传未宣称） |

## 明确未做

- governance `run_cycle` / maturity → **K19 已加深**（本文件保留 K18 范围陈述）
- N09 / 附录 N 全量认证
