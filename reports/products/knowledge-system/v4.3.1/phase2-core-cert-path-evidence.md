---
doc_type: Report
title: Phase 2 — Core 可认证路径闭合（等级映射 + core_ready + 人工徽章）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Core cert path 证据

> 实施权威：白皮书 §16.1 / 附录 N.1–N.2 / 实施方案 §1.1·§14.1。  
> **未宣称** 试点已 certified（`pilot-core-approval-record.pending.json` 仍为 pending）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 三份文档等级映射 | pass | 白皮书 §16.1 / 附录 N / 实施方案 DoD |
| catalog `level` + `core_minimum_ids` | pass | `n24-conformance-catalog.yaml` |
| Core 12 项 exists（Core-scoped） | pass | catalog status |
| N09 探针冻结 | pass | `n09_core_probe_freeze: true` |
| `core_ready` 门 | pass | `evaluate_core_ready_gate` |
| FDE HTTP 接线 | pass | `GET …/conformance-pack/core-ready` / `pilot-core-cert` |
| 无批准时 pilot_certified 恒 false | pass | pending 记录 + honesty 测 |
| certified 不自动置真 | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_conformance_pack_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 明确未做

- 非作者已签字的试点 Core 批准（仍 pending）
- Extended / Operational 全量
- 自动 `certified=true`（永久禁止无批准）
