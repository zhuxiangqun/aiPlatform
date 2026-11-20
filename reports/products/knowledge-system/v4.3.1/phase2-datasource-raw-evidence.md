---
doc_type: Report
title: Phase 2 — DataSourceConfig → Raw 完整性证据（N01 Batch G1）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / DataSource Raw（Batch G1）证据

> 实施权威：附录 N N01 partial 加深（E1 明确未做的 DataSourceConfig 路径）。  
> **未宣称** 全连接器矩阵 / SQL·API 抓取快照全强制 / N01 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 content_hash 强制拒绝 | pass | `test_validate_require_hash_and_mismatch` / suite |
| hash mismatch 拒绝 | pass | 同上 |
| hash 正确 → ingest + verify | pass | `test_ingest_ok_and_verify` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_raw_phase2.py -v
# 预期：4 passed
```

实测（2026-11-17）：`4 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 配置 | `DataSourceConfig.content_hash` + `validate_datasource_content_hash` |
| 核心 | `ingest_datasource_raw` / `run_datasource_raw_suite` / `evaluate_datasource_raw_gate` |
| Facade | `fact_ledger_ingest_datasource_raw` + suite/gate 包装 |

## 明确未做

- SQL/API 连接器全路径自动抓取+hash 强制（本切片以 file 字节/显式 content 为主）
- `process_from_datasource` 默认强制 ingest → 见 `phase2-datasource-process-raw-evidence.md`（仍为 opt-in，非默认强制）
- N01 / 附录 N 全量认证
