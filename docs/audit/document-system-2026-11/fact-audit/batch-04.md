---
doc_type: Report
---

# Batch 04 事实审核台账

## 范围

```text
docs/guides/ 34 份活跃文档
  - 通用 guides 16
  - FDE guides 18
```

## 结果

```text
general: pass 11 / fix 5 / needs-owner 0
FDE:     pass 10 / fix 7 / needs-owner 1
合计：   pass 21 / fix 12 / needs-owner 1
```

## 已修复

### 通用 guides

| 文档 | 问题 | 修复 |
|---|---|---|
| `engineering-quality.md` | required check 写成不存在的 `Test (aiPlat-core)` | 改为 `Test (pytest)` |
| `knowledge/knowledge-system.md` | OntologyEngine 同时写 13 步 / 8 阶段 / 8 个阶段 | 统一为 3 Phase |
| `management.md` | 6 分组 → 7；5 角色 → 8；诊断菜单 12 → 10；工具箱 27 → 25 | 已更新并补 eval 组、完整角色说明 |
| `management-ui-operation-manual.md` | 7 种角色 → 实际 8 | 已更新 |
| `production-readiness.md` | `docs/slo.md` 不存在、Grafana 路径错、workflow 数 3 → 11 | 已改为 `docs/architecture/slo.md`、实际 Grafana 路径、11 workflows |

### FDE guides

| 文档 | 问题 | 修复 |
|---|---|---|
| `fde/README.md` | UI `/diagnostics` 错；Core API 端口错；八步/九步自相矛盾 | `/diagnostics/fde`；Core `:8002/api/core`；统一九步主流程 |
| `01-fde-quickstart.md` | 8 步/8 Tab；UI 路径 | 九步主流程/10 Tab；`/diagnostics/fde` |
| `02-fde-delivery.md` | 八步/8 Tab；UI 路径 | 九步主流程/10 Tab；`/diagnostics/fde` |
| `03-fde-operations.md` | dashboard 10 指标 → 实际 13 | 已更新 |
| `04-fde-admin.md` | `/fde/overview` 不存在；scoring 路径缺 domains；脚本端口 8002 | 删除行、补 `/domains/{domain_id}`、改 8003 |
| `05-fde-implementation-process.md` | `/fde/score` 不存在；FDEBuilderOrch 已归档；JDBC 未实现 | 已改为真实状态 |
| `templates/fde-delivery-manual.md` | 导航 `README.md` 指错层 | 改为 `../README.md` |

## needs-owner

```text
docs/guides/fde/06-sop-domain-delivery.md
```

原因：引用的 `~/.aiplat/ontologies|actions|tests/service-domain*` 是 per-machine 状态，仓库只有 `workspace_seeds/ontologies/service-domain.yaml`，需 owner 确认。

## 累计

```text
standards  16/16
contracts  36/36
architecture 61/61
products   14/14
guides     34/34
合计       161 份文档
needs-owner 9
```
