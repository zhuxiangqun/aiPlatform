---
doc_type: Report
title: Phase 2 — ABox 实例 ACL 管理端薄 UI（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / ABox ACL 薄 UI（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在字段 ACL 薄 UI 之上。  
> **未宣称** N07/N22 certified / 全量权限管理产品 / RBAC 工作流。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| GET ACL + certified=false | pass | `test_get_graph_acl_returns_certified_false` |
| PUT entity/field 已接线 | pass | `test_put_graph_entity_and_field_acl_exist` |
| 面板接线 + 诚实锁文案 | pass | `test_abox_acl_panel_wires_api_and_honesty` |
| 知识工厂挂载 | pass | `test_knowledge_factory_mounts_abox_acl_panel` |
| tsc | pass | `npx tsc --noEmit`（frontend） |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_abox_acl_thin_ui_phase2.py -v
# 实测 2026-11-20：4 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-20：exit 0
```

## 接线

| 入口 | 路径 |
|------|------|
| UI | `AboxAclPanel.tsx` → `KnowledgeFactoryPage` |
| HTTP | `GET/PUT …/fde/graph/acl/{domain}` / entities / fields |
| Store | `~/.aiplat/ontologies/{domain}/abox_acl.json` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 完整权限产品（审批流 / 多租户策略中心 / 批量导入）
- 删除实例 ACL → 见 `phase2-abox-acl-delete-evidence.md`
- condition 选择器完整 H.1 策略编辑器
