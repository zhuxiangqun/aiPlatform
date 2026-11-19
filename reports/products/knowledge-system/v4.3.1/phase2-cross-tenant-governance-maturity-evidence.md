---
doc_type: Report
title: Phase 2 — governance/maturity GraphIndex 租户证据（N09 Batch K19）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / governance·maturity tenant（Batch K19）证据

> 实施权威：附录 N N09 partial 加深（K18 HTTP 回显之上：run_cycle/maturity 透传）。  
> **未宣称** context_bus/evolver 等其它 GraphIndex 调用面 / N09 certified（completeness/audit 见 K20）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `compute_domain_maturity(..., tenant_id=)` → GraphIndex | pass | `test_maturity_and_pipeline_source_wire_tenant` |
| `run_cycle`/`run_all_domains` 透传 | pass | 同上 + HTTP |
| scenario refresh/compare 透传 | pass | `test_scenario_refresh_passes_tenant` |
| HTTP → run_cycle tenant | pass | `test_run_cycle_http_forwards_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_ontology_editor_tenant_k19.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| maturity | `GraphIndex.load(domain_id, tenant_id=)` + state_changes tenant 过滤 |
| governance_pipeline | `run_cycle(..., tenant_id=)` → scenario/quality/publishing |
| DomainRouter | `refresh_domain_maturity(..., tenant_id=)` |
| HTTP | governance `run-cycle`/`run-all` + scenario refresh/compare |

## 明确未做

- ontology completeness/audit/validator → **K20 已加深**；context_bus/evolver 仍残留
- N09 / 附录 N 全量认证
