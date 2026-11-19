---
doc_type: Report
title: Phase 2 — integration/server/memory session 运行时回退 SSOT（N09 Batch K61）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / integration+memory session runtime fallbacks（Batch K61）证据

> 实施权威：附录 N N09 partial 加深（`integration` 聚合 / `server` / memory / seci / platform approvals·gateway 运行时 `session_id or "default"` → `DomainRouter.default_session()`）。  
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
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_integration_memory_session_fallbacks_k61.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `harness/integration.py` + `integration/__init__.py` | req.session_id 回退 |
| `server.py` | meta session |
| memory manager / profile_builder / seci_engine | session→namespace |
| platform approvals / gateway | body/ctx/resolved session |

## 明确未做

- MemoryManager `namespace or "default"` 缓存键（namespace 语义，非 session_id 字段）
- collection/domain_id/workspace_id 字面量回退
- N09 / 附录 N 全量认证（certified 仍 false）
