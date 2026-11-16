---
doc_type: Report
title: Phase 2/3 — Fact 状态机最小切片证据（W3 / N12）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W3 / N12 Fact 状态机（最小切片）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W3。  
> 标准：白皮书 §7.5；`schemas/validate_semantics_v4.3.1.py` TRANSITIONS。  
> **未宣称** N12 全量 / 附录 N 认证 / 裸 `put_fact` 唯一强制门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| review / lifecycle / claim 边表对齐标准包 | pass | `MACHINES` + `test_review_and_lifecycle_edges` |
| draft→published 禁止（须经 reviewed） | pass | `skip_review_forbidden` |
| 转换含 actor/time/reason + revision | pass | `_record_audit` + `test_transition_requires_actor_reason_and_audit` |
| retracted 不物理删除 | pass | lifecycle→retracted 后 `get_fact` 仍在 |
| 门槛门 pass ≠ certified | pass | `evaluate_fact_state_gate` 恒 `certified=false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fact_state_machine_phase2.py -q
```

实测（2026-11-16）：与 N04 合跑 `8 passed`；本文件用例 `3 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `fact_state_machine.transition_fact_review` / `transition_fact_lifecycle` / `transition_claim_status_pure` / `evaluate_fact_state_gate` |
| Facade | 同名 + `dump_fact_state_machines` / `list_fact_state_transitions` |
| HTTP | `GET …/fde/fact-state/machines` · `GET …/fde/fact-state/transitions` · `POST …/fde/fact-state/validate-sequence` · `POST …/fde/facts/{id}/review-transition` · `POST …/fde/facts/{id}/lifecycle-transition` · `POST …/fde/claims/{id}/status-transition` · `POST …/fde/fact-state/gate` |

## 明确未做（后续）

- 将 FactLedger 裸 `put_fact` INSERT OR REPLACE 改为唯一强制走状态机
- Claim 表写回与 Fact 对称的全量 transition API
- reviewer RBAC 角色源强制（现仅要求 actor 非空）
- 宣称 N12 全量 / Core 符合
