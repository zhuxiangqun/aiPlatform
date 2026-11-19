---
doc_type: Report
title: Phase 2 — Unified Audit View 证据（N24 Batch J3）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Unified Audit View（Batch J3）证据

> 实施权威：附录 N N24 partial 加深（Package + ActionExecution + revision_audit 只读汇合）。  
> **未宣称** Package+Action 全量写总线 / 单一 append-only 总线表 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 三流汇合可见 | pass | `test_three_streams_present` |
| streams 过滤生效 | pass | `test_stream_filter_config` |
| 跨租户空 | pass | `test_cross_tenant_empty` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |
| HTTP 经 Facade | pass | `test_unified_audit_http_phase2.py` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_unified_audit_view_phase2.py \
  aiPlat-platform/tests/test_unified_audit_http_phase2.py -v
# 预期：7 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Core | `unified_audit_view.py` + `list_package_versions` + `list_action_executions` |
| Facade | `list_fact_unified_audit_events` / suite / gate |
| HTTP | `GET/POST …/fde/unified-audit*` |

## 明确未做

- 写入统一审计总线表 / 强制全量事件进 ActionExecution
- 合并 ActionStore `action_audit` 为同一流
- N24 / 附录 N 全量认证

> 管理端统一审计 UI 见 Batch J4：`phase2-unified-audit-ui-evidence.md`。
