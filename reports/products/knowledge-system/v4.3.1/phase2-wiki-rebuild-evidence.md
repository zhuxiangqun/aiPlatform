---
doc_type: Report
title: Phase 2 — Wiki 有条件重建证据（N05 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N05 Wiki 有条件重建证据

> 实施权威：附录 N N05 partial 加深。  
> **未宣称** Wiki 引擎全量索引/FTS 热路径 / 人工写绕过 / N05 certified。  
> 派生视图：Fact → `wiki_rebuild_pages`；复用三分类 `rebuild_mode`/`rebuild_reason`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| exact 写派生页 | pass | suite `exact_writes_pages` |
| non 不写页 | pass | suite `non_skips_write` |
| semantic 写且标记 | pass | suite `semantic_writes_marked` |
| 租户必填 | pass | suite `tenant_required` |
| 回执门槛门 | pass | suite `gate_receipt_ok` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_rebuild_phase2.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `project_facts_to_wiki` / `list_wiki_rebuild_pages` / suite/gate |
| Facade / HTTP | `fact_ledger_project_to_wiki` + `/fde/wiki-rebuild*` |
| 配置 | `AIPLAT_WIKI_REBUILD_DB` |

## 明确未做

- 替换 `wiki_engine` / FTS 全量重建热路径
- 开放读模型 collection 人工写
- N05 certified / 关闭 ADR 例外
