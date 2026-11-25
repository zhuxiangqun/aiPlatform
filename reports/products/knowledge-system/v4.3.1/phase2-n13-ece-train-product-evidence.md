---
doc_type: Report
title: Phase 2 — N13 样本 ECE 训练产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N13 ECE train product surface (slice-1)

> 显式产品面开刀：默认可用有界样本 ECE/Brier（无 residual env）。  
> **`ece_train_product_surface=true`**；仍仅离线标注样本计算。  
> **未宣称** N13 certified / `accuracy_claim` / 在线持续训练。  
> **`n13_calibration_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可样本 ECE | pass | suite `ece_train_product_eval` |
| residual 无 env 仍 unavailable | pass | suite `ece_train_product_unavailable` |
| accuracy / certified 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `EceTrainPanel` → `/confidence-calibrations/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ece_train_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n13_calibration_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `compute_ece_from_samples_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/confidence-calibrations/product*` |
| UI | `EceTrainPanel` |

## 明确未做

- 准确率宣称 / N13 certified
- 空样本静默冒充手工 ece
- 关闭 residual opt-in 路径（仍保留）
- 全量在线持续训练 / 自动替换 active 校准报告
