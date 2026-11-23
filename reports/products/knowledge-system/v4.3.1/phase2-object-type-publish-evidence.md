---
doc_type: Report
title: Phase 2 — ObjectType 人审发布证据（N02 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N02 ObjectType 人审发布证据

> 实施权威：附录 N N02 partial 加深。  
> **未宣称** 全量 ObjectType 发布门户 / 替换 workspace_seeds 真源 / N02 certified。  
> 流水线：draft → in_review → published|rejected；publish 须配置角色；Package schema 门可选（`AIPLAT_OBJECT_TYPE_PUBLISH_GATE`，默认关）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 草稿提交 | pass | suite `draft_submit_ok` |
| 允许角色可 publish | pass | suite `publish_role_allowed` |
| 错误/空角色拒绝 | pass | suite `wrong_role_denied` / `empty_role_denied` |
| 仅 published 为 active | pass | suite `active_only_when_published` |
| Package schema 门拦截未发布 | pass | suite `package_schema_gate_blocks` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_type_publish_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `submit_object_type_draft` / `transition_object_type` / suite/gate |
| Package 钩子 | `publish_package` → `assert_schema_object_types_published`（门开启时） |
| Facade / HTTP | 同名 + `/fde/object-types*` |
| 配置 | `AIPLAT_OBJECT_TYPE_PUBLISH_RBAC` / `AIPLAT_OBJECT_TYPE_PUBLISH_ROLES` / `AIPLAT_OBJECT_TYPE_PUBLISH_GATE` / `AIPLAT_OBJECT_TYPE_PUBLISH_DB` |

## 明确未做

- 全量管理端发布门户 / 多域批量人审
- 替换 `*-object-types.json` 种子为唯一运行时真源
- N02 certified / 关闭 ADR 例外（发布面冻结见 `phase2-n02-object-type-freeze-evidence.md`）
