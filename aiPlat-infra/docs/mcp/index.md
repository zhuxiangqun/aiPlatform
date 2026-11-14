---
doc_type: Index
---

# MCP（infra 文档占位）

> **As-Is（2026-11）**：`aiPlat-infra/infra/mcp/` **不存在**（2026-05 已删）。infra 层不管理 MCP。

## 唯一实现位置

| 路径 | 说明 |
|------|------|
| `aiPlat-core/core/apps/mcp/` | MCP client / server / adapter / protocol / config |
| `aiPlat-core/core/mcp/` | 运行时同步与生产策略（`runtime_sync.py`、`prod_policy.py`） |
| `docs/reference/mcp/index.md` | 设计与模块结构说明（指向 core） |

## 禁止

- 在文档或示例中引用 `infra.mcp`、`infra/mcp/*`、`from infra.mcp import …`
- 把历史双栈叙述当作当前架构

历史设计稿若需查阅，以 git 历史为准；本页不再保留虚假文件树与工厂示例。
