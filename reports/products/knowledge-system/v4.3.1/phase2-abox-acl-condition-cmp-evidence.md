---
doc_type: Report
title: Phase 2 — ABox ACL condition $gt/$gte/$lt/$lte（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition 数值比较（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$exists` 之上。  
> **未宣称** N07/N22 certified / 表达式语言 / 矩阵编辑器 / 字符串序比较。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $gt/$gte/$lt/$lte | pass | `test_match_condition_cmp_ops` |
| 非数字/bool 拒绝 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_cmp_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_cmp` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_cmp_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_ops_phase2.py -v
# 实测 2026-11-20：9 passed（cmp+ops+exists）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` ← `$gt/$gte/$lt/$lte` |
| 语义 | 仅 `int`/`float`；`bool`/字符串/缺失 → 不匹配 |
| UI | `AboxAclPanel` condition 提示含 `$gt`…`$lte` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$regex` → 见 `phase2-abox-acl-condition-regex-evidence.md`
- 字符串字典序 → 见 `phase2-abox-acl-condition-strcmp-evidence.md`
- 嵌套布尔表达式
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
