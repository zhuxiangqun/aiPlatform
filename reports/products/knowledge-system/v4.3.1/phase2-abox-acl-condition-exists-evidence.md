---
doc_type: Report
title: Phase 2 — ABox ACL condition $exists（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL condition $exists（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$eq/$ne/$in` 与 H.1 薄表单之上。  
> **未宣称** N07/N22 certified / 表达式语言 / 矩阵编辑器。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| $exists true/false | pass | `test_match_condition_exists` |
| deny 门控 | pass | `test_check_entity_acl_exists_gates_deny` |
| 薄 UI 文案 | pass | `test_panel_documents_exists` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_condition_exists_phase2.py -v
# 实测 2026-11-20：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `_match_condition_value` ← `$exists` |
| 语义 | `$exists:true`→字段非 None；`$exists:false`→字段缺失 |
| UI | `AboxAclPanel` condition 提示含 `$exists` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- `$gt/$gte/$lt/$lte` → 见 `phase2-abox-acl-condition-cmp-evidence.md`
- `$regex` → 见 `phase2-abox-acl-condition-regex-evidence.md`
- 嵌套布尔表达式
- 完整 H.1 矩阵编辑器（多角色×多动作网格）
