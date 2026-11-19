---
doc_type: Report
title: Phase 2 — 运行时 default 漏网清扫（N09 Batch K70）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / runtime default mop（Batch K70）证据

> 实施权威：附录 N N09 partial 加深（K67–K69 漏网的 wiki_* collection 签名、builder module_id、gateway channel、tenant/session 回退 → 既有 `DomainRouter.default_*()` SSOT）。  
> **未宣称** N09 certified。本批**无新增** helper。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helpers_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_ssot` |
| 目标无字面量回退 | pass | `test_target_runtime_default_literals_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_runtime_default_mop_k70.py -v
# 预期：3 passed
```

## 接线（摘要）

| 入口族 | SSOT |
|--------|------|
| wiki_* routers collection 签名 | `default_collection()` |
| builder routes module_id | `default_module_id()` |
| gateway / session channel·agent_type | `default_label()` |
| auth / memory_import / file tenant | `default_tenant()` |
| diagnostics / success_generalizer domain | `default_graph_domain()` |
| materials_chat / pipeline / wiki_engine | `default_collection()` / `default_graph_domain()` |

## 明确未做

- `get_default_model(purpose="default")`（模型 purpose 分类键，非隔离 SSOT）
- observation `kind or "default"` / case_id / model 显示名等非隔离字面量
- N09 / 附录 N 全量认证（certified 仍 false）
