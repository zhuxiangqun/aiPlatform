---
doc_type: Report
---

# Batch 06 事实审核台账（packages）

## 范围与结果

```text
aiplat-evaluation/docs  59  pass 57 / fix 2
其他 5 个 package docs 48  pass 47 / fix 1
合计                   107  pass 104 / fix 3 / needs-owner 0
```

（`a3/human_pack` 生成快照与 `_archive` 未逐篇审。）

## 已修复

| 文档 | 问题 | 修复 |
|---|---|---|
| `evaluation/docs/a3/README.md` | 架构 freeze 写成“双挂=2” | 改为“单挂=1”，与 gate `mounts == 1` 一致 |
| `evaluation/docs/a3/SCORECARD_V1.md` | G2b κ≈0.63 过期；记录日 11-04 | 改为 0.7624；记录日 11-05 |
| `pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md` | 模板路径 `docs/manuals/...`；citation 写成未实现 | 改为 `docs/guides/fde/templates/...`；标为已实现 |

## 关键结论

```text
evaluation docs 的 evidence JSON 与正文数字一致
package docs 的 authorized=false 语义一致
未发现未授权生产/拆分声明
```

## 累计

```text
standards  16
contracts  36
architecture 61
products   14
guides     34
subrepos   159
packages   107
合计       427 份文档
needs-owner 10
```
