---
doc_type: Report
title: Phase 2 — ABox ACL H.1 薄表单（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 薄表单（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在单实体 GET 之上。  
> **未宣称** N07/N22 certified / 完整矩阵式策略编辑器。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 薄表单字段 | pass | `test_abox_panel_h1_thin_form_fields` |
| 仍走 h1_policy PUT | pass | `test_apply_still_uses_h1_policy_body` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_h1_form_phase2.py -v
# 实测 2026-11-20：2 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `AboxAclPanel` effect/principals/actions/condition/masked 薄字段 ↔ JSON |
| 应用 | `buildH1FromForm` → 既有 `PUT … h1_policy` |
| 加载 | `applyPolicyToForm` ← GET 单实体 H.1 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- condition `$exists` → 见 `phase2-abox-acl-condition-exists-evidence.md`
- 任意 RBAC 产品级策略编辑器（固定轴 per-role 矩阵已见 `phase2-abox-acl-h1-matrix-per-role-evidence.md`）
- `$gt` / `$regex` / 嵌套布尔表达式
