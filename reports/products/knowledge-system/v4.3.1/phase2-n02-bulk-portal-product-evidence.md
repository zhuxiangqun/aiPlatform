---
doc_type: Report
title: Phase 2 — N02 多租户批量发布产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-25
pilot_domain: lock-service
---

# Phase 2 / N02 multi-tenant bulk portal product surface (slice-1)

> 显式产品面开刀：默认可用有界多租户 `bulk_transition_object_types_product`。  
> **`bulk_product_surface=true`**；无 residual env 门。  
> **未宣称** N02 certified / seed_replacement / 无限批量编排。  
> **`n02_object_type_freeze` 保持 true**。  
> residual opt-in 路径仍保留（`AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK=1`）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可产品面可达 | pass | suite `bulk_product_default_on` |
| 无 residual env 即可双租户批量 | pass | suite `bulk_product_multi_tenant` |
| residual 默认仍 unavailable | pass | suite / unit |
| certified / seed_replacement 恒 false | pass | suite / gate honesty |
| 管理端 bulk 区挂载产品面 | pass | `ObjectTypePublishPanel` → `/object-types/product/bulk-transition*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_bulk_portal_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n02_object_type_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `bulk_transition_object_types_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/object-types/product/bulk-transition*` |
| UI | `ObjectTypePublishPanel` 批量产品面 |

## 明确未做

- N02 certified / seed_replacement
- 无限批量 / 工作流编排产品
- 关闭 residual opt-in 路径（仍保留）
