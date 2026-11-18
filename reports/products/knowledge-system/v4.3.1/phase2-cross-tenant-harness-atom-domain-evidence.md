---
doc_type: Report
title: Phase 2 — harness atom/kb/terms domain 去硬编码证据（N09 Batch K40）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / harness atom·kb·terms domain（Batch K40）证据

> 实施权威：附录 N N09 partial 加深（harness/core GraphIndex.load 域名 → DomainRouter helpers）。  
> **未宣称** N09 certified；`bell-competition` 已由 Batch K41 清除。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 目标文件无裸 atom/kb/terms load | pass | `test_harness_targets_no_hardcoded_graphindex_domain_loads` |
| helpers 接线 | pass | `test_harness_loads_use_domain_router_helpers` |
| SECI metadata 非字面量 | pass | `test_seci_metadata_domain_not_literal` |
| 生产字面量库存 | pass | `test_production_graphindex_literal_inventory_nearly_clear` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_harness_atom_domain_k40.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| SECI / convergence / diagnostician / evolver / context_bus / pipeline | `get_domain_router().knowledge_atom_domain()` |
| wiki / orchestrated_retrieval | `default_kb_domain()` |
| skills/registry | `terms_domain()` |

## 明确未做

- ontology YAML 文件名路径中的 `knowledge-atom.yaml` 字符串（配置文件名，非 GraphIndex domain 参数）
- N09 / 附录 N 全量认证（certified 仍 false）
- `bell-competition` → 见 Batch K41
