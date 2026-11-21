---
doc_type: Report
title: Phase 2 — 企业域 OCS 扫描证据（N23 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N23 企业域 OCS 扫描证据

> 实施权威：附录 N N23 / 白皮书 §13.4 partial 加深。  
> **未宣称** 企业全域完整 / OCS certified；仅 DomainRouter 扫域 + 词汇预注册 + 门槛地板套件。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 域列表来自 DomainRouter / 显式 ids | pass | suite `domains_from_router` |
| 词汇预注册（≥1 class） | pass | suite `vocab_prereg_required` |
| 门槛地板 ≥80 | pass | suite `threshold_floor_80` |
| certified / enterprise_complete 恒 false | pass | suite `honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ocs_enterprise_scan_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `run_ocs_enterprise_scan_suite` / `evaluate_ocs_enterprise_scan_gate` |
| Facade | 同名 re-export |

## 明确未做

- 企业全域所有入口完整度认证
- 准确率/忠实度替代
- N23 certified / 关闭 ADR 例外
