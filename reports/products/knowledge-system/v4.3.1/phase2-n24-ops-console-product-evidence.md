---
doc_type: Report
title: Phase 2 — N24 运维台产品面第一刀
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N24 ops console product surface (slice-1)

> 显式产品面开刀：默认可用概览 + ObjectType schema JSON 编辑 + 浏览器下载导出。  
> **`full_ops_console=true`**（产品四面板齐全）。  
> **未宣称** N24 certified / Full unconditional / 可视化表单设计器。  
> **`n24_unified_audit_freeze` 保持 true**（停止默认 deepen）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 无 residual env 即可 snapshot | pass | suite `ops_console_product_snapshot` |
| schema 读写 draft | pass | suite `ops_console_product_schema` |
| 浏览器导出 payload + 可选写盘 | pass | suite `ops_console_product_export` |
| certified / export_complete 恒 false；full_ops_console true | pass | suite / gate honesty |
| 管理端三区挂载 | pass | `OpsConsolePanel` → `/ops-console/product*` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ops_console_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n24_unified_audit_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `build_ops_console_product_snapshot` / schema get·save / `export_ops_console_product` / suite·gate |
| Facade / HTTP | `build_knowledge_ops_console_product_snapshot` + `/ops-console/product*` |
| UI | `OpsConsolePanel` 概览 / Schema / 导出 |

## 明确未做

- N24 certified / Full unconditional
- 可视化表单式 schema 设计器
- 恢复默认 N24 deepen mop
- 关闭 residual opt-in 路径（仍保留）
