---
doc_type: Report
---

# Batch 05 事实审核台账（子仓 docs）

## 范围与结果

```text
aiPlat-core/docs/        74   pass 41 / fix 33
aiPlat-infra+platform    47   pass 31 / fix 16
aiPlat-management+app    38   pass 33 / fix 4  / needs-owner 1
合计                    159   pass 105 / fix 53 / needs-owner 1
```

## 已修复（本轮可直接修的部分）

### Core 路径根因

全局替换 24 份 core docs 中的失效根路径：

```text
core/harness/execution/loop.py → core/harness/execution/loop/
core/services/execution_store.py → core/services/execution_store/
docs/research/ → docs/reference/research/
indexer.py → wiki_indexer.py
```

### Management / App 选中项

- `overview.md`：`overviewApi/alertsApi` → `apiClient.ts`；`alerts.py` → `alerting.py`；
- `infra/models.md`：`external_storage.py` → `storage.py`；
- `aiPlat-app` 用户/开发者文档增加历史设计说明：当前 CLI 仅 `agents/execute/run/status/kb`，当前仓库为 Python package，不是 TS/React `app/` 结构。

## 未修复（已在 agent 台账中列明）

```text
core docs 剩余 30+ 处符号/状态/行号问题
infra docs 16 处（MCP 幻影包、config 路径、测试命令等）
platform docs 4 处（GraphQL/WebSocket、config/deploy 目录）
app ops 1 处（部署主机树，needs-owner）
```

这些需要逐篇人工决定，不能安全批量替换。

## 关键发现

### Core

```text
loop.py / execution_store.py / langgraph nodes 是主要根因
ARCHITECTURE_STATUS 的 tool 状态与 embedding 描述已过期
contracts/06 acceptance 命令指向不存在的 docs/research/
```

### Infra / Platform

```text
infra/mcp/ 整个包不存在，真实 MCP 在 core
config/infra/*.yaml 实际是 default.yaml 的 section
platform 的 GraphQL/WebSocket 被标为已实现，但平台无实现
platform 无 config/、无 deploy/
```

### Management / App

```text
文件重命名未同步：alerts.py → alerting.py、external_storage.py → storage.py
aiPlat-app 文档仍描述旧的 TS/React app/ 布局和未发布的 aiplat-cli
```

## 累计

```text
standards  16
contracts  36
architecture 61
products   14
guides     34
subrepos   159
合计       320 份文档
needs-owner 10
```
