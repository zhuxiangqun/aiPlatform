---
doc_type: Report
title: Phase 2 — N10 Gold LLM judge 显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N10 Gold LLM judge residual

> 叠在 Exact-match gold 流水线与 `n10_gold_eval_freeze` 之上。  
> **未宣称** N10 certified / 准确率达标 / 关闭 ADR 例外。  
> **`n10_gold_eval_freeze` 保持 true**（不恢复默认 N10 deepen mop）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `judge_mode=llm` opt-in 同义 object | pass | suite `llm_judge_opt_in` |
| 不可用诚实上报 `llm_judge_unavailable` | pass | suite `llm_judge_unavailable` |
| 默认关闭实网 LLM（无 env） | pass | `llm_judge_object_equiv` → unavailable |
| accuracy_claim / certified 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_knowledge_gold_eval_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n10_gold_eval_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `llm_judge_object_equiv` / `evaluate_domain_gold(judge_mode=llm)` |
| Facade / HTTP | 同名 + pipeline `judge_mode` |
| 实网开关 | `AIPLAT_KNOWLEDGE_GOLD_LLM_JUDGE=1` |

## 明确未做

- 准确率宣称 / N10 certified / 关闭 ADR 例外
- 无 env 时静默把 Exact-match 冒充为 LLM judge
- ECE 训练（属 N13 residual）
