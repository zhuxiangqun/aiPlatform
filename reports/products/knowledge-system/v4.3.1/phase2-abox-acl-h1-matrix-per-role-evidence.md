---
doc_type: Report
title: Phase 2 — ABox ACL H.1 per-role 矩阵（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 per-role 矩阵（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在薄矩阵（共享 actions）之上。  
> **未宣称** N07/N22 certified / 任意 RBAC 产品。有界表达式 A+B+C + H.1 条件面冻结见对应证据。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| role_actions 独立写入/回读 | pass | `test_apply_h1_role_actions_per_role` |
| 非法 role_actions 拒写 | pass | `test_apply_h1_role_actions_rejects_bad` |
| 薄 UI 文案 | pass | `test_panel_documents_h1_matrix_per_role` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_matrix_per_role_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_apply_phase2.py -v
# 实测 2026-11-20：5 passed（per-role+apply）

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `apply_h1_policy` / `entity_acl_to_h1` ← `role_actions` |
| 语义 | 有 `role_actions` → 每角色独立动作；否则 principals×共享 actions |
| UI | `AboxAclPanel` 矩阵勾选写入 `role_actions`；`actions` 为并集 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 任意自由输入角色/动作轴（配置轴 deepen → `phase2-abox-acl-h1-matrix-config-axes-evidence.md`）
- `$where`/`$expr`（H.1 条件面 deepen 已冻结）
