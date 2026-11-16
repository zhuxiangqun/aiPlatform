---
doc_type: Report
title: Phase 2 — Raw 读时完整性校验证据（N01 Batch E1）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Raw 完整性（Batch E1）证据

> 实施权威：附录 N N01 partial 加深。  
> **未宣称** DataSourceConfig 全路径强制 hash / N01 certified；仅 FactLedger 读时验 hash + 篡改拒绝。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 登记后 verify ok + read_bytes | pass | `test_verify_ok_and_read_bytes` |
| 快照篡改拒绝 | pass | `test_tamper_rejected` |
| 快照缺失拒绝 | pass | `test_missing_snapshot_rejected` |
| 同 source_id 覆写拒绝 | pass | `test_rewrite_same_source_id_rejected` |
| 跨租户 verify 拒绝 | pass | `test_cross_tenant_verify_denied` |
| certified 恒 false | pass | `test_gate_pass_and_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_raw_integrity_phase2.py -v
# 预期：6 passed
```

实测（2026-11-16）：`6 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `verify_raw_integrity` / `read_raw_bytes` / `evaluate_raw_integrity_gate` |
| Facade | `fact_ledger_verify_raw_integrity` + `fact_ledger_read_raw_bytes` + `evaluate_fact_raw_integrity_gate` |

## 明确未做

- DataSourceConfig content_hash→Raw（见 Batch G1 `phase2-datasource-raw-evidence.md`；非全连接器矩阵）
- N01 / 附录 N 全量认证
