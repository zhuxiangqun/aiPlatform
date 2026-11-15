---
doc_type: Report
title: Phase 1 — G1 证据（lock-service Fact Ledger）
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
---

# Phase 1 / G1 证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §6 Phase 1。  
> **未宣称**附录 N 24/24 或 Core 全量符合；仅证明 G1 四条。

## G1 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Raw 不可变 | pass | `FactLedger.register_source` 写 sha256 + 快照文件（`fact_ledger.py`）；测试 `test_raw_immutable_source_has_sha256` |
| Fact 有 evidence | pass | `put_fact`/`put_claim` 在 `review_status=published` 时拒绝空 evidence；测试 `test_published_fact_requires_evidence` |
| 查询前置权限（租户） | pass | `query_facts` 强制 `tenant_id` 且 SQL `WHERE tenant_id=?`；测试 `test_fact_with_evidence_and_query_tenant_filter` / `test_query_requires_tenant_id` |
| 跨租户测试通过 | pass | 同测：`tenant-b` 查不到 `tenant-a` 的 source/fact |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_ledger_phase1.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| 实现 | `aiPlat-core/core/harness/knowledge_pipeline/fact_ledger.py` |
| Facade | `core.api.core_facade`：`FactLedger` / `get_fact_ledger` / `record_extraction_as_claim` / `fact_ledger_query_gateway` / `load_object_type_bindings` |
| 生产 caller | `extraction_routes.py` confirm：存在 `{domain}-object-types.json` 时写 Claim+Fact；`GET /extractions/facts` 调查询网关 |
| ObjectType 绑定 | 种子 `workspace_seeds/ontologies/lock-service-object-types.json` + `load_object_type_bindings(path)` |

## 明确未做（后续 Phase）

- Wiki 只读化 / 有条件重建分类
- ObjectSet SDK、Scenario Package
- 字段级 ACL、完整 Gateway 路由
- 附录 N 认证证据包
