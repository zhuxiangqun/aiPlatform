---
doc_type: Report
title: Phase 2 — ABox ACL condition 浅层 $and/$or（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 浅层 $and/$or（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在字符串字典序之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 矩阵编辑器 / 多层嵌套（浅层 `$not` → 见 not-shallow 证据）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 浅层 $and/$or | pass | `test_match_condition_bool_shallow` |
| 嵌套/混用/超长/空/$not 拒配 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_bool_shallow_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_bool_shallow` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_shallow_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_strcmp_phase2.py -v
# 实测 2026-11-20：6 passed（bool+strcmp）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `match_abox_condition` ← 顶层 `$and`/`$or` |
| 语义 | 纯 `{$and| $or: [字段子句…]}`；一层、≤8 子句；子句不可再含 `$and`/`$or`/`$not` |
| UI | `AboxAclPanel` condition 提示含浅层 `$and|$or` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 浅层 `$not` → 见 `phase2-abox-acl-condition-not-shallow-evidence.md`
- 多层嵌套布尔 / 完整表达式语言
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
