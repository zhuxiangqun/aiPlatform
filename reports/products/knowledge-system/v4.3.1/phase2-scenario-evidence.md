---
doc_type: Report
title: Phase 2 — Knowledge Scenario 最小切片证据（W9 / H.2）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Knowledge Scenario（W9）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W9。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §H.2。  
> **未宣称**附录 N 全量符合；仅证明 dry_run 模拟不写主事实 + 合并人审。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| simulate 不增加 FactLedger 行数 | pass | `test_simulate_does_not_write_main_facts` |
| 变更落在 Scenario 账本且 dry_run | pass | 同上 |
| 无人审不可 merged | pass | `test_merge_requires_human_review` |
| 无 approver 拒绝 | pass | 同上 |
| 跨租户读隐藏 | pass | `test_cross_tenant_lookup_hidden` |
| 过期阻断 simulate | pass | `test_expired_blocks_simulate` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_scenario_branch_phase2.py -v
# 预期：4 passed
```

实测（2026-11-16）：`4 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `scenario_branch.create_scenario` / `simulate_change` / `request_merge` / `approve_merge` |
| Facade | `create_knowledge_scenario` 等 |
| HTTP | `POST/GET …/fde/scenarios*` |

## 明确未做（后续）

- 合并后自动回写主 Fact / ActionExecution
- Package → 见 `phase2-ontology-package-evidence.md`（本批另切片）
- 附录 N 全量符合
