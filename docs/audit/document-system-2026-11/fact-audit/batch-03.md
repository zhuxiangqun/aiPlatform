---
doc_type: Report
---

# Batch 03 事实审核台账

## 范围

```text
docs/products/ 14/14
```

## 结果

```text
pass 12 / fix 2 / needs-owner 0
```

## 已修复

| 文档 | 问题 | 修复 |
|---|---|---|
| `evaluation/MODULE.md` | 引用模块内 `contracts/schemas/eval_protocol.schema.json` 和 `healthz.schema.json`，实际只有 README shim | 改为 `packages/aiplat-evaluation/contracts/schemas/` 并标注模块内为 shim |
| `evaluation/EVAL_PROTOCOL.md` | schema 路径同上 | 改为 package SSOT + shim 说明 |

## 根因

```text
Evaluation schema 的 SSOT 已移到 packages/aiplat-evaluation/contracts/schemas/，
产品文档仍指向模块内 shim 目录。
```

## 累计

```text
standards  16/16
contracts  36/36
architecture 61/61
products   14/14
合计       127 份文档已覆盖
needs-owner 8
```
