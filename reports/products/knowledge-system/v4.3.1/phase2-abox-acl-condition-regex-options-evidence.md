---
doc_type: Report
title: Phase 2 — ABox ACL condition $regex $options:i（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $regex+$options:i（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$regex` 之上。  
> **未宣称** N07/N22 certified / 表达式语言 / 矩阵编辑器 / `m|s|x` flags / 嵌套布尔。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $options:i 忽略大小写 | pass | `test_match_condition_regex_options_i` |
| 非 i / 多余键拒配 | pass | 同测 |
| deny 门控 | pass | `test_check_entity_acl_regex_options_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_regex_options` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_regex_options_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_regex_phase2.py -v
# 实测 2026-11-20：6 passed（options+regex）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_regex_condition` ← `$regex` + 可选 `$options` |
| 语义 | `$options` 仅 `i`；其它字符 / 非 str / 多余键 → 不匹配 |
| UI | `AboxAclPanel` condition 提示含 `$options` 仅 i |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$options` 的 `m`/`s`/`x` 等其它 flags
- 嵌套布尔表达式 / 字符串字典序
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
