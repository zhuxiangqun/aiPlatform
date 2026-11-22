---
doc_type: Report
title: Phase 2 — Raw↔Fact↔Index 全链路对账证据（N14 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N14 Raw↔Fact↔Index 对账证据

> 实施权威：附录 N N14 deepen（跨存储失败恢复/对账）。  
> **未宣称** 生产切写认证 / N14 certified / 全量生产回填。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 干净链路 ok | pass | suite `clean_chain_ok` |
| Raw 无 Fact | pass | suite `raw_without_fact_reported` |
| Index orphan | pass | suite `index_orphan_reported` |
| Fact 未入 Index | pass | suite `fact_not_indexed_reported` |
| cutover/certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_raw_fact_index_reconcile_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `reconcile_raw_fact_index` / suite/gate |
| Facade / HTTP | 同名 + `/fde/raw-fact-index-reconcile*` |

## 明确未做

- 生产切写授权 / `process_cutover_authorized=true`
- 自动修复写回生产 Index/Wiki
- N14 certified / 关闭 ADR 例外冒充签字
