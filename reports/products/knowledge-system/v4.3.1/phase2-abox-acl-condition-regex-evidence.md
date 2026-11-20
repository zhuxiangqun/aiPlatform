---
doc_type: Report
title: Phase 2 — ABox ACL condition $regex（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $regex（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$gt/$gte/$lt/$lte` 之上。  
> **未宣称** N07/N22 certified / 表达式语言 / 矩阵编辑器 / `$options` flags / 嵌套布尔。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $regex 命中/拒配 | pass | `test_match_condition_regex_ops` |
| 非法/过长/缺失拒配 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_regex_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_regex` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_regex_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_cmp_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_ops_phase2.py -v
# 实测 2026-11-20：9 passed（regex+cmp+ops）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` ← `$regex` |
| 语义 | 仅 str 模式 ≤128；主语截断 ≤4096；非法编译 → 不匹配；无 `$options` |
| UI | `AboxAclPanel` condition 提示含 `$regex` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$options` / 嵌套布尔表达式 / 字符串字典序
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
