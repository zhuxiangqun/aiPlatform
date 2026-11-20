---
doc_type: Report
title: Phase 2 — Claim 状态写路径证据（N03 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / Claim 状态写路径（N03 deepen）证据

> 实施权威：附录 N N03 partial 加深。  
> **未宣称** Claim 全量生命周期产品 / reviewer RBAC / N03 certified；仅写路径
> （读当前态 → 合法边 → 审计 → `put_claim`）+ 门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| accepted→contested 写回持久化 | pass | `test_accepted_to_contested_persisted` |
| 非法边（archived→accepted）拒绝 | pass | `test_illegal_edge_rejected` |
| 纯边诊断路径仍可用 | pass | `test_pure_edge_still_available` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |
| Facade suite/gate | pass | `test_facade_suite_and_gate` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_claim_status_write_phase2.py -v
# 预期：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `transition_claim_status` / `run_claim_status_write_suite` / `evaluate_claim_status_write_gate` |
| 纯边（诊断） | `transition_claim_status_pure` |
| Facade | 同名 suite/gate + `transition_claim_status` 写路径 |
| HTTP | `POST /fde/claims/{id}/status-transition`（读当前态，不再要求 body.from_status） |

## 明确未做

- Claim 全量状态机产品 / 多层业务工作流
- reviewer RBAC 角色源替换
- N03 / 附录 N 全量认证 / 关闭 ADR 例外
