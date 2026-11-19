---
doc_type: Report
title: Phase 2 — 字段 ACL 管理端薄 UI（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / 字段 ACL 薄 UI（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 platform auto 身份透传之上。  
> **未宣称** N07/N22 certified / 全量权限管理产品 / RBAC 工作流。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| list API + certified=false | pass | `test_list_field_permissions_endpoint_exists` |
| list 路由在 entity path 之前 | pass | `test_list_route_registered_before_entity_path` |
| 面板接线 + 诚实锁文案 | pass | `test_field_acl_panel_wires_api_and_honesty` |
| 知识工厂挂载 | pass | `test_knowledge_factory_mounts_field_acl_panel` |
| tsc | pass | `npx tsc --noEmit`（frontend） |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_field_acl_thin_ui_phase2.py -v
# 实测 2026-11-19：4 passed

cd aiPlat-management/frontend && npx tsc --noEmit
# 实测 2026-11-19：exit 0
```


## 接线

| 入口 | 路径 |
|------|------|
| UI | `FieldAclPanel.tsx` → `KnowledgeFactoryPage` 「更多」区 |
| HTTP | `GET/PUT/DELETE …/wiki/ontology/field-permissions*` |
| Store | `~/.aiplat/wiki/collections/{collection}/field_permissions.json` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 完整权限产品（审批流 / 多租户策略中心 / 批量导入）
- 无身份伪造 cron 角色（见 auto identity 证据）
