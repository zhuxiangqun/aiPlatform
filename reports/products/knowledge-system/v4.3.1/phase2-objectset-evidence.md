---
doc_type: Report
title: Phase 2 — ObjectSet 最小切片证据（W6）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / ObjectSet（W6）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W6。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §E.1/E.2。  
> **未宣称**附录 N 全量符合；仅证明「租户前置 + L1 + 查询不写事实」最小切片。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 `kb:read` → 硬拦 | pass | `policy_denied`；`test_policy_denied_without_kb_read` |
| `tenant_id` 必填 | pass | 空租户 → `tenant_id_required`；`test_tenant_id_required` |
| 跨租户不可见 | pass | t1 查不到 t2 的 `O-9`；`test_tenant_isolation` |
| 查询不写 Fact | pass | 查询前后 Fact 行数不变；`test_query_does_not_write` |
| 未注册 object_type | pass | `not_found`；`test_object_type_not_found` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 查询 | `harness/knowledge_pipeline/object_set.py` → `query_object_set` |
| 绑定 | `workspace_seeds/ontologies/*-object-types.json`（配置驱动） |
| CoreFacade | `query_object_set` |
| HTTP | `POST /api/platform/apps/fde/object-sets/query?tenant_id=…`（`X-AIPLAT-SCOPES`→permissions） |

## 明确未做（后续）

- SDK 生成 / Link traverse / Agent tool 全矩阵
- Interface；字段级 ACL
- 完整游标分页与多字段聚合
- 附录 N 全量符合
