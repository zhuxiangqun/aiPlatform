---
doc_type: Report
title: Phase 2 — ObjectSet 嵌套 filter 证据（N07/N22 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N07/N22 ObjectSet 嵌套 filter 证据

> 实施权威：附录 N N07/N22 partial 加深。  
> **未宣称** Wiki/KB 全入口 ACL / 任意角色×动作轴产品 / N07·N22 certified。  
> 扁平等值 filter 仍兼容附录 E 示例。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 扁平等值兼容 | pass | suite `flat_equality` |
| `$and`/`$or`/`$not` 嵌套 | pass | suite `nested_boolean` |
| `$eq`/`$ne`/`$in`/`$exists` | pass | suite `field_ops` |
| 深度上限拒绝 | pass | suite `depth_cap` |
| certified 恒 false | pass | suite `honesty_certified_false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_object_set_filter_phase2.py -v
# 预期：6 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `match_filter_expr` / `run_object_set_filter_suite` / `evaluate_object_set_filter_gate` |
| 查询 | `query_object_set` → `_item_matches_filter` |
| Facade | 同名 suite/gate |

## 明确未做

- Wiki/KB 全入口字段/实例 ACL
- 任意角色×动作轴 RBAC 产品
- 无限深度 / 完整表达式语言产品化
- N07/N22 certified / 关闭 ADR 例外
