---
title: "aiPlat 生态与集成白皮书"
volume_id: ecosystem-integration
type: whitepaper-volume
status: generated
generated_at: "2026-10-12T15:46:59Z"
audience: "ISV、集成商、开源社区、渠道"
core_question: "如何接入、贡献、协作？"
priority: P2
source_status: gap
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "d81e99f21c3729fe2714e4e604af7e00a5b60d77114df7f25694b3ec66bce425"
language: zh-CN
---

<!-- volume_stamp id=ecosystem-integration suite_sha256=d81e99f21c3729fe2714e4e604af7e00a5b60d77114df7f25694b3ec66bce425 -->

# aiPlat 生态与集成白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `ecosystem-integration` |
| 受众 | ISV、集成商、开源社区、渠道 |
| 核心问题 | 如何接入、贡献、协作？ |
| 优先级 | P2 |
| 材料完备度（suite） | `gap` |
| 生成时间 (UTC) | `2026-10-12T15:46:59Z` |

**备注**：

核心接口稳定 + 早期伙伴验证后再发正式卷。

## 1. 本卷论证目标

本卷面向 **ISV、集成商、开源社区、渠道**，围绕「**如何接入、贡献、协作？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md) | MCP 生产准入 | ✅ |
| [`packages/aiplat-pi-runtime/README.md`](../../packages/aiplat-pi-runtime/README.md) | 厂外 Pi 包交付 | ✅ |
| [`docs/API/api-reference.md`](../API/api-reference.md) | API 参考（若存在） | ✅ |


## 3. 正文编排（节选权威源）

### 3.1 MCP / A2A 能力切片（CAPABILITIES）

> ⚠️ suite 标注本卷仍为 gap：伙伴权益/贡献机制专稿待补。

## 十四、MCP 协议

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| MCPToolAdapter | `apps/mcp/adapter.py` | ✅ | 自动同步 | 已合入 |
| MCPClientManager | `apps/mcp/client.py` | ✅ | 自动同步 | 已合入 |
| MCPRuntime | `apps/mcp/runtime.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| MCP JSON-RPC 2.0 | apps/mcp/protocol.py | ✅ | 完整 MCP 协议实现 (init, tools/list, tools/call) | 已合入 |
| MCP HTTP+SSE Server | apps/mcp/server.py | ✅ | 远程工具暴露服务 | 已合入 |
| MCP Stdio Transport | apps/mcp/local_tools_server.py | ✅ | 工作区工具暴露给 AI 编辑器 | 已合入 |
| MCP Runtime Wiring | apps/mcp/runtime.py | ✅ | MCP Server → ToolRegistry 运行时绑定 + PolicyGate | 已合入 |
| MCP Client Manager | apps/mcp/client.py | ✅ | 多服务端客户端连接生命周期管理 | 已合入 |
| MCP Production Policy | core/mcp/prod_policy.py | ✅ | 生产安全策略 (risk level, allowed tools) | 已合入 |
| MCP 搜索 Server（aiplat-search） | workspace_seeds/mcps/search/mcp_server.py | ✅ | 搜索基础设施 MCP（AnySearch 借鉴 P1-1，2026-08-28）：JSON-RPC over stdio，三工具 search_web（结构化信源标注事实条目）/ search_routed（意图路由三通道分发）/ search_intent（意图判定）；server 启动自动物化到 ~/.aiplat/mcps/search（对齐 file_ops 等种子 MCP）；MCP_SEARCH_WEB_ENABLED=false 可关 web 通道（隐私场景） | 已合入 |

---


## 十四附、A2A 协议 (Agent-to-Agent)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| AgentMessageBus | `core/harness/interfaces/messaging.py` | ✅ | 自动同步 | 已合入 |
| AgentDiscovery | `harness/ontology_engine/triple_scanner.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Agent Card | apps/a2a/agent_card.py | ✅ | 自动枚举 Skill/Tool 能力 + JSON-LD 上下文 | 已合入 |
| Task Send | apps/a2a/server.py | ✅ | POST /tasks → 复用 core_chat 执行 | 已合入 |
| Task Get | apps/a2a/server.py | ✅ | GET /tasks/{id} → 复用 ExecutionStore | 已合入 |
| Task Stream | apps/a2a/server.py | ✅ | SSE /tasks/{id}/stream → 复用 ReActLoop | 已合入 |
| Task Cancel | apps/a2a/server.py | ✅ | POST /tasks/{id}/cancel | 已合入 |
| Task Artifacts | apps/a2a/server.py | ✅ | GET /tasks/{id}/artifacts → 复用 TaskSkills | 已合入 |
| Task List | apps/a2a/server.py | ✅ | GET /tasks 任务列表 | 已合入 |

---



### 3.2 MCP 生产准入

#!/bin/false
# prod 放行 stdio MCP（路线A）策略

> 背景：stdio MCP 等同于在 core 所在机器上启动本机进程（高风险 L3）。  
> 目标：在 **prod 也允许使用** 的前提下，提供可审计、可回滚、默认拒绝的显式放行机制。

## 1) 放行条件（必须同时满足）

当 `AIPLAT_ENV=prod` 时，以下条件必须全部满足，stdio MCP 才允许：

1. `~/.aiplat/mcps/<server>/server.yaml` 的 `metadata.prod_allowed: true`
2. 环境变量 `AIPLAT_PROD_STDIO_MCP_ALLOWLIST` 包含该 `server_name`（逗号分隔）
3. `server.yaml` 的 `command` 为绝对路径，且命令路径前缀在 `AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES` 允许范围内  
   - 该变量支持 `:`（os.pathsep）或 `,` 分隔多个前缀
4. 加固校验（prod 默认启用）：
   - 禁止高风险解释器作为入口命令（默认：`bash,sh,zsh`；可用 `AIPLAT_STDIO_DENY_COMMAND_BASENAMES` 覆盖）
   - 命令必须存在且具备可执行权限（best-effort：`os.path.exists` + `os.access(..., X_OK)`）
   - 参数数量/长度限制（默认：最多 32 个参数、每个参数最多 （参见 AIPLAT_CAPABILITIES.md 当前计数） 字符；可通过 `AIPLAT_STDIO_MAX_ARGS` / `AIPLAT_STDIO_MAX_ARG_LENGTH` 调整）
5. 推荐增强（可选开启）：prod 强制统一 launcher
   - `AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD=true`
   - `AIPLAT_STDIO_PROD_LAUNCHER=/opt/aiplat/mcp/bin/launch`
   - 开启后：`server.yaml.command` 必须与 `AIPLAT_STDIO_PROD_LAUNCHER` 完全一致（避免散落多入口命令）

示例：

```bash
export AIPLAT_ENV=prod
export AIPLAT_PROD_STDIO_MCP_ALLOWLIST="integrated_browser,my_internal_stdio_server"
export AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES="/opt/aiplat/mcp/bin:/usr/local/aiplat/mcp/bin"
export AIPLAT_STDIO_DENY_COMMAND_BASENAMES="bash,sh,zsh"
export AIPLAT_STDIO_MAX_ARGS="32"
export AIPLAT_STDIO_MAX_ARG_LENGTH="512"
export AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD="true"
export AIPLAT_STDIO_PROD_LAUNCHER="/opt/aiplat/mcp/bin/launch"
```

server.yaml 示例：

```yaml
name: my_internal_stdio_server
enabled: false
transport: stdio
command: /opt/aiplat/mcp/bin/my-server
args: ["--config", "/etc/aiplat/mcp/my-server.yaml"]
metadata:
  description: 内部受控 stdio MCP server
  prod_allowed: true
```

使用 launcher 时的 server.yaml 示例：

```yaml
name: my_internal_stdio_server
enabled: false
transport: stdio
command: /opt/aiplat/mcp/bin/launch
args: ["my_internal_stdio_server", "--config", "/etc/aiplat/mcp/my-server.yaml"]
metadata:
  description: 内部受控 stdio MCP server（通过统一 launcher 启动）
  prod_allowed: true
```

## 2) 受影响的操作

在 prod 中，stdio MCP 的以下操作都会触发同一套放行校验：
- 启用：`POST /api/core/workspace/mcp/servers/{name}/enable`
- 工具发现：`GET /api/core/workspace/mcp/servers/{name}/tools`

若未满足条件，接口返回 403，并在 UI 中提示策略原因。

## 3) 为什么需要双白名单（server + command 前缀）

- **server_name 白名单**：防止任意人创建新 server 并启用（控制面可控）
- **command 前缀白名单**：防止用 `bash`/`python`/任意路径执行任意代码（执行面可控）

## 4) 建议（进一步增强）

- 将 `command` 收敛为受控的 launcher（例如 `/opt/aiplat/mcp/bin/launch`），由 launcher 再选择具体子命令
- 配置审计：记录 enable/disable 以及 tools/call 的审计日志（输入输出摘要）
- 资源限制：超时、并发、CPU/内存配额（若支持容器/沙箱更佳）

## 5) 已落地的审计

当前已将 MCP 管理动作写入 ExecutionStore 的 `syscall_events`（kind=`mcp_admin`）：
- workspace.mcp.upsert
- workspace.mcp.enable / workspace.mcp.disable
- workspace.mcp.discover_tools

用于后续在 Traces/审计页面统一查询与追踪。


### 3.3 厂外 Pi Package

# @aiplat/pi-runtime

Thin **Pi Package** Runtime for aiPlat factory **Agent-mode** artifacts.

- **aiPlat** = heavy factory (PRD → AGENT.md / SKILL.md / `agent_manifest.json`)
- **This package** = **厂外** user-side thin host (Pi extensions + package `skills/`)

## Two axes (do not merge)

See [`docs/architecture/plans/pi-thin-runtime.md`](../../docs/architecture/plans/pi-thin-runtime.md).

| Axis | Role of Pi | Status |
|------|------------|--------|
| **(B) Factory-out** | User-side host for artifacts | **Shipped** — this package |
| **(A) Factory-in** | Optional coding exec kernel behind PolicyGate | Experiment only — not default ReActLoop |

**Product decision (locked)**

| Mode | Meaning |
|------|---------|
| **Pi-only** (default) | Artifacts run with Pi alone: SOP + skills + handler + your LLM. No 8002/8003. |
| **Pi + aiPlat** (enterprise) | Same Pi shell; enterprise features via aiPlat APIs (PolicyGate / Memory / KB / audit). |
| Thick aiPlat-only on user machine | **Not** the default delivery shape. |

Do not claim Pi-only equals full in-factory agent. Enterprise thickness is **Pi + aiPlat**, not “stuff the platform into the Pi process”.

## Scheme A (Skills)

Skills are **copied into** the package `skills/` directory at export time. Pi auto-discovers them. There is **no** `registerSkill` API.

## Quick start

```bash
# Install Pi (Node >= 22.19)
npm install -g --ignore-scripts @earendil-works/pi-coding-agent

# Smoke this package
cd packages/aiplat-pi-runtime
pi -e .
# /aiplat-status
# /skill:fixture-skill
# /aiplat-sop-check
```

With an exported app:

```bash
export AIPLAT_APP_HOME=/path/to/exported-app   # contains agent_manifest.json
pi -e /path/to/aiplat-pi-runtime
# or: aiplat-run
```

Export from aiPlat disk deploy:

```bash
python3 scripts/export_pi_bundle.py --app-home ~/.aiplat/apps/<project_id>/current --out dist/aiplat-app-<id>
pi install ./dist/aiplat-app-<id>
```

## Thin HTTP (Phase 2)

```bash
AIPLAT_HTTP_STUB=1 AIPLAT_APP_HOME=./fixtures/sample-app \
  AIPLAT_HTTP_API_KEY=dev node bin/aiplat-http.mjs
# GET  /health
# POST /v1/chat            Authorization: Bearer dev
# POST /v1/skills/demo_skill   → handler.py if present

bash scripts/http_smoke.sh
```

Agent mode (OpenAI-compatible — Ollama default):

```bash
# ensures ~/.pi/agent/models.json has ollama provider (for CLI)
bash scripts/ensure_ollama_models_json.sh

AIPLAT_PI_MODEL=ollama/qwen2.5:3b AIPLAT_APP_HOME=./fixtures/sample-app \
  AIPLAT_HTTP_API_KEY=dev node bin/aiplat-http.mjs
# Optional: AIPLAT_PI_BASE_URL / AIPLAT_PI_API_KEY / AIPLAT_PI_SDK_ROOT

# Full live gate (offline + stub HTTP + CLI + HTTP agent)
AIPLAT_PI_MODEL=ollama/qwen2.5:3b bash scripts/live_smoke.sh
```

## Factory-in experiment (not wired to engine)

Optional way-4 CLI: `scripts/coding_exec.py` (Pi print-mode coding). Refuses host cwd unless `--allow-host`; does **not** replace ReActLoop / PipelineEngine.

```bash
python3 scripts/test_coding_exec_unit.py
bash scripts/coding_exec_smoke.sh
```

See [docs/FACTORY_IN_EXPERIMENT.md](./docs/FACTORY_IN_EXPERIMENT.md).

See [PHASE0.md](./PHASE0.md) and `docs/architecture/plans/pi-thin-runtime.md`.


### 3.4 MCP 文档索引

# MCP 协议集成设计

## 概述

本文档描述如何将 Model Context Protocol (MCP) 集成到 aiPlat-core 系统，使系统能够连接外部 MCP 服务器并使用其提供的工具。

## 目标

1. **连接外部 MCP 服务器** - 支持 stdio 和 SSE 传输
2. **工具接入** - 将 MCP 工具转换为本地 ITool 接口
3. **工具导出** - 将本地工具暴露为 MCP 服务器

## 架构设计

### 模块结构

```
core/apps/mcp/
├── types.py       # 协议数据类型定义
├── protocol.py    # JSON-RPC 处理、SSE/stdio 传输
├── client.py      # MCP Client 和 ClientManager
├── adapter.py     # 工具适配器 (MCP ↔ ITool)
├── server.py      # MCP Server (FastAPI)
└── config.py      # 配置管理
```

### 核心组件

#### 1. 类型定义 (types.py)

| 类型 | 用途 |
|------|------|
| `JSONRPCRequest` | JSON-RPC 请求 |
| `JSONRPCResponse` | JSON-RPC 响应 |
| `MCPTool` | MCP 工具定义 |
| `MCPToolResult` | 工具调用结果 |
| `MCPResource` | MCP 资源定义 |
| `MCPServerCapabilities` | 服务器能力 |
| `MCPServerConfig` | 服务器配置 |
| `MCPClientConfig` | 客户端配置 |

#### 2. 协议处理 (protocol.py)

- JSON-RPC 2.0 请求/响应编解码
- SSE (Server-Sent Events) 传输
- STDIO 传输

#### 3. 客户端 (client.py)

| 类 | 职责 |
|------|------|
| `MCPClient` | 单个 MCP 服务器连接管理 |
| `MCPClientManager` | 多服务器连接管理 |

#### 4. 适配器 (adapter.py)

| 类 | 职责 |
|------|------|
| `MCPToolAdapter` | MCP 工具 → 本地 ITool |
| `MCPToolExporter` | 本地 ITool → MCP 工具 |
| `MCPClientWrapper` | 批量注册 MCP 工具到注册表 |

## 使用方式

### 1. 连接外部 MCP 服务器

```python
from core.apps.mcp import MCPClientManager, MCPClientConfig

manager = MCPClientManager()

# SSE 连接
client = await manager.add_server(
    "my-server",
    MCPClientConfig(
        server_url="http://localhost:3000/mcp",
        transport=TransportType.SSE
    )
)

# STDIO 连接
client = await manager.add_server(
    "filesystem",
    MCPClientConfig(
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    )
)
```

### 2. 注册 MCP 工具到本地注册表

```python
from core.apps.mcp.adapter import MCPClientWrapper

wrapper = MCPClientWrapper(manager)
count = await wrapper.register_server_tools("my-server", tool_registry)
print(f"Registered {count} tools")
```

### 3. 启动 MCP 服务器（暴露本地工具）

```python
from core.apps.mcp import MCPServer

server = MCPServer(tool_registry)
await server.start(host="0.0.0.0", port=8080)
```

## 配置

### 0. 目录化配置（engine vs workspace）

MCP server 的“启用/禁用/策略”推荐以文件系统为真值来源，并按 scope 分离：

- **引擎内置（engine，仅核心能力层使用）**  
  `aiPlat-core/core/engine/mcps/<server>/{server.yaml,policy.yaml}`

- **应用库（workspace，对外/用户可用）**  
  `~/.aiplat/mcps/<server>/{server.yaml,policy.yaml}`

管理面对应两套入口（避免混用）：
- engine：`GET/POST /api/core/mcp/servers*`
- workspace：`GET/POST /api/core/workspace/mcp/servers*`

### 服务器配置 (MCP Server)

```python
MCPServerConfig(
    name="my-server",
    transport=TransportType.SSE,  # 或 STDIO
    command="python",  # for stdio
    args=["server.py"],
    url="http://localhost:3000",  # for sse
    auth={"type": "bearer", "token": "..."}
)
```

### 客户端配置 (MCP Client)

```python
MCPClientConfig(
    server_url="http://localhost:3000/mcp",
    transport=TransportType.SSE,
    timeout=30000,  # ms
    auth={"type": "bearer", "token": "..."}
)
```

## 安全考虑

1. **URL 白名单** - HTTP 工具应配置允许的域名
2. **认证** - 支持 Bearer Token 认证
3. **超时控制** - 防止工具调用挂起
4. **响应大小限制** - 防止过大响应占用内存

## 待实现

- [ ] STDIO 传输的进程启动和管理
- [ ] MCP 服务器认证
- [ ] 工具缓存和刷新机制
- [ ] 连接池管理


## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`ecosystem-integration`*
