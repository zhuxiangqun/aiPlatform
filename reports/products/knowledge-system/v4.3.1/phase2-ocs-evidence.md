---
doc_type: Report
title: Phase 2/4 — OCS Completeness 最小切片证据（W10 / §13.4）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W10 / OCS Completeness（§13.4）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W10。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md` §13.4；契约 `docs/contracts/knowledge/ONTOLOGY_COMPLETENESS.md`。  
> **未宣称** 企业全域完整 / N24 全量 / 生产迁移切写；仅证明六维加权 + C5 覆盖计分 + 门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 权重和=100 | pass | `test_weights_sum_100` |
| C5 非节点数档位；覆盖驱动 | pass | `test_c5_coverage_not_node_count_tiers` |
| 低于门槛 → gate failed | pass | `test_evaluate_ocs_gate_threshold` |
| 诚实锁字段 | pass | `test_honesty_flags_on_report` |
| lock-service OCS≥80（兼容 ratchet） | pass | `compute_domain_ocs(..., credit_test_evidence=True)` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ocs_v431_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_completeness_ocs.py -q
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `compute_domain_ocs` / `evaluate_ocs_gate` |
| Facade | 同名 re-export |
| HTTP | `GET …/fde/ocs/{domain_id}` · `GET …/fde/ocs/{domain_id}/gate` |

## 明确未做（后续）

- 边类型级精确覆盖（按 object_property 逐条命中）
- 附录 N 24 项全量符合证据包
- 生产切写 / 认证证据包汇总
