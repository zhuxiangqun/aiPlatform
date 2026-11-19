---
doc_type: Report
title: Phase 2 — Query/Form/签名默认参数 SSOT（N09 Batch K67）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Query+Form+signature defaults（Batch K67）证据

> 实施权威：附录 N N09 partial 加深（HTTP `Query`/`Form`/签名默认 `"default"` → `DomainRouter.default_*()`；MemoryManager namespace 签名回退；顺带修 pre-commit `grep -c || echo 0` 双 0 整数比较）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_ssot` |
| 目标无 Query/Form/签名字面量 | pass | `test_target_query_form_signature_defaults_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_query_form_signature_defaults_k67.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| workbench/core kanban Query | `default_profile()` |
| FDE extraction Form / action Query | `default_graph_domain()` |
| FDE marking Query / rapid_insight / conversations | `default_collection()` |
| server/org/value Query tenant | `default_tenant()` |
| wiki / wiki_scenes collection | `default_collection()` |
| MemoryManager namespace | `default_session()` |
| pre-commit-hook | `grep -c \|\| true` |

## 明确未做

- builder `module_id="default"` / `purpose="default"` / channel 枚举等非隔离语义字面量
- N09 / 附录 N 全量认证（certified 仍 false）
