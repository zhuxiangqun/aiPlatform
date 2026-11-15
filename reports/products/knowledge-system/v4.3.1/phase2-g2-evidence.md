---
doc_type: Report
title: Phase 2 — G2 证据（lock-service 最小切片）
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
---

# Phase 2 / G2 证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §6 Phase 2。  
> **未宣称**附录 N 全量符合；仅证明 G2 三条最小切片。

## G2 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 动作有 L1 硬门 | pass | `AsyncActionRegistry._evaluate_l1_policy_gate`：合同 `required_permissions` 非空且调用方缺权限 → `policy_denied`；`lock_service_accept_order.yaml` 已声明权限；测试 `test_action_l1_policy_denied_without_permissions` |
| 对象/索引可重建 | pass | `project_facts_to_graph`：`rebuild_mode=exact_replay_from_facts`；`clear_projected` 后可重放；测试 `test_project_facts_rebuildable`；HTTP `POST …/extractions/facts/rebuild` |
| 查询/动作不越权 | pass | 查询仍走 FactLedger `tenant_id` SQL 前置（G1）；动作缺权限硬拦（本切片）；跨租户 Fact 查询见 Phase1 测试 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_projector_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_ledger_phase1.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| L1 PolicyGate | `action_registry.py` Step 3.25 + audit `policy_gate` |
| 投影器 | `fact_projector.py` → CoreFacade `fact_ledger_project_to_graph` |
| 生产 caller | `extraction_routes` confirm 后投影；`POST /extractions/facts/rebuild` |
| 试点合同 | `workspace_seeds/actions/lock_service_accept_order.yaml` |

## 明确未做（后续）

- 抽取 confirm 全量改走 ActionRegistry（仍旁路审批；本切片先硬门权限字段）
- Wiki 只读化 / ObjectSet SDK / FunctionContract
- 字段级 ACL 全矩阵
