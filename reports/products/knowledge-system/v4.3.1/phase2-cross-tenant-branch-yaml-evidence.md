---
doc_type: Report
title: Phase 2 — ontology branch YAML 租户前缀证据（N09 Batch K37）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / branch YAML tenant（Batch K37）证据

> 实施权威：附录 N N09 partial 加深（分支 ontology YAML 路径租户前缀）。  
> **未宣称** 域名硬编码消除 / N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| YAML 路径前缀 | pass | `test_branch_yaml_path_tenant_prefix` |
| 新租户可读共享引导 | pass | `test_resolve_yaml_source_falls_back_to_shared` |
| fork 写入租户路径 | pass | `test_fork_copies_yaml_to_tenant_path` |
| 源码接线 | pass | `test_source_wires_branch_yaml_helpers` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_branch_yaml_tenant_k37.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| `_branch_yaml_path` | 与 GraphIndex / `_branch_db_path` 同前缀约定 |
| fork / merge | 读 `_resolve_branch_yaml_source`；写租户路径 |

## 明确未做

- FDE/平台业务域名硬编码消除 — platform FDE `fde-delivery` load 见 K38；其它域名仍延后
- N09 / 附录 N 全量认证（certified 仍 false）
