---
doc_type: Report
title: Phase 2 — 知识域 Gold 评测流水线证据（N10 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N10 知识域 Gold 评测证据

> 实施权威：附录 N N10 partial 加深。  
> **未宣称** 准确率达标 / 全知识域 gold 覆盖完成 / N10 certified。  
> Exact-match 对照 FactLedger；跨域扫描经 DomainRouter 或显式域列表。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 登记 gold | pass | suite `register_gold_ok` |
| Exact-match 评测 | pass | suite `eval_exact_match` |
| 缺 gold 域上报 | pass | suite `missing_gold_reported` |
| 多域扫描 | pass | suite `multi_domain_scan` |
| accuracy_claim 恒 false | pass | suite / gate honesty |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_knowledge_gold_eval_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `register_gold_dataset` / `run_knowledge_gold_eval_pipeline` / suite/gate |
| Facade / HTTP | 同名 + `/fde/knowledge-gold*` |
| 配置 | `AIPLAT_KNOWLEDGE_GOLD_EVAL_DB` |

## 明确未做

- LLM judge / 真实 ECE 训练 / 准确率宣称
- 强制全域 gold 覆盖后才允许查询
- N10 certified / 关闭 ADR 例外
