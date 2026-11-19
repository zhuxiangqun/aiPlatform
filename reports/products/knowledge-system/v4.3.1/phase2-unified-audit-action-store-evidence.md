---
doc_type: Report
title: Phase 2 — Unified Audit ActionStore 合流证据（N24 Batch J7）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Unified Audit ActionStore（Batch J7）证据

> 实施权威：附录 N N24 partial 加深（ActionStore.action_audit 汇入统一视图/写总线）。  
> **未宣称** N24 certified；不改写 ActionStore 历史。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| insert_audit 热路径入 bus | pass | `test_action_store_hotpath_to_bus` |
| view 含 action_store 流 | pass | `action_store_stream_present`（view suite） |
| 跨租户过滤 | pass | params.tenant_id / tenant_id 召回前过滤 |
| suite/gate certified 恒 false | pass | bus + view suite honesty |
| materialize 含 action_store | pass | `materialize_source_streams` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：16 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Hotpath | `ActionStore.insert_audit` → `append_unified_audit_event(stream=action_store)` |
| View | `list_unified_audit_events` 默认含 `action_store` |
| Materialize | 源流默认含 `action_store` |
| HTTP | `GET …/unified-audit?domain_id=` 可选域过滤 |

## 明确未做

- N24 / 附录 N 全量认证

> 物理 `tenant_id` 列见 Batch J8：`phase2-unified-audit-action-store-tenant-evidence.md`。
