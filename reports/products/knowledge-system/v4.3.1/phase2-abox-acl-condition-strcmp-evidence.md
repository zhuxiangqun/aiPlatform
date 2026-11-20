---
doc_type: Report
title: Phase 2 — ABox ACL condition 字符串字典序（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 字符串字典序（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$regex+$options:i` 之上。  
> **未宣称** N07/N22 certified / 表达式语言 / 矩阵编辑器 / 嵌套布尔。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| str 字典序 $gt/$gte/$lt/$lte | pass | `test_match_condition_strcmp_ops` |
| 混合类型拒配 + 数值路径保留 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_strcmp_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_strcmp` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_strcmp_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_cmp_phase2.py -v
# 实测 2026-11-20：6 passed（strcmp+cmp）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` ← `$gt/$gte/$lt/$lte` |
| 语义 | 两端均为 `str` → 字典序；两端均为 number → 数值；混合/`bool`/缺失 → 不匹配 |
| UI | `AboxAclPanel` condition 提示含「str 字典序」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 嵌套布尔表达式（`$and`/`$or`）
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
