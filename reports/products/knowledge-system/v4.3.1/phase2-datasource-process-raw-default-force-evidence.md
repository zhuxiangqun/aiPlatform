---
doc_type: Report
title: Phase 2 — process_from_datasource Raw 默认强制（N01 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-20
pilot_domain: lock-service
---

# Phase 2 / DataSource process → Raw 默认强制（N01 deepen）

> 实施权威：附录 N N01；叠在 process→Raw opt-in 之上。  
> **未宣称** 全连接器矩阵 / N01 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 env 时默认强制 | pass | `test_require_raw_ingest_default_on` |
| 默认路径执行 Raw ingest | pass | `test_process_default_forces_raw_ingest` |
| 显式 opt-out 跳过 | pass | `test_process_opt_out_skips_raw_ingest` |
| 代码/路由诚实锁 | pass | `test_docs_and_route_state_default_force` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_process_raw_default_force_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_process_raw_phase2.py -v
# 实测 2026-11-20：10 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 默认 | `AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST` 缺省 `1` |
| opt-out | 参数 `require_raw_ingest=false` 或 env=`0`/`false`/`off` |
| 引擎 | `process_from_datasource` → `ingest_datasource_raw`（失败硬停） |

## 明确未做

- SQL/API 全连接器矩阵
- N01 certified / 关闭 ADR 例外
- 取消 opt-out 逃生舱
