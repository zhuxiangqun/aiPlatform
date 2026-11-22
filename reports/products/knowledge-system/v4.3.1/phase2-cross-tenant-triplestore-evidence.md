---
doc_type: Report
title: Phase 2 — TripleStore tenant 隔离证据（N09 SECURITY V2）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / TripleStore tenant 隔离（SECURITY V2）证据

> 实施权威：附录 N N09 partial 加深（统一三元组库读路径按租户过滤）。  
> **未宣称** 空 tenant 强制拒绝 / platform 旁路全量接线 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `tenant_id` 列 + 旧库迁移 | pass | `triple_store._ensure_schema` |
| 显式 tenant → 本租户+共享 `''` | pass | `_tenant_clause` + `test_explicit_tenant_hides_other_tenant` |
| 跨租户行不可见 | pass | 同上 |
| 空 tenant 兼容全量 | pass | `test_empty_tenant_sees_all_legacy` |
| URN syscall / HTTP `/query` `/impact` 透传 | pass | `ontology.py` · `ontology_routes.py` |
| certified 恒 false（N19 联路） | pass | 回执字段不变 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_ontology_engine/test_triple_store_tenant.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py::test_ontology_urn_hotpath \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_query_audit_phase2.py::test_ontology_urn_http_hotpath \
  -v
# 预期：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| 存储 | `TripleStore.get_downstream/upstream/get_by_predicate/stats(..., tenant_id=)` |
| Agent | `sys_ontology_context(..., tenant_id=)` → store 过滤 |
| HTTP | `POST /ontology/query` · `GET /ontology/impact/...` · `GET /ontology/stats?tenant_id=` |

## 明确未做

- 空 `tenant_id` 强制拒绝（仍兼容旧调用全量扫描）
- `aiPlat-platform/api/rest/routes.py` ontology 旁路端点强制 tenant
- N09 / 附录 N 全量认证
