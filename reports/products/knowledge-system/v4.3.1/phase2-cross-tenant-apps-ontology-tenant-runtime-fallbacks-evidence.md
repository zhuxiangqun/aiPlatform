---
doc_type: Report
title: Phase 2 — apps + ontology_engine tenant 运行时回退 SSOT（N09 Batch K57）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / apps + ontology tenant runtime fallbacks（Batch K57）证据

> 实施权威：附录 N N09 partial 加深（`ontology_branch` / `state_history` / apps org·value·fde·prompt / `code_review_gold` 运行时 `tenant_id or "default"` → `DomainRouter.default_tenant()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_default_tenant_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_tenant_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_apps_ontology_tenant_runtime_fallbacks_k57.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `ontology_branch` | tid 解析 / 前缀 / legacy YAML / list 比较 |
| `state_history` | strip-or → `default_tenant()` |
| `code_review_gold._safe_tenant` | sanitize 回退 |
| org / value safety / fde rapid_insight / prompt | body/session/key 回退 |

## 明确未做

- 其它 apps 模块零星 `domain_id or "default"`（非 tenant）
- N09 / 附录 N 全量认证（certified 仍 false）
