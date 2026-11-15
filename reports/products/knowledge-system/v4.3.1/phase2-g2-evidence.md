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
> **未宣称**附录 N 全量符合；仅证明 G2 最小切片（含 confirm 收口）。

## G2 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 动作有 L1 硬门 | pass | `AsyncActionRegistry._evaluate_l1_policy_gate`：合同 `required_permissions` 非空且调用方缺权限 → `policy_denied`；`lock_service_accept_order.yaml` 已声明权限；测试 `test_action_l1_policy_denied_without_permissions` |
| 对象/索引可重建 | pass | `project_facts_to_graph`：`rebuild_mode=exact_replay_from_facts`；`clear_projected` 后可重放；测试 `test_project_facts_rebuildable`；HTTP `POST …/extractions/facts/rebuild` |
| 查询/动作不越权 | pass | 查询仍走 FactLedger `tenant_id` SQL 前置（G1）；动作缺权限硬拦；跨租户 Fact 查询见 Phase1 测试 |
| confirm 经 ActionRegistry | pass | `platform_action:knowledge:confirm_extraction`（`required_permissions=["kb:write"]`）→ `run_confirm_extraction`；HTTP `POST …/extractions/{id}/confirm` 传 scopes→permissions；缺 `kb:write` → `policy_denied`；测试 `test_confirm_via_action_registry.py` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_projector_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_ledger_phase1.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_confirm_via_action_registry.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_factory_confirm_proposal.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| L1 PolicyGate | `action_registry.py` Step 3.25 + audit `policy_gate`；`admin`/`*` 通配放行 |
| 投影器 | `fact_projector.py` → CoreFacade `fact_ledger_project_to_graph` |
| confirm 编排 | `CoreFacade.run_confirm_extraction` ← `builtin_handlers.confirm_extraction`（禁 harness→apps 直导） |
| HTTP confirm | `extraction_routes.confirm_extraction` → `get_action_registry().execute(...)` |
| 生产 caller | Action execute 路由 scopes→permissions；`POST /extractions/facts/rebuild` |
| 试点合同 | `workspace_seeds/actions/lock_service_accept_order.yaml` + builtin confirm 合同 |

## 明确未做（后续）

- Wiki 只读化 / ObjectSet SDK / FunctionContract
- 字段级 ACL 全矩阵
- confirm 全量走审批队列（本切片 `_bypass_approval=True`，仅硬门权限）
