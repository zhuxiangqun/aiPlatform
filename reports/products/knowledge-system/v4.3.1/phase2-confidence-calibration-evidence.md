---
doc_type: Report
title: Phase 2/4 — Confidence Calibration 最小切片证据（W10 / 附录 O）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W10 / Confidence Calibration（附录 O）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W10。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §O；正文 §9.6.7。  
> **未宣称**准确率 / OCS 全量 / 迁移双写 / N24 全量符合；仅证明校准报告门槛 + 失败降级。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 达标报告可 active，允许 high | pass | `test_publish_pass_allows_high` |
| ECE 超标 → failed，最高 medium | pass | `test_ece_fail_caps_to_medium` |
| 缺失/过期 → 最高 medium | pass | `test_missing_or_expired_caps_to_medium` |
| 跨租户读隐藏 | pass | `test_cross_tenant_hidden` |
| 指标含 dataset/version/门槛 | pass | publish 必填 + `evaluate_calibration_gate` thresholds |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_confidence_calibration_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `confidence_calibration.publish_calibration_report` / `validate_calibration_report` / `resolve_max_confidence` |
| Facade | `publish_confidence_calibration` 等 |
| HTTP | `POST/GET …/fde/confidence-calibrations*` |

## 明确未做（后续）

- 真实 ECE/Brier 训练流水线
- OCS 完整度运行时聚合接线
- 迁移双写/对账
- 附录 N 24 项全量符合证据包
