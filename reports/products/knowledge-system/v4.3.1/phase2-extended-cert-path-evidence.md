---
doc_type: Report
title: Phase 2 — Extended 可认证路径（等级子集 + extended_ready）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Extended cert path 证据

> 实施权威：附录 N.3 / 实施方案 §14.2。  
> 前置：试点 Core 已 `pilot_certified`（朱鸿林）。  
> Extended：`pilot_extended_certified=true`（非作者 **朱莹** 已复核确认）。  
> **未宣称** 24/24 / Operational；全量 `certified` 仍 false。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Extended 6 项 exists | pass | catalog `extended_minimum_ids` |
| `extended_ready` 门 | pass | `evaluate_extended_ready_gate` |
| FDE HTTP | pass | `/conformance-pack/extended-ready` `/pilot-extended-cert` |
| 无批准时徽章 false | pass | superseded pending |
| 有非作者批准时徽章 | pass | `pilot-extended-approval-record.approved.json`（朱莹） |
| 全量 certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_extended_cert_path_phase2.py -v
```

## 明确未做

- Operational 6 项 / 生产 SLO / 附录 N 24/24
- 自动全量 `certified=true`
