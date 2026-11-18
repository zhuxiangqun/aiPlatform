---
doc_type: Report
title: Phase 2 — competition domain 去硬编码证据（N09 Batch K41）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / competition domain（Batch K41）证据

> 实施权威：附录 N N09 partial 加深（`bell-competition` GraphIndex.load → DomainRouter.competition_domain）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| DomainRouter SSOT helper | pass | `test_domain_router_competition_domain` |
| rapid_insight 无裸 competition load | pass | `test_rapid_insight_no_hardcoded_competition_graphindex_load` |
| membership 走 helper | pass | `test_rapid_insight_competition_membership_uses_helper` |
| 生产 GraphIndex.load 字面量空 | pass | `test_production_graphindex_load_literals_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_competition_domain_k41.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_harness_atom_domain_k40.py -v
# 预期：8 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| DomainRouter | `PLATFORM_COMPETITION_DOMAIN` + `competition_domain()` |
| rapid_insight Q2 / icebreaker | `_ri_competition_domain()` → `get_domain_router().competition_domain()` |

## 明确未做

- icebreaker_map 中其他业务域字面量键（supply-chain / bell-* 等）— 非 GraphIndex.load
- `GraphIndex("ai-knowledge")` 等 **ctor** 字面量 → 见 Batch K42
- N09 / 附录 N 全量认证（certified 仍 false）
