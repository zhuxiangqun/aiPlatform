---
doc_type: Report
title: Phase 2 — ABox ACL condition 有界表达式切片 A+B（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 有界表达式切片 A+B（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$elemMatch` / `$all` / `$nor` / bool depth≤28（停刀）之上。  
> **未宣称** N07/N22 certified / Mongo 全兼容 / `$where`/`$expr` / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$elemMatch` 内有界布尔谓词 | pass | `test_match_condition_elemmatch_bool_predicate` |
| 嵌套 `$elemMatch`（nest≤2；nest=3 拒配） | pass | `test_match_condition_nested_elemmatch` |
| 点号路径（段≤8；空段/超段拒配） | pass | `test_match_condition_dotted_path` |
| `$size` / `$type`（别名+多选 OR） | pass | `test_match_condition_size_and_type` |
| deny 门控 | pass | `test_check_entity_acl_expr_lang_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_expr_lang_ab` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_expr_lang_ab_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_elemmatch_phase2.py -v
# 实测 2026-11-23：9 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_resolve_attr_value` / `_match_type_condition` / `_match_elem_match_condition(nest)`；`_ELEMMATCH_MAX_NEST=2`；`_DOTTED_MAX_SEGMENTS=8` |
| UI | `AboxAclPanel` condition：有界表达式切片 + `$size`/`$type`/点号路径 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$where` / `$expr` / 字段级 `$not:{$gt:…}`（切片 C）
- 布尔深度继续 +1 deepen（已停刀）
- nest≥3 / 点号段≥9
