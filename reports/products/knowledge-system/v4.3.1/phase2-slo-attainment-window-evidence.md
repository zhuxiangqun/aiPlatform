---
doc_type: Report
title: Phase 2 — 知识系统生产 SLO 达标窗口（显式 residual）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md §14
---

# Phase 2 / SLO 生产达标窗口（显式 residual）

> 实施权威：白皮书 §14；在遥测接线之上评估窗口达标。
> `slo_telemetry_freeze` 仍成立（不恢复默认 wiring deepen）；本刀为 catalog residual「生产达标」显式消费。  
> **attainment_ok = 窗口三指标达标 + 非作者 SLO 批准**；**certified / n24_full_conformance 恒假**。  
> **未宣称** Full unconditional / 告警仪表盘 / ingest·object-sync·索引重建 SLI / 准确率。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无批准路径 → attainment_ok=false | pass | `test_attainment_requires_approval_path` |
| pending 批准阻断 | pass | `test_attainment_pending_approval_blocks` |
| 窗口达标 + approved → attainment_ok | pass | `test_attainment_ok_with_approved_and_window` |
| 未达标即有批准仍 false | pass | `test_misses_target_blocks_even_with_approval` |
| 复用 Full 批准被拒 | pass | `test_wrong_scope_approval_rejected` |
| certified 恒假 | pass | `test_attainment_ok_with_approved_and_window` |
| Facade 唯一入口 | pass | `test_facade_attainment_delegates` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_slo_attainment_window_phase2.py -v
# 预期：6 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`6 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| Core | `slo_telemetry.evaluate_slo_attainment_window` |
| Facade | `evaluate_knowledge_slo_attainment_window` |
| HTTP | `POST …/fde/slo/evaluate-attainment` |
| 批准 | `pilot-slo-attainment-approval-record.{pending,approved}.json` |

## 明确未做

- 清除 Full `conditional` / 置 `certified=true`
- 告警 / Grafana / PagerDuty
- ingest / object-sync / 索引重建 SLI
- 用窗口达标冒充准确率或 N24 全量
