---
doc_type: Report
title: Phase 2 — ontology_editor class/rollback tenant 注入证据（N09 Batch K9）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / ontology_editor class+rollback tenant（Batch K9）证据

> 实施权威：附录 N N09 partial 加深（K8 publish/list 之上接线 rollback + class CRUD + 按租户清 GraphIndex 缓存）。  
> **未宣称** view/monitor/metric 等旁路 CRUD GraphIndex 租户 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| rollback HTTP 注入 `resolve_request_tenant` | pass | `domain_crud.rollback_rule_version` |
| upsert/delete class 透传 tenant → 缓存失效 | pass | `test_rollback_and_class_pass_resolved_tenant` |
| `_invalidate_domain_caches(..., tenant_id=)` | pass | `test_invalidate_domain_caches_loads_tenant_graph` |
| 禁裸 header spoof | pass | 仍走 `resolve_request_tenant` |
| certified 恒 false | pass | honesty（本批不宣称 N09 certified） |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_ontology_editor_tenant_k9.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| HTTP | `POST …/rollback` / `POST …/classes` / `DELETE …/classes/{name}` |
| Facade | `rollback_rule_version` / `upsert_ontology_class` / `delete_ontology_class(_async)` |
| 缓存 | `_invalidate_domain_caches(domain_id, tenant_id=)` → `GraphIndex.load(..., tenant_id=)` |
| 测试 | `test_ontology_editor_tenant_k9.py` |

## 明确未做

- view/meta GraphIndex 缓存 tenant（见 Batch K10：`phase2-cross-tenant-ontology-editor-side-crud-evidence.md`）
- process_monitor `state_changes` 物理 tenant / metric 旁路 / N09 certified
