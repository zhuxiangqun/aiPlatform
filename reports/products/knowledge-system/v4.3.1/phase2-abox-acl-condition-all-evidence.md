---
doc_type: Report
title: Phase 2 — ABox ACL condition $all（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $all（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$in`/`$nin` + 有界 bool depth（停刀）之上。  
> **未宣称** N07/N22 certified / `$elemMatch` / 完整表达式语言。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$all` 命中/未命中 + 空真 | pass | `test_match_condition_all` |
| 非集合主语 / 超长期望拒配 | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_all_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_all` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_all_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_nin_phase2.py -v
# 实测 2026-11-23：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` `$all`；`_ALL_MAX_ITEMS=32` |
| UI | `AboxAclPanel` condition：$all |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$elemMatch` / 任意表达式语言
- 布尔深度继续 +1 deepen（已停刀）
