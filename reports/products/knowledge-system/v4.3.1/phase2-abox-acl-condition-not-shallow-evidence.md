---
doc_type: Report
title: Phase 2 — ABox ACL condition 浅层 $not（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 浅层 $not（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在浅层 `$and`/`$or` 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 矩阵编辑器 / 多层嵌套。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 浅层 $not 否定字段子句 | pass | `test_match_condition_not_shallow` |
| list/空/嵌套/混键拒配 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_not_shallow_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_not_shallow` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_not_shallow_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_shallow_phase2.py -v
# 实测 2026-11-20：6 passed（not+bool）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `match_abox_condition` ← 顶层 `$not` |
| 语义 | 纯 `{$not: {字段子句}}`；一层；list/空/嵌套布尔/混键 → 不匹配 |
| UI | `AboxAclPanel` condition 提示含浅层 `$not` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$nin` → 见 `phase2-abox-acl-condition-nin-evidence.md`
- 多层嵌套布尔 / 完整表达式语言
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
