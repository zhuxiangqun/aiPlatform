---
doc_type: Report
title: Phase 2/4 — Knowledge Migration 最小切片证据（W10 / §15）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W10 / Knowledge Migration（§15 双写/对账/回滚）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W10 / §8。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md` §15。  
> **未宣称** 生产回填/切写 / OCS 全量 / N24 全量符合；仅证明本地双写对账 + 回滚演练。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 双写两端一致 → reconcile ok | pass | `test_dual_write_reconcile_ok` |
| target 失败 → missing；repair 收敛 | pass | `test_partial_dual_write_repair` |
| stale + orphan 可检测并修复 | pass | `test_stale_and_orphan_repair` |
| 漂移时禁止影子读；修复后可 shadow；回滚回 source | pass | `test_shadow_read_blocked_until_reconcile_then_rollback` |
| 跨租户隐藏 | pass | `test_cross_tenant_hidden` |
| 切写未授权 | pass | 响应恒含 `process_cutover_authorized=false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_knowledge_migration_phase2.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `knowledge_migration.start_migration_job` / `dual_write_record` / `reconcile_migration` / `record_rollback_drill` |
| Facade | `start_knowledge_migration` 等 |
| HTTP | `POST/GET …/fde/knowledge-migrations*` |

## 明确未做（后续）

- 真实 Wiki/Graph/KB 生产回填
- 写切写（cutover）授权与灰度百分比
- OCS 完整度运行时聚合
- 附录 N 24 项全量符合证据包
