---
doc_type: Report
title: Phase 2 — ABox ACL $not→$not（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL $not→$not（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$not` 否定 `$and`/`$or` 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$not→$not` 字段 / `$not→$not→$or` | pass | `test_match_condition_not_not` |
| 超深 `$not` 链拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_not_not_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_not_not` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_not_not_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_not_bool_depth2_phase2.py -v
# 实测 2026-11-22：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_bool_condition`：`$not` 对布尔子树递归求值再取反（禁 fail-open） |
| UI | `AboxAclPanel` condition：`$not` 可否定 `$not` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 深度 4 → 见 `phase2-abox-acl-condition-bool-depth4-evidence.md`
- 完整表达式语言
