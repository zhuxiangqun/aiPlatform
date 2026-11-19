---
doc_type: Report
title: Phase 2 — ontology quality GraphIndex 租户证据（N09 Batch K20）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / ontology completeness·audit·validator tenant（Batch K20）证据

> 实施权威：附录 N N09 partial 加深（质量审计面 GraphIndex）。  
> **未宣称** evolver/SECI 等其它 GraphIndex 调用面 / N09 certified（context_bus/health 见 K21）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| OCS C5 / audit / validator `GraphIndex.load(..., tenant_id=)` | pass | `test_completeness_audit_validator_source_wire_tenant` |
| diagnostics ontology-audit 身份绑定 | pass | `test_diagnostics_ontology_audit_uses_actor_from_http` |
| C5 / HTTP 透传 | pass | `test_score_c5_loads_tenant_graph` / `test_get_ontology_audit_forwards_identity_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_quality_tenant_k20.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| completeness | `_score_c5` / `compute_domain_ocs(..., tenant_id=)` |
| audit | `OntologyAuditor.audit_domain/all(..., tenant_id=)` |
| validator | `validate_domain(..., tenant_id=)` |
| diagnostics | `actor_from_http` → audit |

## 明确未做

- context_bus / system_health → **K21 已加深**（本文件保留 K20 范围陈述）
- system_evolver / SECI / orchestrated_retrieval 默认 GraphIndex.load
- N09 / 附录 N 全量认证
