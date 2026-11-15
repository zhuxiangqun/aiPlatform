---
doc_type: Index
status: active
authority: supporting
doc_id: REPORTS_LIFECYCLE_INDEX
last_reviewed: 2026-11-15
---

# Reports 生命周期

> v2.4 定义。报告/证据不是文档 canonical，不参与标准评审。

> **As-Is（2026-11）**：`reports/`（含分析快照、白皮书生成物、`_archive/`）**不是**现网架构契约。文中路径/能力声明可能过期；以代码、`AIPLAT_CAPABILITIES.md`、`docs/architecture/` 为准。勿把历史分析稿里的 `infra/mcp`、GraphQL、假 make 入口等当作已实现。

## 分层

| 路径 | 内容 | 保留期 | 处理 |
|---|---|---|---|
| `docs/products/five-products/modules/` | 产品定义（规范树） | 长期 | 维护 |
| `docs/contracts/products/five-products/` | 产品叙事契约（旧 `reports/five-products/contracts/` 为 Index stub） | 长期 | 维护 |
| `reports/products/five-products/ops/` | 运行证据/回执（`aiplat_five_products_paths.sh` SoT；旧 `reports/five-products/ops/` 为 Index stub） | 180 天 | 归档 `_archive` |
| `reports/security/evidence/` | 安全证据 | 365 天 | 合规归档 |
| `reports/docs-governance/` | 文档治理过程 | 365 天 | 归档 |
| 根 `reports/*.md` | 分析快照 / 活日志 | 90 天（`doc_type: Index` stub 除外） | 超期归档；`audit_changelog.md` 为活日志保留 |
| `reports/**/_archive/` | 历史 | 永久 | 只读 |

## 规则

- 报告禁止手工编辑；需要新数据时重新生成；
- 报告头必须包含生成时间、生成命令、“不手动编辑”声明；
- 运行证据只追加，不参与 canonical；
- 生成物只写 `reports/`，不写 `docs/`。
