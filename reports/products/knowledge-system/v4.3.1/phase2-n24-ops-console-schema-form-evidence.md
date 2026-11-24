---
doc_type: Report
title: Phase 2 — N24 运维台 Schema 表单字段编辑器
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N24 ops console schema form editor

> 产品面：ObjectType schema **字段表单**（name / type / required / description）+ JSON 高级模式。  
> **`schema_form_editor=true`**；复用 `object_type_publish` draft，非第二存贮。  
> **未宣称** N24 certified / 自由布局可视化设计器 / Full unconditional。  
> **`n24_unified_audit_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| form ↔ definition 往返 | pass | suite `ops_console_product_schema_form` |
| GET 回填 `form` | pass | `get_ops_console_schema` |
| save 接受 `form=` | pass | `save_ops_console_schema` / HTTP PUT |
| 管理端字段表 | pass | `OpsConsolePanel` Schema 区 |
| certified 恒 false；freeze 仍 true | pass | suite / catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ops_console_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n24_unified_audit_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `normalize_ops_console_schema_form` / `definition_from_ops_console_schema_form` |
| Facade / HTTP | `save_knowledge_ops_console_schema(form=…)` + `/ops-console/product/schema` |
| UI | `OpsConsolePanel` 字段表单 + JSON 高级切换 |

## 明确未做

- N24 certified / Full unconditional
- 自由布局可视化设计器（拖拽画布 / Retool 级）
- 恢复默认 N24 deepen mop
