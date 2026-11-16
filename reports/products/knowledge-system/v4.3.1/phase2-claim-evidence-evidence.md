---
doc_type: Report
title: Phase 2 — Claim 证据硬门与冲突记录证据（N03 Batch F2）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Claim 证据（Batch F2）证据

> 实施权威：附录 N N03 partial 加深。  
> **未宣称** 全量 Claim 状态机 / reviewer RBAC / N03 certified；仅证据硬门 + 同键冲突记录 + 门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| published 无 evidence 拒绝 | pass | `test_published_without_evidence_rejected` |
| published 有 evidence 写入 | pass | `test_published_with_evidence_ok` |
| 同 conflict_key 不同主张 → open 冲突 | pass | `test_claim_conflict_recorded` |
| enforce_write_gates 要求策略已登记 | pass | `test_enforce_write_gates_unknown_policy` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_claim_evidence_phase2.py -v
# 预期：5 passed
```

实测（2026-11-16）：`5 passed`（落地后以本地/CI 为准）。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `put_claim` / `record_claim_conflict` / `run_claim_evidence_suite` / `evaluate_claim_evidence_gate` |
| Facade | `fact_ledger_run_claim_evidence_suite` + `evaluate_fact_claim_evidence_gate` |

## 明确未做

- Claim 全量状态机 / reviewer RBAC
- 冲突自动裁决选边
- N03 / 附录 N 全量认证
