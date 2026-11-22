---
doc_type: Report
title: Phase 2 — ABox ACL $not 否定 $and/$or（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL $not 否定 $and/$or（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 bool depth-2 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / `$not→$not` / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$and` 内嵌 `$not(字段)` / `$not→$or` / 纯字段 `$not→$and` | pass | `test_match_condition_not_over_bool` |
| `$not→$not` / `$not` 子树再嵌布尔拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_not_bool_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_not_bool_depth2` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_not_bool_depth2_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth2_phase2.py -v
# 实测 2026-11-22：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_bool_condition`：`$not` 正规求值子树再取反（禁 fail-open） |
| UI | `AboxAclPanel` condition：`$not` 可否定字段或一层 `$and|$or` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$not→$not` / 完整表达式语言
- 深度 3 `$and`/`$or` → 见 `phase2-abox-acl-condition-bool-depth3-evidence.md`
