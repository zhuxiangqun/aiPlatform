---
title: "aiPlat 生态与集成白皮书"
volume_id: ecosystem-integration
type: whitepaper-volume
doc_type: Report
status: generated
generated_at: "2026-11-12T09:33:20Z"
audience: "ISV、集成商、开源社区、渠道"
core_question: "如何接入、贡献、协作？"
priority: P2
source_status: ready
suite: docs/reference/explanatory/whitepaper-suite.yaml
suite_sha256: "917aa76340b4d2b2d6f40ff4f227007cd89f4eb79748529df30513bf43abbc8c"
caps_sha256: "579bd50c9b85b9450451e6713941da787c7ff443ccb732a866cfd89af36a7488"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=ecosystem-integration suite_sha256=917aa76340b4d2b2d6f40ff4f227007cd89f4eb79748529df30513bf43abbc8c caps_sha256=579bd50c9b85b9450451e6713941da787c7ff443ccb732a866cfd89af36a7488 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 生态与集成白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI
> 体系：[`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md) · 清单：[`../../../docs/reference/explanatory/whitepaper-suite.yaml`](../../../docs/reference/explanatory/whitepaper-suite.yaml)
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `ecosystem-integration` |
| 受众 | ISV、集成商、开源社区、渠道 |
| 核心问题 | 如何接入、贡献、协作？ |
| 优先级 | P2 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-11-12T09:33:20Z` |
| CAPABILITIES sha256 | `579bd50c9b85…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

**备注**：

开放面：MCP、HTTP API、Pi Package、A2A、Skill。技术分层已闭环。 商务条款以盖章版为准；模板不构成要约。


## 1. 本卷论证目标

本卷面向 **ISV、集成商、开源社区、渠道**，围绕「**如何接入、贡献、协作？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/mcp/index.md`](../../../docs/reference/mcp/index.md) | MCP 文档入口 | ❌ |
| [`docs/API/api-reference.md`](../../../docs/reference/API/api-reference.md) | API 参考 | ❌ |
| [`docs/policy/mcp-stdio-prod-allowlist.md`](../../../docs/reference/policy/mcp-stdio-prod-allowlist.md) | MCP 生产准入（治理边界） | ❌ |
| [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | 厂外 Pi Package 交付面 | ✅ |
| [`docs/reference/explanatory/ecosystem-partner-tiers.md`](../../../docs/reference/explanatory/ecosystem-partner-tiers.md) | 技术伙伴分层（Pi/KB/工具/MCP/私有化） | ✅ |
| [`docs/reference/templates/ecosystem-partner-commercial-template.md`](../../../docs/reference/templates/ecosystem-partner-commercial-template.md) | 商务条款空白模板（不构成要约） | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/API/AttributionSchema.md`](../../../docs/reference/API/AttributionSchema.md) | 归因协议 | ❌ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | Pi 薄 Runtime 战略边界 | ✅ |
| [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md) | 企业混合回连阶梯 | ✅ |
| [`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md) | 白皮书体系（生态卷定位） | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 生态伙伴分层与开放边界

本卷以技术伙伴分层闭环，不写未确认的分成比例、商标授权或排他条款。

- 技术分层：[`docs/reference/explanatory/ecosystem-partner-tiers.md`](../../../docs/reference/explanatory/ecosystem-partner-tiers.md)
  - Pi-only 接入
  - KB 混合接入
  - 工具代理接入
  - MCP / API ISV 接入
  - 私有化厚部署
- 开放边界矩阵：见 `ecosystem-partner-tiers.md` 第 3 节
- 企业混合部署：[`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md)；能力行以 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) 为准
- 商务条款模板：[`docs/reference/templates/ecosystem-partner-commercial-template.md`](../../../docs/reference/templates/ecosystem-partner-commercial-template.md)

---

> **商务条款声明**
>
> 分成、权益、商标、排他等条款以双方盖章版协议为准。`ecosystem-partner-commercial-template.md` 仅为空白模板，不构成要约。

---

生态卷 ready 边界：技术分层与开放边界已闭环；商务条款提供可盖章模板附录；正文不写假分成。

### 3.1 技术分层专稿（节选）

### 生态伙伴技术分层（权威专稿）

> 供生态与集成白皮书节选。本专稿只定义**接入权限与交付形态**，不定义分成/返佣。
> 商务条款见 [`ecosystem-partner-commercial-template.md`](../../../docs/reference/templates/ecosystem-partner-commercial-template.md)（以盖章版为准）。

#### 1. 分层总览

| 层 | 伙伴做什么 | 典型入口 | 平台侧治理 |
|----|------------|----------|------------|
| **L0 Pi-only** | 消费工厂导出的薄 Runtime 包，自备模型 | `packages/aiplat-pi-runtime` · 导出 ZIP | 能力边界写进交付说明；无平台 Memory/SECI |
| **L1 KB 混合** | Pi 壳 + 只读知识检索回连 | `AIPLAT_ENTERPRISE=1` · `aiplat_kb_retrieve` | 平台 `kb:read` / PolicyGate |
| **L2 工具代理** | 允许列表内工具 HTTP 执行 | `AIPLAT_ENTERPRISE_TOOLS` · `aiplat_tool_execute` | Core `/api/core/tools/{name}/execute` + RBAC |
| **L3 MCP / API ISV** | 注册 MCP 工具或调 HTTP API | `docs/reference/mcp/` · `docs/reference/API/` | MCP 生产准入 · 鉴权/租户/限流 |
| **L4 私有化厚部署** | 驻场/私有化接近全栈 | 特殊合同 · 非默认交付 | 全量治理面由平台侧强制 |

默认交付锁定 **L0**。企业加厚按 L1→L2→L3 阶梯开启；L4 非默认。详见 [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md)。

#### 2. 各层说明

##### 2.1 Pi-only 接入

仅使用导出包内 SOP / skills / handler + 用户自备 LLM。不要求 8002/8003。

##### 2.2 KB 混合接入

在 L0 基础上 opt-in 回连 `POST /platform/kb/query`。断连时回退本地 skills，禁止编造引用。

##### 2.3 工具代理接入

须显式允许列表；空列表 = 工具代理关闭。PolicyGate 留在 Core，扩展只转发 Bearer。

##### 2.4 MCP / API ISV 接入

通过 MCP 或 REST 暴露/消费平台能力。生产 MCP 须符合 `docs/reference/policy/mcp-stdio-prod-allowlist.md` 与成本阶梯。

##### 2.5 私有化厚部署

接近全栈 aiPlat 的驻场形态；**不是**厂外默认交付，须单独合同与运维边界。

#### 3. 开放边界矩阵

| 接入面 | 伙伴/集成商做什么 | 权威入口 | 平台侧治理 |
|--------|-------------------|----------|------------|
| MCP 工具 | 注册/暴露工具 | `docs/reference/mcp/index.md` | MCP 准入 + 成本阶梯 |
| HTTP API | 调平台/Core | `docs/reference/API/api-reference.md` | 鉴权 / 租户 / 限流 |
| A2A | Agent 间互操作 | CAPABILITIES「A2A」 | PolicyGate / 身份透传 |
| Pi Package | 薄 Runtime 包 | `packages/aiplat-pi-runtime/README.md` | 交付边界说明 |
| Skill / Handler | 贡献可执行技能 | CAPABILITIES「Skill」 | `execution_type` + lint |

#### 4. 治理边界

权限、审计、数据隔离、升级责任以 `docs/reference/security/security-architecture.md` 与 `AIPLAT_CAPABILITIES.md` 安全/治理切片为准。伙伴不得要求在 Pi 进程内重实现 PolicyGate。


### 3.2 开放边界矩阵（接入面）

| 接入面 | 伙伴/集成商做什么 | 权威入口 | 平台侧治理 |
|--------|-------------------|----------|------------|
| **MCP 工具** | 注册/暴露工具供 Agent 调用 | [`docs/mcp/index.md`](../../../docs/reference/mcp/index.md) | [`docs/reference/policy/mcp-stdio-prod-allowlist.md`](../../../docs/reference/policy/mcp-stdio-prod-allowlist.md) + 成本阶梯 |
| **HTTP API** | 调平台/Core 能力 | [`docs/API/api-reference.md`](../../../docs/reference/API/api-reference.md) | 鉴权 / 租户 / 限流（platform） |
| **A2A** | Agent 间互操作 | CAPABILITIES「A2A 协议」切片 | PolicyGate / 身份透传 |
| **Pi Package** | 消费工厂导出的薄 Runtime 包 | [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) · [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | 能力边界写进交付说明（无平台 Memory/SECI） |
| **Skill / Handler** | 贡献可执行技能 | CAPABILITIES「Skill 系统」· engine skills | `execution_type` + lint + 准入 |

### 3.3 MCP / A2A 能力切片（CAPABILITIES）

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



### 3.4 MCP 文档入口

_(存在性检查失败：文件缺失 `docs/mcp/index.md`)_


### 3.5 MCP 生产准入

#!/bin/false
### prod 放行 stdio MCP（路线A）策略

> 背景：stdio MCP 等同于在 core 所在机器上启动本机进程（高风险 L3）。
> 目标：在 **prod 也允许使用** 的前提下，提供可审计、可回滚、默认拒绝的显式放行机制。

#### 1) 放行条件（必须同时满足）

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

#### 2) 受影响的操作

在 prod 中，stdio MCP 的以下操作都会触发同一套放行校验：
- 启用：`POST /api/core/workspace/mcp/servers/{name}/enable`
- 工具发现：`GET /api/core/workspace/mcp/servers/{name}/tools`

若未满足条件，接口返回 403，并在 UI 中提示策略原因。

#### 3) 为什么需要双白名单（server + command 前缀）

- **server_name 白名单**：防止任意人创建新 server 并启用（控制面可控）
- **command 前缀白名单**：防止用 `bash`/`python`/任意路径执行任意代码（执行面可控）

#### 4) 建议（进一步增强）

- 将 `command` 收敛为受控的 launcher（例如 `/opt/aiplat/mcp/bin/launch`），由 launcher 再选择具体子命令
- 配置审计：记录 enable/disable 以及 tools/call 的审计日志（输入输出摘要）
- 资源限制：超时、并发、CPU/内存配额（若支持容器/沙箱更佳）

#### 5) 已落地的审计

当前已将 MCP 管理动作写入 ExecutionStore 的 `syscall_events`（kind=`mcp_admin`）：
- workspace.mcp.upsert
- workspace.mcp.enable / workspace.mcp.disable
- workspace.mcp.discover_tools

用于后续在 Traces/审计页面统一查询与追踪。


### 3.6 API 参考（节选）

_(存在性检查失败：文件缺失 `docs/API/api-reference.md`)_


### 3.7 厂外 Pi Package

默认交付为 **Pi-only** 薄包；企业混合为可选回连（KB / 工具 / Memory / Approval），详情以包文档为准，本卷不复制 README 全文。

| 权威源 | 读什么 |
|--------|--------|
| [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | 包入口与双轴（厂外交付 / 厂内已关闭） |
| [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | 战略边界 living 摘要 |
| [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md) | 企业回连配置 |
| [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md) | SKU / 验收 |

> 「Hybrid」在此指 **Pi↔aiPlat 企业回连**，与 Skill `execution_type`、Builder 工厂模式中的其它 “hybrid” 用语不是同一概念。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`ecosystem-integration`*
