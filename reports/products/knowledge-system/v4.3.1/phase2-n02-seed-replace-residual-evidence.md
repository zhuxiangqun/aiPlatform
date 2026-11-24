---
doc_type: Report
title: Phase 2 — N02 种子权威覆盖显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N02 published-over-seed authority residual

> 叠在 ObjectType 人审发布 + 多租户 bulk residual 之上。  
> **未宣称** 全量种子替换产品化 / 改写 `workspace_seeds` / N02 certified。  
> **`n02_object_type_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认关闭 | pass | suite `seed_replacement_unavailable` |
| opt-in published 优先于 seed | pass | suite `seed_replacement_opt_in` |
| 不改写 workspace_seeds | pass | `workspace_seeds_mutated=false`；写盘仅 allowlist |
| certified / seed_replacement_complete 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_seed_replacement_residual_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n02_object_type_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `apply_published_seed_authority` / suite/gate |
| Facade / HTTP | 同名 Facade + `/object-types/seed-authority*` |
| 实网开关 | `AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE=1` |
| 写盘根 | `AIPLAT_HOME/data/knowledge_object_type_authority/` |

## 明确未做

- 原地改写 / 删除 `workspace_seeds/**-object-types.json`
- 全域自动以 published 为唯一真源产品化
- N02 certified / 关闭 ADR 例外
