---
doc_type: Report
title: Phase 2 — collection/namespace 运行时回退 SSOT（N09 Batch K62）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / collection+namespace runtime fallbacks（Batch K62）证据

> 实施权威：附录 N N09 partial 加深（facade/kb/wiki/routes/delivery 运行时 `collection_id or "default"` → `DomainRouter.default_collection()`；MemoryManager `namespace or "default"` → `default_session()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_collection_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_collection_namespace_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_collection_namespace_fallbacks_k62.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| core_facade / kb_facade / knowledge router / kb_tools | collection 回退 |
| wiki_read_model / session_wiki / conversations / knowledge_retrieval | collection |
| policy_gate / diagnostics / platform routes / kb telemetry / delivery | collection |
| MemoryManager | namespace → `default_session()` |
| retrieval syscall | domain/collection 回退 |

## 明确未做

- `domain_id` / `workspace_id` / `view_name` / `ProfileConfig(name="default")` 字面量
- `AIPLAT_DEFAULT_TENANT` 运维 env
- N09 / 附录 N 全量认证（certified 仍 false）
