---
doc_type: Report
title: Phase 2 — session 运行时回退 SSOT（N09 Batch K59）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / session runtime fallbacks（Batch K59）证据

> 实施权威：附录 N N09 partial 加深（facade/diagnostics/file_checkpoint/approval gates/session store/platform routes/FDE 运行时 `session_id or "default"` → `DomainRouter.default_session()`；附带 `consultant_personal` tenant strip-or）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_session_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_session_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_session_runtime_fallbacks_k59.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `core_facade` attendance | `default_session()` |
| diagnostics / FDE / routes / execution_snapshots | session 回退 |
| file_checkpoint / approval_inbox·reviewer / session_write_provenance / session_mixin | session 分区键 |
| `consultant_personal` | tenant strip-or |

## 明确未做

- agents/jobs/plugins/materials_chat/pipeline_engine/compressor/langgraph 等其它 session 字面量 → 见 K60
- collection/domain_id/workspace_id 字面量回退（非 session/tenant）
- N09 / 附录 N 全量认证（certified 仍 false）
