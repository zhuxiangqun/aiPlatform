---
doc_type: Report
title: Phase 2 — N02 多租户批量发布 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N02 multi-tenant bulk portal residual

> 叠在 ObjectType 人审发布与薄门户之上。  
> **未宣称** 种子替换 / N02 certified / 关闭 ADR 例外。  
> **`n02_object_type_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认关闭批量 | pass | suite `bulk_unavailable` |
| 多租户 opt-in 逐项回执 | pass | suite `bulk_opt_in` |
| 门户 bulk-transition 入口 | pass | `ObjectTypePublishPanel` |
| certified / seed_replacement 恒 false | pass | suite / bulk 回执 |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_type_publish_phase2.py -q
cd aiPlat-management/frontend && npx tsc --noEmit
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n02_object_type_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `bulk_transition_object_types` |
| Facade / HTTP | 同名 + `POST …/object-types/bulk-transition` |
| UI | `ObjectTypePublishPanel` 批量区 |
| 开关 | `AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK=1` |

## 明确未做

- 替换 workspace_seeds 为唯一真源
- 无限批量 / 工作流编排产品
- N02 certified / 关闭 ADR 例外

> 后续产品面第一刀见 `phase2-n02-bulk-portal-product-evidence.md`（默认可用；residual 路径仍保留）。
