---
doc_type: Report
title: Phase 2 — N07/N22 ObjectSet $where/$expr 产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N07 ObjectSet where/expr product surface (slice-1)

> 显式产品面开刀：默认可用有界 `$expr` 结构化回执（无 residual 异常冒充成功）。  
> **`objectset_where_expr_product_surface=true`**；`$where` 仍诚实 unavailable（禁 JS）。  
> **未宣称** N07/N22 certified / 完整表达式语言 / JS `$where`。  
> **`n07_n22_h1_condition_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$expr` 产品面可匹配 | pass | suite `where_expr_product_eval` |
| `$where` 产品面 unavailable | pass | suite `where_expr_product_where_unavailable` |
| residual `$where` 仍抛 where_unavailable | pass | suite 同案 |
| certified / where_js_eval 恒 false | pass | suite / gate honesty |
| 管理端薄面板挂载 | pass | `ObjectSetWhereExprPanel` → `/object-sets/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_objectset_where_expr_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n07_n22_h1_condition_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_object_set_where_expr_product` / suite·gate |
| Facade / HTTP | 同名 Facade + `/object-sets/product*` |
| UI | `ObjectSetWhereExprPanel` |

## 明确未做

- `$where` JS / 任意脚本求值
- `$expr` 聚合 / 多算子 / 完整表达式语言
- N07/N22 certified
- 关闭 residual / 恢复默认 H.1 deepen mop
