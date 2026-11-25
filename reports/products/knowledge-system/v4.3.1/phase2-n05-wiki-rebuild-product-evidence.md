---
doc_type: Report
title: Phase 2 — N05 Wiki 重建产品面第一刀（条件重建 + 有界 FTS）
status: active
authority: supporting
measured_at: 2026-11-25
pilot_domain: lock-service
---

# Phase 2 / N05 Wiki rebuild product surface (slice-1)

> 实施权威：附录 N N05 产品面第一刀。  
> **默认可用**：Fact→`wiki_rebuild_pages` + 写页后有界 `fts_upsert_page`；可选 `rebuild_wiki_fts_product`。  
> **诚实锁**：`wiki_rebuild_product_surface=true` / `wiki_fts_product_sync=true`；`wiki_engine_fts_full` / `certified` 恒 false。  
> **`n05_wiki_rebuild_freeze` 保持 true**。  
> **未宣称** wiki_engine/FTS 全量热路径 / N05 certified / 关闭 ADR 例外。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 产品 exact 写页 | pass | suite `product_exact_writes_pages` |
| 产品 non 不写 | pass | suite `product_non_skips_write` |
| 租户必填 | pass | suite `product_tenant_required` |
| FTS sync 旗 + upsert | pass | suite `product_fts_sync_flags` |
| FTS rebuild 诚实 | pass | suite `product_fts_rebuild_honesty` |
| certified / fts_full 恒 false | pass | suite / gate honesty |
| freeze 仍 true | pass | catalog + 回执 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_rebuild_product_phase2.py -v
# 预期：4 passed
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n05_wiki_rebuild_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `project_facts_to_wiki_product` / `list_wiki_rebuild_pages_product` / `rebuild_wiki_fts_product` / suite/gate |
| Facade / HTTP | Facade 同名 + `/fde/wiki-rebuild/product*` |
| UI | `WikiRebuildPanel` → KnowledgeFactory |
| deepen 保留 | `/wiki-rebuild`（非 product） |

## 明确未做

- 替换 `wiki_engine` / FTS 全量重建热路径（`wiki_engine_fts_full`）
- 开放读模型人工写
- N05 certified / 关闭 ADR 例外 / 翻 `n05_wiki_rebuild_freeze`
