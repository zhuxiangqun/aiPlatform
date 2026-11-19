---
doc_type: Report
title: Phase 2 — Operational 可认证路径（等级子集 + operational_ready）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Operational cert path 证据

> 实施权威：附录 N.4 / 实施方案 §14.3。  
> 前置：Core（朱鸿林）+ Extended（朱莹）已等级徽章。  
> Operational：`pilot_operational_certified=true`（非作者 **朱莹** 已复核确认）。  
> **未宣称** 全量 `certified` / 24/24。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Operational 6 项 exists | pass | catalog `operational_minimum_ids` |
| `operational_ready` 门 | pass | `evaluate_operational_ready_gate` |
| FDE HTTP | pass | `/operational-ready` `/pilot-operational-cert` |
| 无批准时徽章 false | pass | pending 记录 |
| 有非作者批准时徽章 | pass | `pilot-operational-approval-record.approved.json`（朱莹） |
| 全量 certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_operational_cert_path_phase2.py -v
```

## 明确未做

- 自动全量 `certified=true` / 24/24（须独立全量人工认证）
