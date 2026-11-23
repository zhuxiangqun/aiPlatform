---
doc_type: Report
title: Phase 2 — ABox ACL H.1 矩阵配置轴（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-22
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 矩阵配置轴（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 per-role 矩阵之上。  
> **未宣称** N07/N22 certified / 任意 RBAC 产品。有界表达式 A+B+C 见 expr-lang 证据；条件面 deepen 已冻结见 `phase2-abox-acl-h1-condition-freeze-evidence.md`。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| h1_matrix_axes 默认轴 | pass | `test_h1_matrix_axes_defaults` |
| env JSON 扩展角色入轴 | pass | `test_h1_matrix_axes_env_extends` |
| 薄 UI 读 crud_matrix.h1_matrix_* | pass | `test_panel_documents_h1_matrix_config_axes` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_matrix_config_axes_phase2.py -v
# 实测 2026-11-22：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-22：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `h1_matrix_axes` ← `load_role_action_matrix` / `AIPLAT_ABOX_ROLE_ACTION_MATRIX` |
| Facade/HTTP | `crud_matrix_doc` → GET `/graph/acl/{domain}` `.crud_matrix.h1_matrix_*` |
| UI | `AboxAclPanel` `h1MatrixRoles` / `h1MatrixActions` 运行时覆盖默认兜底 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 任意自由输入角色/动作轴（仍须经 env/配置 SSOT）
- `$where`/`$expr`（H.1 条件面 deepen 已冻结）
