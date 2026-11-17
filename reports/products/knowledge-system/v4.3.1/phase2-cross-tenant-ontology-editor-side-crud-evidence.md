---
doc_type: Report
title: Phase 2 — ontology_editor view/meta tenant 注入证据（N09 Batch K10）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / ontology_editor view+meta tenant（Batch K10）证据

> 实施权威：附录 N N09 partial 加深（K9 class/rollback 之上接线 view 写路径 + domain meta 缓存失效）。  
> **未宣称** process_monitor `state_changes` 物理 tenant 列 / metric 旁路 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| view upsert/delete 注入 `resolve_request_tenant` | pass | `view_crud.py` |
| domain meta 透传 tenant → 缓存失效 | pass | `test_view_and_meta_pass_resolved_tenant` |
| Facade `_invalidate_domain_caches(..., tenant_id=)` | pass | `upsert_view_for_domain` / `update_ontology_domain_meta` |
| 禁裸 header spoof | pass | 仍走 `resolve_request_tenant` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_ontology_editor_tenant_k10.py -v
# 预期：2 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| HTTP | `POST/DELETE …/views` / `PUT …/domains/{id}` |
| Facade | `upsert_view_for_domain` / `delete_view_for_domain` / `update_ontology_domain_meta` |
| 缓存 | `_invalidate_domain_caches(domain_id, tenant_id=)` |
| 测试 | `test_ontology_editor_tenant_k10.py` |

## 明确未做

- process_monitor / `state_changes` 物理 tenant（见 Batch K11：`phase2-cross-tenant-process-monitor-evidence.md`）
- metric/scoring/scenario/governance 旁路 CRUD
- N09 / 附录 N 全量认证
