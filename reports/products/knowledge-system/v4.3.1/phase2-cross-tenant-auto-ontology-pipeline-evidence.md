---
doc_type: Report
title: Phase 2 — auto_ontology_pipeline tenant 注入证据（N09 Batch K13）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / auto_ontology_pipeline tenant（Batch K13）证据

> 实施权威：附录 N N09 partial 加深（K12 OntologyEngine 之上：ingest 上下文 tenant → `auto_ontology_pipeline_for_doc`）。  
> **未宣称** staleness/diagnostics 多租户 KB 路径 / metric 旁路 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Facade `auto_ontology_pipeline_for_doc(..., tenant_id=)` | pass | `core_facade.py` |
| `load_engine` / `process_chunks` 透传 tenant | pass | `test_auto_ontology_pipeline_passes_tenant` |
| ingest HTTP 经 identity 注入 | pass | `routes.py` `identity.tenant_id` |
| KB watch 透传 `tenant_id` | pass | `kb/service.py` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_auto_ontology_pipeline_tenant_k13.py -v
# 预期：2 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| HTTP ingest | `_resolve_identity` → `_auto_ontology_pipeline(..., tenant_id=)` |
| Watch | `watch_directory(tenant_id=)` → `auto_ontology_pipeline_for_doc` |
| Engine | `load_engine(..., tenant_id=)` → `process_chunks(..., tenant_id=)` → `record_transition` |

## 明确未做

- staleness/diagnostics 租户 KB 路径（见 Batch K14：`phase2-cross-tenant-staleness-diagnostics-evidence.md`）
- metric/scoring/scenario/governance 旁路
- N09 / 附录 N 全量认证
