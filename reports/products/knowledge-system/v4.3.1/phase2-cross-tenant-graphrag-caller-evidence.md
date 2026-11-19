---
doc_type: Report
title: Phase 2 — GraphRAG 调用方 tenant 透传证据（N09 Batch K4）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / GraphRAG caller passthrough（Batch K4）证据

> 实施权威：附录 N N09 partial 加深（K3 向量层之上接线 CRAG/治理入口）。  
> **未宣称** GraphIndex 图节点租户隔离 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 既有九探针仍 pass | pass | `run_cross_tenant_isolation_suite` |
| CRAG → GraphRAG 透传 tenant | pass | `graphrag_caller_passthrough` |
| 治理 locate → GraphRAG 透传 tenant | pass | 同上（mock hits） |
| HTTP locate body.tenant_id | pass | `action_routes.ontology_governance_locate` |
| certified 恒 false | pass | gate / honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_cross_tenant_phase2.py -v
# 预期：2 passed（suite 10/10）
```

## 接线

| 入口 | 路径 |
|------|------|
| CRAG | `sys_crag_retrieve(..., tenant_id=)` → `GraphRAGRetriever.retrieve(tenant_id=)` |
| 治理 | `locate_via_ontology_async` / `governance_locate_view` / HTTP locate |
| 套件 | `graphrag_caller_passthrough`（capture retrieve kwargs） |

## 明确未做

- GraphIndex 图节点级租户隔离（图层透传见 Batch K5：`phase2-cross-tenant-graphindex-evidence.md`）
- N09 / 附录 N 全量认证
