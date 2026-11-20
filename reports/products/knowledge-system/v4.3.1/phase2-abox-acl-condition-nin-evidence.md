---
doc_type: Report
title: Phase 2 — ABox ACL condition $nin（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $nin（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在浅层 `$not` 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 矩阵编辑器 / 多层嵌套。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $nin 命中/拒配 | pass | `test_match_condition_nin_ops` |
| 非 list 拒配 + $in 回归 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_nin_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_nin` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_nin_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_ops_phase2.py -v
# 实测 2026-11-20：6 passed（nin+ops）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` ← `$nin` |
| 语义 | `$in` 对偶；arg 须为 list/tuple/set；空列表 → 恒 True |
| UI | `AboxAclPanel` condition 提示含 `$nin` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 多层嵌套布尔 / 完整表达式语言
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
