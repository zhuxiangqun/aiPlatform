---
doc_type: Report
title: Phase 2 — N24 运维台有界导出显式 residual
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
---

# Phase 2 / N24 ops console export residual

> 叠在运维台薄壳 residual 之上。  
> **未宣称** 全量运维台 / 通用下载产品化 / schema 编辑器 / N24 certified / Full unconditional。  
> **`n24_unified_audit_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 默认关闭 | pass | suite `ops_console_export_unavailable` |
| opt-in 有界 JSON 写盘 | pass | suite `ops_console_export_opt_in` |
| certified / full / export_complete / schema_editor 恒 false | pass | suite / gate honesty |
| 管理端导出按钮挂载 | pass | `OpsConsolePanel` → `/ops-console/export` |
| freeze 仍 true | pass | `n24-conformance-catalog.yaml` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ops_console_export_residual_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n24_unified_audit_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `export_ops_console_snapshot` / suite/gate / allowlist root |
| Facade / HTTP | `export_knowledge_ops_console_snapshot` + `/ops-console/export*` |
| UI | `OpsConsolePanel`「导出」 |
| 实网开关 | `AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT=1` |

## 明确未做

- 全量运维台 / schema 编辑器 / 浏览器通用下载产品化
- N24 certified / Full unconditional
- 恢复默认 N24 deepen mop
