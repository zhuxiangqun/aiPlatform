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
> 试点 Core：`pilot_certified=true`（非作者 **朱鸿林** 已复核确认，`pilot-core-approval-record.approved.json`）。  
> 后续：Extended/Operational/全量见各自证据；全量 `certified` 由独立全量批准置真（朱向群，conditional）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 三份文档等级映射 | pass | 白皮书 §16.1 / 附录 N / 实施方案 DoD |
| catalog `level` + `core_minimum_ids` | pass | `n24-conformance-catalog.yaml` |
| Core 12 项 exists（Core-scoped） | pass | catalog status |
| N09 探针冻结 | pass | `n09_core_probe_freeze: true` |
| `core_ready` 门 | pass | `evaluate_core_ready_gate` |
| FDE HTTP 接线 | pass | `GET …/conformance-pack/core-ready` / `pilot-core-cert` |
| 无批准时 pilot_certified 恒 false | pass | 缺路径 / superseded pending + honesty 测 |
| 有非作者批准时 pilot_certified | pass | `pilot-core-approval-record.approved.json`（朱鸿林） |
| 本门不自动置全量 certified | pass | honesty（全量须独立批准） |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_conformance_pack_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 明确未做

- Extended / Operational 全量 / 附录 N 24/24
- 自动 `certified=true`（全量徽章仍禁止无独立全量批准）
