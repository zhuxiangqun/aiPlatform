---
doc_type: Report
title: Phase 2 — ActionStore tenant_id 存量回填证据（N24 Batch J9）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / ActionStore tenant_id backfill（Batch J9）证据

> 实施权威：附录 N N24 partial 加深（空物理 `tenant_id` 从 `params.tenant_id` 幂等回填）。  
> **未宣称** N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `backfill_tenant_id` 回填空列 | pass | `test_action_store_tenant_backfill` |
| initialize 接线幂等回填 | pass | `ActionStore.initialize` → `backfill_tenant_id` |
| 无 params 租户不猜测默认 | pass | 同测 `e_orphan` 保持空列 |
| 二次调用 updated=0 | pass | 同测 idempotent |
| suite/gate certified 恒 false | pass | 既有 honesty 测 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：18 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| API | `ActionStore.backfill_tenant_id` |
| 生产 caller | `ActionStore.initialize`（幂等） |
| 过滤 | 回填后 `list_audit(tenant_id=)` 命中物理列；空列仍可回退 params |

## 明确未做

- N24 / 附录 N 全量认证
- 为无 `params.tenant_id` 的历史行猜测/注入默认租户
- 改写历史 `params` payload
