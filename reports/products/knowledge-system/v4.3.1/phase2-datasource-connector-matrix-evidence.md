---
doc_type: Report
title: Phase 2 — DataSource Core 连接器矩阵（N01 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / DataSource Core file/sql/api 连接器矩阵（N01 deepen）

> 实施权威：附录 N N01；叠在 process→Raw 默认强制之上。  
> **未宣称** vendor 驱动矩阵 / N01 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 矩阵声明 file/sql/api | pass | `test_matrix_declares_file_sql_api` |
| sql/api hash 快照 + mismatch 拒 | pass | `test_sql_api_hash_snapshot_and_mismatch` |
| suite 6/6 + honesty | pass | `test_suite_and_gate_honesty` |
| Facade 接线 | pass | `test_facade_matrix_suite_and_helpers` |
| 代码/文档接线 | pass | `test_docs_and_wiring_state` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_connector_matrix_phase2.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| 矩阵声明 | `DATASOURCE_RAW_CONNECTOR_MATRIX` / `datasource_raw_connector_matrix` |
| 强制轴 | `require_datasource_raw_connector` → `snapshot_datasource_bytes` |
| 套件/门 | `run_datasource_connector_matrix_suite` / `evaluate_datasource_connector_matrix_gate` |
| Facade | `get_datasource_raw_connector_matrix` / `ensure_datasource_raw_connector` / suite/gate |

## 明确未做

- PG/MySQL/Oracle 等 vendor 驱动全量矩阵
- N01 certified / 关闭 ADR 例外（Raw 面冻结见 `phase2-n01-raw-integrity-freeze-evidence.md`）
- 取消 process Raw opt-out 逃生舱
