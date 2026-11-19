---
doc_type: Report
title: Phase 2 — ABox ACL H.1 masked_properties（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL masked_properties（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 condition `$eq/$ne/$in` 之上。  
> **未宣称** N07/N22 certified / 完整 H.1 策略编辑器（effect/principals 矩阵 UI）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| masked 同步 fields + 清除 | pass | `test_masked_properties_syncs_field_acl` |
| H.1 只读投影 + preview | pass | `test_entity_acl_to_h1_and_preview` |
| 薄 UI 文案 | pass | `test_abox_panel_documents_masked_properties` |
| tsc | pass | `npx tsc --noEmit` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_masked_props_phase2.py -v
# 实测 2026-11-20：3 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `set_entity_acl(masked_properties=)` → fields `visibility=none` |
| 投影 | `entity_acl_to_h1` / `list_masked_properties`；`preview_abox_acl.h1_policy` |
| HTTP | `PUT …/graph/acl/.../entities/{id}` body.masked_properties |
| UI | `AboxAclPanel` masked_properties 逗号输入 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- H.1 薄导入 `apply_h1_policy` → 见 `phase2-abox-acl-h1-apply-evidence.md`
- 完整 H.1 策略编辑器（effect/principals/actions 矩阵 UI）
- `$gt` / `$regex` / 嵌套布尔表达式
