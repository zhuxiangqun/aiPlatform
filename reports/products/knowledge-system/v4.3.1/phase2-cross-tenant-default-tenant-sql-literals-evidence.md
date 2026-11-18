---
doc_type: Report
title: Phase 2 — default tenant SQL/赋值字面量 SSOT（N09 Batch K51）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / default tenant SQL + assignment literals（Batch K51）证据

> 实施权威：附录 N N09 partial 加深（SQL `tenant_id='default'` / DDL DEFAULT / 赋值回落 → `DomainRouter.default_tenant()`，优先参数化）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件无 SQL 字面量 | pass | `test_targets_use_ssot_not_sql_literal` |
| 生产 tenant 字面量清零 | pass | `test_production_tenant_sql_and_assign_literals_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_default_tenant_sql_literals_k51.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| process_orchestrator / state_history DDL+UPDATE | `default_tenant()` + `?` bind |
| wiki_engine SELECT/UPDATE / path | parameterized + SSOT path segment |
| emotion_tracker / skill_marketplace DDL | f-string DEFAULT |
| summarizer / voice / kb intelligence / routes | assignment / Identity |

## 明确未做

- `collection_id` / `profile_id` DDL `DEFAULT 'default'`
- N09 / 附录 N 全量认证（certified 仍 false）
