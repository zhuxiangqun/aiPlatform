---
doc_type: Report
title: Phase 2 — 知识系统生产 SLO 遥测接线（F1 deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md §14
---

# Phase 2 / SLO 遥测接线（F1 deepen）

> 实施权威：附录 N `certification_slots.slo` 加深；白皮书 §14 目标。  
> **接线 ≠ 生产达标**；**未宣称** 生产窗口达标 / Full unconditional / 告警仪表盘。  
> Full 批准保持 `conditional`（见 `pilot-full-approval-record.approved.json`）。

## 本切片覆盖

| 指标 | 目标 | 接线源 |
|------|------|--------|
| action 成功率 | ≥ 99.5% | `record_slo_sample` + Facade `execute_action` 钩子 + ActionStore live |
| query p95 | ≤ 2000ms | 样本表 + `cost_estimator` live + platform KB `duration_ms` |
| citation 覆盖率 | ≥ 99% | 样本表 + ExecutionStore `knowledge_retrieve` live |

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 租户隔离样本 | pass | `test_record_sample_tenant_scoped` |
| snapshot 含 targets + samples | pass | `test_snapshot_exposes_targets_and_samples` |
| 空样本 wiring_ok=false | pass | `test_wiring_gate_honesty_empty_not_green` |
| wiring 可真且 attainment/certified 恒假 | pass | `test_wiring_gate_pass_attainment_still_false` |
| Facade 唯一入口 | pass | `test_facade_delegates_to_slo_telemetry` |
| KB query duration_ms 可写 | pass | `test_record_kb_query_syscall_calls_store` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_slo_telemetry_phase2.py \
  aiPlat-platform/tests/test_kb_query_telemetry.py -v
# 预期：slo ≥6 passed；kb telemetry 既有用例仍绿
```

实测（2026-11-19，`.venv` Python 3.11）：`11 passed`（6 slo + 5 kb telemetry）。

## 接线

| 入口 | 路径 |
|------|------|
| Core | `slo_telemetry.record_slo_sample` / `get_slo_snapshot` / `evaluate_slo_wiring_gate` |
| Facade | `record_knowledge_slo_sample` / `get_knowledge_slo_snapshot` / `evaluate_knowledge_slo_wiring_gate` |
| HTTP | `GET …/fde/slo/snapshot` · `POST …/fde/slo/evaluate-wiring` · `POST …/fde/slo/sample` |
| 热路径 | `execute_action` → action 样本；`record_kb_query_syscall(duration_ms=)` → query/citation 样本 |

## 明确未做

- ingest / object-sync / 索引重建 SLI
- 生产告警 / Grafana / PagerDuty
- 用接线冒充生产达标或清除 Full `conditional`
- 准确率宣称
