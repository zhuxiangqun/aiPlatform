---
doc_type: Report
title: Phase 2 — 重建条件三分类契约证据（N05 Batch D）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / 重建条件分类（Batch D）证据

> 实施权威：附录 N N05 partial 加深。  
> **未宣称** Wiki 全量重建认证 / N05 certified；仅 Fact→Graph 投影回执带三分类 + 门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认 exact + reason | pass | `test_classify_default_exact` / `test_project_receipt_has_taxonomy` |
| 不可 exact 能力禁标 exact | pass | `test_classify_rejects_exact_when_not_capable` |
| semantic / non 可分类 | pass | `test_classify_semantic_and_non` |
| 回执缺 mode/reason 失败 | pass | `test_validate_receipt_requires_mode_and_reason` |
| exact + exact_capable=false 失败 | pass | `test_validate_rejects_exact_when_not_capable_flag` |
| non_rebuildable 不写 Graph | pass | `test_project_non_rebuildable_skips_write` |
| certified 恒 false | pass | gate 字段断言 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_rebuild_taxonomy_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_projector_phase2.py -v
# 预期：9 passed
```

实测（2026-11-16）：`9 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `classify_rebuild` / `validate_rebuild_receipt` / `project_facts_to_graph` |
| Facade | `fact_ledger_project_to_graph` + `validate_fact_rebuild_receipt` |

## 明确未做

- Wiki 读模型硬门变更（保持既有）
- 语义重建全流水线
- N05 / 附录 N 全量认证
