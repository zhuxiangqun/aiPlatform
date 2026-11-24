---
doc_type: Report
title: Phase 2 — N13 样本 ECE 训练显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N13 ECE train residual

> 叠在 Operational 校准封顶与附录 O 门槛之上。  
> **未宣称** 准确率达标 / N13 certified / 关闭 ADR 例外。  
> **`n13_calibration_freeze` 保持 true**（不恢复默认 N13 deepen mop）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `compute_ece_from_samples` opt-in | pass | suite `ece_train_opt_in` |
| 不可用诚实上报 `ece_training_unavailable` | pass | suite `ece_train_unavailable` |
| 默认关闭实网训练（无 env） | pass | `AIPLAT_KNOWLEDGE_ECE_TRAIN` 未设 |
| accuracy_claim / certified 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_calibration_pipeline_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n13_calibration_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `compute_ece_from_samples` |
| Facade / HTTP | 同名 + `POST …/ece-train` |
| 实网开关 | `AIPLAT_KNOWLEDGE_ECE_TRAIN=1` |

## 明确未做

- 准确率宣称 / N13 certified / 关闭 ADR 例外
- 全量在线持续训练 / 自动替换 active 校准报告
