---
doc_type: Report
title: Phase 2 — 知识系统 SLO 目标登记（Batch F1 §9.4 slo 槽位）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md §14
---

# Phase 2 / SLO 目标登记（Batch F1）

> 实施权威：附录 N 认证证据包 `certification_slots.slo` 最小填空。  
> **目标登记 ≠ 生产遥测达标**；**未宣称** 生产 SLO 已测量 / Core 认证 / 24/24。

## 默认目标（摘自白皮书 §14）

| 指标 | 默认目标 |
|------|----------|
| ingest 成功率 | ≥ 99.9% |
| ingest p95 延迟 | ≤ 5 分钟 |
| object sync p95 延迟 | ≤ 5 分钟 |
| query p95 | ≤ 2 秒 |
| action 成功率 | ≥ 99.5% |
| citation 命中率 | ≥ 99% |
| 索引重建耗时 | ≤ 4 小时 |
| 跨租户隔离测试通过率 | 100% |

试点域：`lock-service`。放宽任一目标须另立例外 ADR（见 `phase2-exception-adr.md`）并记录风险接受。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `slo` 槽位 path 非空且文件存在 | pass | `n24-conformance-catalog.yaml` |
| 结构门无 `slo_and_exception_adr_explicitly_missing` | pass | `test_repo_catalog_slots_filled_no_explicit_missing_warning` |
| certified 恒 false | pass | `evaluate_conformance_gate` |

## 明确未做

- 生产告警 / Grafana / PagerDuty 仪表盘
- 用本文件冒充生产达标或附录 N 认证

## 加深

- 遥测接线（采集/快照/接线门）→ 见 `phase2-slo-telemetry-wiring-evidence.md`（仍非达标）
