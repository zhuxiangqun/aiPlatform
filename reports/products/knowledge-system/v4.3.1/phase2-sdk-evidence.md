---
doc_type: Report
title: Phase 2 — Knowledge SDK 最小切片证据（W6 / E.3）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Knowledge SDK（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §E.3。  
> **未宣称**附录 N 全量符合；仅证明 ObjectType→Client 表面/源码经 CoreFacade，不绕过 L1。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 `kb:read` 拒绝 | pass | `test_surface_requires_kb_read` |
| InstallOrder 表面含 Facade via | pass | `test_surface_for_install_order` |
| 生成源码仅 import CoreFacade；无 sql/bypass | pass | `test_render_source_facade_only_no_sql` |
| 运行时 query 经 Facade | pass | `test_object_client_delegates_query` |
| 创建 client 权限拒绝 | pass | `test_create_client_policy_denied` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_sdk_generator_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| Generator | `sdk_generator.build_sdk_surface` / `render_sdk_python` / `ObjectClient` |
| Facade | `build_knowledge_sdk_surface` / `generate_knowledge_sdk` / `create_knowledge_object_client` |
| HTTP | `GET …/fde/sdk/surface/{object_type}` · `POST …/fde/sdk/generate/{object_type}` · `GET …/fde/sdk/object-types` |

## 明确未做（后续）

- 多语言包发布 / PyPI 发布（Python 写盘安装见 `phase2-sdk-write-install-evidence.md`）
- 字段级 ACL；附录 N 全量符合
