---
doc_type: Report
title: Phase 2 — process_from_datasource → Raw ingest（N01 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / DataSource process → Raw（N01 deepen）

> 实施权威：附录 N N01；叠在 DataSourceConfig content_hash→Raw（G1）之上。  
> **未宣称** 全连接器矩阵 / N01 certified（默认强制 → 见 `phase2-datasource-process-raw-default-force-evidence.md`）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 快照稳定（file 原文 / sql·api JSON） | pass | `test_snapshot_file_and_sql_stable` |
| 历史 opt-in 路径（显式 True） | pass | `test_require_raw_ingest_opt_in` / `test_process_raw_ingest_opt_in_ok` |
| opt-in + hash 正确 → ingest | pass | `test_process_raw_ingest_opt_in_ok` |
| opt-in + 缺 hash → 硬停不 process | pass | `test_process_raw_ingest_missing_hash_hard_stop` |
| HTTP 透传 + certified=false | pass | `test_panel_or_route_documents_require_raw_ingest` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_process_raw_phase2.py -v
# 实测 2026-11-20：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 开关 | 见 default-force 证据；本文件保留 opt-in 时期接线说明 |
| 快照 | `snapshot_datasource_bytes` |
| 引擎 | `OntologyEngine.process_from_datasource` → `ingest_datasource_raw` |
| HTTP | `POST …/engine/process-from-datasource` body `require_raw_ingest` |

## 明确未做

- 默认强制 Raw ingest → 见 `phase2-datasource-process-raw-default-force-evidence.md`
- SQL/API 全连接器矩阵 / N01 certified
- 关闭 ADR N01 例外
