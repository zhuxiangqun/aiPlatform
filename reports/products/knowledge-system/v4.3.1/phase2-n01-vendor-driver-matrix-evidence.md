---
doc_type: Report
title: Phase 2 — N01 SQL vendor 驱动矩阵（显式 residual）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / N01 SQL vendor 驱动软依赖矩阵（residual）

> 实施权威：附录 N N01 residual；叠在 Core file/sql/api 连接器矩阵与 `n01_raw_integrity_freeze` 之上。  
> **未宣称** 生产连真实 PG/MySQL/Oracle 集群验收 / N01 certified / 关闭 ADR 例外。  
> **`n01_raw_integrity_freeze` 保持 true**（不恢复默认 N01 deepen mop）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 声明轴 sqlite/postgresql/mysql/oracle | pass | `test_matrix_declares_vendor_axis` |
| oracle → declared_unavailable（不假绿） | pass | `test_oracle_declared_unavailable_never_available` |
| 缺驱动 available=false / certified=false | pass | `test_missing_driver_not_fake_green` |
| suite 7/7 + honesty | pass | `test_suite_and_gate_honesty` |
| Facade + HTTP 接线 | pass | `test_facade_matrix_suite_and_helpers` / `test_docs_and_wiring_state` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_datasource_vendor_matrix_phase2.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| 矩阵声明 | `DATASOURCE_VENDOR_DRIVER_MATRIX` / `datasource_vendor_driver_matrix` |
| 软依赖探测 | `probe_vendor_driver`（importlib；非生产连库） |
| 套件/门 | `run_datasource_vendor_matrix_suite` / `evaluate_datasource_vendor_matrix_gate` |
| Facade | `get_datasource_vendor_driver_matrix` / `probe_datasource_vendor_driver` / suite/gate |
| HTTP | `/fde/datasource/vendor-matrix*` → CoreFacade |

## 明确未做

- 生产连真实 PG/MySQL/Oracle 集群验收
- 实现 `$where` / 全量门户 / 置 `certified` / `n01_full_conformance`
- 恢复默认 N01 deepen mop（freeze 仍 true）
- 内置 Oracle 驱动
