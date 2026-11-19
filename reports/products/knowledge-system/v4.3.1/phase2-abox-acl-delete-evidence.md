---
doc_type: Report
title: Phase 2 — ABox ACL DELETE（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL 删除（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 ABox 薄 UI 之上。  
> **未宣称** N07/N22 certified / 全量权限产品 / condition 策略编辑器。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| remove roundtrip | pass | `test_remove_entity_and_field_acl_roundtrip` |
| Facade 符号 | pass | `test_facade_remove_graph_acl_symbols` |
| DELETE 路由 + certified=false | pass | `test_delete_routes_exist_and_honesty` |
| 薄 UI 删除接线 | pass | `test_abox_panel_wires_delete` |
| tsc | pass | `npx tsc --noEmit`（frontend） |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_delete_phase2.py -v
# 实测 2026-11-20：4 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| Policy | `remove_entity_acl` / `remove_field_acl` |
| Facade | `remove_graph_entity_acl` / `remove_graph_field_acl` |
| HTTP | `DELETE …/fde/graph/acl/{domain}/entities|fields/…` |
| UI | `AboxAclPanel` 列表「删除」 |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 按角色预览 → 见 `phase2-abox-acl-preview-evidence.md`
- H.1 condition 选择器 / 完整策略编辑器
- 批量导入 / 审批流权限产品
