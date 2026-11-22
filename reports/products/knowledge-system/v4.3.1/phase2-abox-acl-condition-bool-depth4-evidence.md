---
doc_type: Report
title: Phase 2 — ABox ACL condition $and/$or 深度 4（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $and/$or 深度 4（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 depth-3 / `$not→$not` 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$and→$or→$and→$or`（深度 4） | pass | `test_match_condition_bool_depth4` |
| 深度 5 拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_bool_depth4_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_bool_depth4` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth4_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth3_phase2.py -v
# 实测 2026-11-22：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_BOOL_MAX_DEPTH=4` → `_match_bool_condition`（拒配 `None` 不可被外层 `$not` 取反） |
| UI | `AboxAclPanel` condition：深度≤4 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 深度 ≥5 / 完整表达式语言
