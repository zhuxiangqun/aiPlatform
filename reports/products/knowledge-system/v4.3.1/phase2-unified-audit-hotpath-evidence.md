---
doc_type: Report
title: Phase 2 — Unified Audit Package/Action 热路径证据（N24 Batch J6）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Unified Audit Hotpath（Batch J6）证据

> 实施权威：附录 N N24 partial 加深（Package publish/rollback + ActionExecution persist 热路径写总线）。  
> **未宣称** ActionStore `action_audit` 合并 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| publish_package 入 bus | pass | `test_package_and_action_hotpath_to_bus` |
| persist_execution 入 bus | pass | `test_package_and_action_hotpath_to_bus` |
| suite 含 package/action hotpath | pass | `package_hotpath_to_bus` / `action_hotpath_to_bus` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |
| materialize 与热路径幂等共存 | pass | `test_materialize_and_view_bus_stream` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_bus_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：15 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Package | `ontology_package.publish_package` / `rollback_package` → `append_unified_audit_event` |
| Action | `action_execution.persist_execution` → `append_unified_audit_event` |
| Suite | `run_unified_audit_bus_suite` 增 `package_hotpath_to_bus` / `action_hotpath_to_bus` |

## 明确未做

- N24 / 附录 N 全量认证

> ActionStore `action_audit` 合流见 Batch J7：`phase2-unified-audit-action-store-evidence.md`。
