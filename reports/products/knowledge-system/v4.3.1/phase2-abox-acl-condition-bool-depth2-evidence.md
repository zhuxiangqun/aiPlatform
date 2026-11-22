---
doc_type: Report
title: Phase 2 — ABox ACL condition $and/$or 深度 2（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $and/$or 深度 2（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在浅层布尔之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $and 内嵌 $or / $or 内嵌 $and | pass | `test_match_condition_bool_depth2` |
| 深度 3 / 嵌套 $not 拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_bool_depth2_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_bool_depth2` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth2_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_shallow_phase2.py -v
# 实测 2026-11-22：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `match_abox_condition` → `_match_bool_condition`（`_BOOL_MAX_DEPTH=2`） |
| UI | `AboxAclPanel` condition 诚实文案：深度≤2 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 深度 ≥3 / `$not` 嵌套布尔 / 完整表达式语言
