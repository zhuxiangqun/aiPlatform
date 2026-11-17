---
doc_type: Report
title: Phase 2 — Unified Audit 写总线证据（N24 Batch J5）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Unified Audit Bus（Batch J5）证据

> 实施权威：附录 N N24 partial 加深（append-only 统一审计写总线；revision_audit 热路径 + materialize）。  
> **未宣称** ActionStore `action_audit` 合并 / Package·Action 热路径全量强制写 bus / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| append 幂等不覆盖 | pass | `test_append_idempotent` |
| revision_audit 热路径入 bus | pass | `test_revision_emit_to_bus` |
| materialize 三流 + view bus | pass | `test_materialize_and_view_bus_stream` |
| 跨租户空 | pass | `test_cross_tenant_empty` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |
| HTTP 经 Facade | pass | `test_unified_audit_http_phase2.py` append/bus/materialize |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：14 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Core | `unified_audit_bus.py` + `fact_ledger._emit_revision_audit` |
| View | `list_unified_audit_events` 默认含 `bus` |
| Facade | `append_fact_unified_audit_event` / `list_fact_unified_audit_bus_events` / `materialize_fact_unified_audit_bus` / suite / gate |
| HTTP | `POST …/unified-audit/append` · `GET …/bus` · `POST …/materialize` · `…/bus/suite|gate` |

## 明确未做

- 合并 ActionStore `action_audit` 为同一流
- N24 / 附录 N 全量认证

> Package/Action 热路径见 Batch J6：`phase2-unified-audit-hotpath-evidence.md`。
