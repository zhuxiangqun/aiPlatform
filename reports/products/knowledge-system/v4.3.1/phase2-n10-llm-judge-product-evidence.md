---
doc_type: Report
title: Phase 2 — N10 Gold LLM judge 产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N10 LLM judge product surface (slice-1)

> 显式产品面开刀：默认可用有界 LLM object 等价（无 residual env）。  
> **`llm_judge_product_surface=true`**；仍仅单对 object 判定。  
> **未宣称** N10 certified / `accuracy_claim` / 全量 gold 覆盖。  
> **`n10_gold_eval_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可注入成功 | pass | suite `llm_judge_product_eval` |
| residual 无 env 仍 unavailable | pass | suite `llm_judge_product_unavailable` |
| accuracy / certified 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `LlmJudgePanel` → `/knowledge-gold/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_llm_judge_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n10_gold_eval_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `llm_judge_object_equiv_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/knowledge-gold/product*` |
| UI | `LlmJudgePanel` |

## 明确未做

- 准确率宣称 / N10 certified
- 无模型时静默 Exact-match 冒充
- 关闭 residual opt-in 路径（仍保留）
