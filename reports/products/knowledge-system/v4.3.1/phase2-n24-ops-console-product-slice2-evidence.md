---
doc_type: Report
title: Phase 2 — N24 运维台产品面第二刀（四面板 + 通用 bundle）
status: active
authority: supporting
measured_at: 2026-11-25
pilot_domain: lock-service
---

# Phase 2 / N24 ops console product surface (slice-2)

> 产品面：默认可用 **四面板**（Audit / SLO / Schema / Export）+ **通用 ops bundle** 导出。  
> bundle = snapshot + schema + 有界 audit 样本（≤20）+ SLO miss；`ops_console_general_export=true`。  
> **`full_ops_console=true`**；**未宣称** `export_complete` / N24 certified / 自由布局可视化设计器 / Full unconditional。  
> **`n24_unified_audit_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 四面板 `panels` + `panel_summaries` | pass | suite `ops_console_product_multi_panel` |
| 通用 bundle 含 snapshot/schema/sample/slo | pass | suite `ops_console_product_general_export` |
| audit 样本硬上限 ≤20 | pass | `audit_sample_limit` 钳制 + suite |
| `ops_console_general_export=true`；`export_complete` 恒 false | pass | suite / gate honesty |
| 管理端四 Tab + 下载 | pass | `OpsConsolePanel` → `/ops-console/product*` |
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
| 核心 | `build_ops_console_product_snapshot`（panel_summaries）/ `export_ops_console_product`（bundle）/ suite·gate |
| Facade / HTTP | `export_knowledge_ops_console_product(include_audit_sample=…)` + `/ops-console/product/export` |
| UI | `OpsConsolePanel` 四 Tab + general export 下载 |

## 明确未做

- N24 certified / Full unconditional / `export_complete`
- 自由布局可视化设计器（拖拽画布 / Retool 级）
- 统一审计 bus 全量 dump
- 恢复默认 N24 deepen mop
