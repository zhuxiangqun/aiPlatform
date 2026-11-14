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

## 后续闭环（2026-11-14）

已修：
- CAPABILITIES：`FDEBuilderOrchestrator` ✅→⚠️ 已归档
- platform CLAUDE / BOUNDARY / gateway / architect：去掉「已提供 GraphQL/WS」口径
- app CLAUDE / docs：向下依赖改为 REST only
- infra `docs/mcp` 改为占位重定向；architect/developer 去 `infra/mcp/*` 幻影路径
- platform ops/developer：标明无 `config/`、`deploy/` 树；deployment 指向真实 `DeploymentManager`

续修（2026-11-14 同 PR）：
- `ARCHITECTURE_STATUS`：CodeExecutionTool / BrowserTool ❌→✅
- infra docs index + developer：canonical `aiPlat-infra/config/infra/`；去掉假 `*.yaml.example` / 假 make 入口
- app ops：文首降级为历史示意（needs-owner 仍登记，待现网证据）
- core docs：`execution/loop.py` → `execution/loop/`（多篇 harness/architecture/testing）
- core/platform developer：验证命令改为 pytest（根仓无统一 Makefile）

续修 tranche-4（2026-11-14）：
- `indexer.py` 树图 → `wiki_indexer.py`；overview/tot_reserve `loop/` 对齐
- core/platform ops·developer 去剩余 make 幻影
- infra 15 个模块 index 加 As-Is 配置 section 横幅

续修 tranche-5（2026-11-14）：
- infra developer：目录树/表去掉 `mcp/`；`make test-infra-*` → pytest

路径级高信号幻影（loop/indexer/GraphQL/Makefile/infra.mcp）在活跃 docs 已基本清零。

续修 tranche-6（2026-11-14）：
- core developer / harness / services / framework：幻影路径改为现网入口
- design/* 加 As-Is 横幅（历史/To-Be 引用勿当已实现）

续修 tranche-7（2026-11-14）：
- infra developer：logging/compute/memory/network 独立 yaml → `default.yaml` section
- `reports/README.md`、`docs/archive/README.md` 加强「非现网契约」声明

诚实对账收口（活跃 docs 路径级 + 配置入口级）：
```text
剩余仅：infra 模块正文内示意 yaml 块（已有模块 As-Is 横幅）
        design/* 正文历史路径（已有横幅）
        archive/reports 正文本身（索引已声明非契约）
```

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
