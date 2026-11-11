---
doc_type: Index
---

# Reports 生命周期

> v2.4 定义。报告/证据不是文档 canonical，不参与标准评审。

## 分层

| 路径 | 内容 | 保留期 | 处理 |
|---|---|---|---|
| `reports/products/five-products/modules/` | 产品定义 | 长期 | 维护 |
| `reports/products/five-products/contracts/` | 产品契约 | 长期 | 维护 |
| `reports/products/five-products/ops/` | 运行证据/回执 | 180 天 | 归档 `_archive` |
| `reports/security/evidence/` | 安全证据 | 365 天 | 合规归档 |
| `reports/docs-governance/` | 文档治理过程 | 365 天 | 归档 |
| 根 `reports/*.md` | 分析快照 | 90 天 | 归档 |
| `reports/**/_archive/` | 历史 | 永久 | 只读 |

## 规则

- 报告禁止手工编辑；需要新数据时重新生成；
- 报告头必须包含生成时间、生成命令、“不手动编辑”声明；
- 运行证据只追加，不参与 canonical；
- 生成物只写 `reports/`，不写 `docs/`。
