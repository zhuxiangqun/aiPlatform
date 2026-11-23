---
doc_type: Report
title: Phase 2 — ABox ACL condition 有界表达式切片 C（字段级 $not）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 有界表达式切片 C（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在有界表达式切片 A+B 之上。  
> **未宣称** N07/N22 certified / Mongo 全兼容 / `$where`/`$expr`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 字段级 `$not` 取反命中/未命中 | pass | `test_match_condition_field_not` |
| 形态拒配不 fail-open | pass | 同上（空/`$not` 嵌套/布尔/坏 `$type`/`$regex`） |
| deny 门控 | pass | `test_check_entity_acl_field_not_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_expr_lang_c` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_expr_lang_c_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_expr_lang_ab_phase2.py -v
# 实测 2026-11-23：9 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_eval_condition_value` 字段 `$not`；`_eval_regex_condition` / `_eval_type_condition` 形态→`None` |
| UI | `AboxAclPanel`：字段级 `$not` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$where` / `$expr`
- 字段 `$not` 再嵌套字段 `$not` / 字段内布尔算子
- 布尔深度继续 +1 deepen（已停刀）
