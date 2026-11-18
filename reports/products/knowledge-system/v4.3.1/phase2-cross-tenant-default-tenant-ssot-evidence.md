---
doc_type: Report
title: Phase 2 — default tenant SSOT（知识层签名默认 + 回落）（N09 Batch K49）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default tenant SSOT（Batch K49）证据

> 实施权威：附录 N N09 partial 加深（`tenant_id: str = "default"` / `or "default"` → `DomainRouter.PLATFORM_DEFAULT_TENANT` / `default_tenant()`），范围：**harness/knowledge**。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| PLATFORM_DEFAULT_TENANT + helper | pass | `test_platform_default_tenant_helper` |
| 目标文件签名默认用 SSOT | pass | `test_knowledge_targets_use_default_tenant_ssot` |
| knowledge tenant `or "default"` 回落用 SSOT | pass | `test_knowledge_tenant_or_default_fallbacks_use_ssot` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_tenant_ssot_k49.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter SSOT | `PLATFORM_DEFAULT_TENANT` + `default_tenant()` |
| context_bus | `_resolve_graph_tenant` → `default_tenant()` |
| knowledge 签名默认 / 回落 | GraphIndex / scoring / metric / process / staleness 等 |

## 明确未做

- `core_facade` / syscalls / memory / platform 等其它层签名默认 → 见 Batch K50
- wiki_engine SQL 字面量 `tenant_id='default'`
- collection_id / domain_id / session_id 的 `"default"` 回落
- N09 / 附录 N 全量认证（certified 仍 false）
