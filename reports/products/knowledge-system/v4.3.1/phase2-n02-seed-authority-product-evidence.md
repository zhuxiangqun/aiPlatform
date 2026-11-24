---
doc_type: Report
title: Phase 2 — N02 种子权威产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N02 seed authority product surface (slice-1)

> 显式产品面开刀：默认可用 workspace_seeds 目录列举 + published-over-seed 权威解析/写盘。  
> **`seed_product_surface=true`**；**不改写** `workspace_seeds`。  
> **未宣称** N02 certified / `seed_replacement_complete` / 原地替换种子真源。  
> **`n02_object_type_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可 catalog | pass | suite `seed_authority_product_catalog` |
| 无 residual env 即可 apply + allowlist 写盘 | pass | suite `seed_authority_product_apply` |
| workspace_seeds 只读；mutated 恒 false | pass | suite / gate honesty |
| certified / seed_replacement_complete 恒 false | pass | suite / gate honesty |
| 管理端种子区挂载 | pass | `ObjectTypePublishPanel` → `/object-types/product/seed*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_seed_authority_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n02_object_type_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `list_object_type_seed_catalog` / `apply_published_seed_authority_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/object-types/product/seed-files` + `/object-types/product/seed-authority*` |
| UI | `ObjectTypePublishPanel` 种子权威产品面 |

## 明确未做

- N02 certified / seed_replacement_complete
- 原地改写 / 删除 `workspace_seeds/**-object-types.json`
- 关闭 residual opt-in 路径（仍保留）
