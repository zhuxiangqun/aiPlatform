---
doc_type: Report
title: Phase 2 — ActionStore 物理 tenant_id 证据（N24 Batch J8）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / ActionStore tenant_id（Batch J8）证据

> 实施权威：附录 N N24 partial 加深（`action_audit.tenant_id` 物理列 + 召回前过滤）。  
> **未宣称** N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 表含物理 `tenant_id` | pass | `CREATE` + `ALTER` 迁移 |
| insert 写入物理列 | pass | `insert_audit` |
| list_audit 按 tenant 过滤 | pass | `test_action_store_physical_tenant_column` |
| view action_store 跨租户空 | pass | 同测 |
| suite/gate certified 恒 false | pass | 既有 honesty 测 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：17 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Schema | `ActionStore.initialize` + `idx_action_audit_tenant` |
| Write | `insert_audit` 写 `tenant_id` |
| Read | `list_audit(tenant_id=)`；存量空列回退 `json_extract(params,'$.tenant_id')` |
| View | `_action_store_events` 经 `list_audit(tenant_id=)` |

## 明确未做

- N24 / 附录 N 全量认证

> 存量空列强制回填见 Batch J9：`phase2-unified-audit-action-store-tenant-backfill-evidence.md`。
