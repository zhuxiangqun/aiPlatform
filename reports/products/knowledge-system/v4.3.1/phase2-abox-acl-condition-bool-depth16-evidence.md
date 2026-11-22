---
doc_type: Report
title: Phase 2 — ABox ACL condition $and/$or 深度 16（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $and/$or 深度 16（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 depth-15 + 拒配传播之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / 任意深度。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 深度 16 命中/未命中 | pass | `test_match_condition_bool_depth16` |
| 深度 17 拒配 + `$not` 不可 fail-open | pass | 同上 |
| deny 门控 | pass | `test_check_entity_acl_bool_depth16_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_bool_depth16` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth16_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_bool_depth15_phase2.py -v
# 实测 2026-11-22：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_BOOL_MAX_DEPTH=16` + `Optional[bool]` 拒配传播 |
| UI | `AboxAclPanel` condition：深度≤16 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 深度 17 → 见 `phase2-abox-acl-condition-bool-depth17-evidence.md`
- 完整表达式语言
