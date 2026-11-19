---
doc_type: Report
title: Phase 2 — 全量可认证路径（full_ready + 独立批准）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Full cert path 证据

> 实施权威：附录 N.6 / 实施方案 §14.4。  
> 前置：Core（朱鸿林）+ Extended（朱莹）+ Operational（朱莹）等级徽章已齐。  
> **未宣称** 全量 `certified` / 24/24（签字仍 pending）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 24 项 exists | pass | catalog 全量 |
| 三级 `*_ready` | pass | core/extended/operational gates |
| `full_ready` | pass | `evaluate_full_ready_gate` |
| 三级徽章 | pass | 三份 `*.approved.json` |
| FDE HTTP | pass | `/full-ready` `/full-cert` |
| 无全量批准时 certified false | pass | pending 记录 |
| SLO | conditional | 目标登记（非生产遥测） |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_full_cert_path_phase2.py -v
```

## 明确未做

- 非作者全量签字（`pilot-full-approval-record.pending.json`）
- 生产 SLO 遥测达标
- 准确率宣称
