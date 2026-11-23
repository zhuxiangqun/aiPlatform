---
doc_type: Report
title: Phase 2 — ABox ACL condition $elemMatch（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $elemMatch（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$all` + `$nor` + 有界 bool depth（停刀）之上。  
> **未宣称** N07/N22 certified / Mongo 全兼容。嵌套 `$elemMatch` + 布尔谓词见 `phase2-abox-acl-condition-expr-lang-ab-evidence.md`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 文档元素字段 AND | pass | `test_match_condition_elemmatch` |
| 标量元素值算子 | pass | 同上 |
| 拒配（非数组/空谓词） | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_elemmatch_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_elemmatch` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_elemmatch_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_all_phase2.py -v
# 实测 2026-11-23：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_elem_match_condition`；`_ELEMMATCH_MAX_ITEMS=64` |
| UI | `AboxAclPanel` condition：$elemMatch |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 任意表达式语言 / `$where`/`$expr`（有界切片 A+B → `phase2-abox-acl-condition-expr-lang-ab-evidence.md`）
- 布尔深度继续 +1 deepen（已停刀）
