---
doc_type: Report
title: Phase 2 — 记录级语义校验运行时权威证据（N17 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N17 记录级语义校验证据

> 实施权威：附录 N N17 deepen（记录级语义运行时权威）。  
> **未宣称** N17 certified / 替换 `reference_policy.json` / semantic_cases 全量对真实 Fact Store。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| published 拒空 evidence | pass | suite `fact_published_needs_evidence` |
| 生命周期一致性 | pass | suite `fact_lifecycle_coherence` |
| abstain 无 citations | pass | suite `query_abstain_no_citations` |
| draft→published 非法 | pass | suite `transition_fact_review` |
| FactLedger 扫描 | pass | suite `ledger_scan_reports` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_record_semantics_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `validate_record` / `validate_transition` / `scan_ledger_facts` / suite/gate |
| Facade / HTTP | 同名 + `/fde/record-semantics*` |

## 明确未做

- 替换 `reference_policy.json` 为部署侧 RBAC/ACL 真源（N18）
- semantic_cases 全量状态机序列对真实 Fact Store
- N17 certified / 关闭 ADR 例外冒充签字
