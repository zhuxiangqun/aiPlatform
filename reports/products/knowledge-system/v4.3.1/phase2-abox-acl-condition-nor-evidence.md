---
doc_type: Report
title: Phase 2 — ABox ACL condition $nor（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $nor（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在有界 bool depth（当前 ≤27，**停刀不再 +1**）+ 拒配传播之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$nor` 命中/未命中 + 嵌套 | pass | `test_match_condition_nor` |
| `$not→$nor` 正规取反 / 拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_nor_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_nor` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_nor_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth27_phase2.py -v
# 实测 2026-11-23：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_BOOL_OPS` 含 `$nor`；`$nor` ≡ ¬(∨)；拒配 `None` 传播 |
| UI | `AboxAclPanel` condition：$and\|$or\|$nor\|$not |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$all` / `$elemMatch` / 任意表达式语言
- 布尔深度继续 +1 deepen（已停刀）
