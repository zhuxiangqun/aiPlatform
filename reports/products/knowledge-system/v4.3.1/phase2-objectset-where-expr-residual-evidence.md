---
doc_type: Report
title: Phase 2 — ObjectSet $where/$expr 显式 residual（N07/N22）
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N07/N22 ObjectSet `$where` / `$expr` residual

> 叠在嵌套 filter deepen 与 `n07_n22_h1_condition_freeze` 之上。  
> **未宣称** N07/N22 certified / 完整表达式语言 / JS `$where` / 关闭 ADR 例外。  
> **`n07_n22_h1_condition_freeze` 保持 true**（不恢复默认 condition-op deepen mop）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `$where` → `where_unavailable`（禁 JS eval） | pass | suite `where_unavailable` |
| `$expr` 有界 `$eq/$ne/$gt/$gte/$lt/$lte` | pass | suite `expr_bounded` |
| `where_js_eval` 恒 false | pass | suite 回执 |
| certified 恒 false | pass | suite/gate honesty |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_filter_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n07_n22_h1_condition_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `match_filter_expr` / `_eval_bounded_expr` |
| suite/gate | `run_object_set_filter_suite` / `evaluate_object_set_filter_gate` |
| Facade | 同名（无平行 API） |

## 明确未做

- `$where` JS / 任意脚本求值
- `$expr` 聚合 / 多算子 / 路径点号展开
- Wiki/KB 全入口 ACL / 任意 RBAC 产品
- 置 `certified` / 关闭 ADR 例外 / 恢复默认 H.1 deepen mop
