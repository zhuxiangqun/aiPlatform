---
doc_type: Report
title: Phase 2 — N02 种子权威产品面第二刀（migrate / rollback）
status: active
authority: supporting
measured_at: 2026-11-25
pilot_domain: lock-service
---

# Phase 2 / N02 seed authority product surface (slice-2)

> 产品面：allowlist 权威镜像 **backup → write → restore**。  
> 写盘根：`AIPLAT_HOME/data/knowledge_object_type_authority/`（`current/` + `backups/{id}/`）。  
> **`seed_migrate_rollback=true`**；**不改写** `workspace_seeds`。  
> **未宣称** `seed_replacement_complete` / N02 certified / 原地替换种子真源。  
> **`n02_object_type_freeze` 保持 true**。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| backup 现有镜像 | pass | suite `seed_migrate_backup` |
| write 前自动 backup + 写 `current/` | pass | suite `seed_migrate_write` / `seed_authority_product_apply` |
| restore 回滚到 backup | pass | suite `seed_migrate_restore` |
| `seed_migrate_rollback=true`；complete/mutated 恒 false | pass | suite / gate honesty |
| 管理端 Backup / Restore | pass | `ObjectTypePublishPanel` |
| freeze 仍 true | pass | catalog |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_seed_authority_product_phase2.py -q
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n02_object_type_freeze'] is True"
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `backup_seed_authority_snapshot` / `list_seed_authority_backups` / `restore_seed_authority_snapshot` / product apply auto-backup |
| Facade / HTTP | `backup_knowledge_*` + `/object-types/product/seed-authority/{backup,backups,restore}` |
| UI | `ObjectTypePublishPanel` Backup / Restore |

## 明确未做

- 原地改写 / 删除 `workspace_seeds/**-object-types.json`
- `seed_replacement_complete=true` / N02 certified
- 关闭 residual opt-in 或翻 freeze
