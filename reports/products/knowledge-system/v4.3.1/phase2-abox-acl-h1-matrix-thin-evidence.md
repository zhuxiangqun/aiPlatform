---
doc_type: Report
title: Phase 2 — ABox ACL H.1 薄矩阵（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 薄矩阵（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 `$nin` 与 H.1 薄表单之上。  
> **未宣称** N07/N22 certified / 完整表达式语言（per-role → 见 `phase2-abox-acl-h1-matrix-per-role-evidence.md`）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 薄矩阵 UI（固定角色×动作轴） | pass | `test_panel_documents_h1_matrix_thin` |
| 写入折叠为共享 actions | pass | `test_panel_matrix_folds_to_shared_actions` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_matrix_thin_phase2.py -v
# 实测 2026-11-20：2 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `AboxAclPanel` ← `H1_MATRIX_ROLES` × `H1_MATRIX_ACTIONS` |
| 语义 | 无 `role_actions` 时：勾选折叠为 `principals` + **共享** `actions`；有则见 per-role 证据 |
| 诚实锁 | 薄路径不单独存 per-cell；非 certified |


## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- per-role 差异矩阵 → 见 `phase2-abox-acl-h1-matrix-per-role-evidence.md`
- 多层嵌套布尔 / 完整表达式语言
