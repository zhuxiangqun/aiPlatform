# 生态伙伴技术分层（权威专稿）

> 供生态与集成白皮书节选。本专稿只定义**接入权限与交付形态**，不定义分成/返佣。  
> 商务条款见 [`ecosystem-partner-commercial-template.md`](./ecosystem-partner-commercial-template.md)（以盖章版为准）。

## 1. 分层总览

| 层 | 伙伴做什么 | 典型入口 | 平台侧治理 |
|----|------------|----------|------------|
| **L0 Pi-only** | 消费工厂导出的薄 Runtime 包，自备模型 | `packages/aiplat-pi-runtime` · 导出 ZIP | 能力边界写进交付说明；无平台 Memory/SECI |
| **L1 KB 混合** | Pi 壳 + 只读知识检索回连 | `AIPLAT_ENTERPRISE=1` · `aiplat_kb_retrieve` | 平台 `kb:read` / PolicyGate |
| **L2 工具代理** | 允许列表内工具 HTTP 执行 | `AIPLAT_ENTERPRISE_TOOLS` · `aiplat_tool_execute` | Core `/api/core/tools/{name}/execute` + RBAC |
| **L3 MCP / API ISV** | 注册 MCP 工具或调 HTTP API | `docs/mcp/` · `docs/API/` | MCP 生产准入 · 鉴权/租户/限流 |
| **L4 私有化厚部署** | 驻场/私有化接近全栈 | 特殊合同 · 非默认交付 | 全量治理面由平台侧强制 |

默认交付锁定 **L0**。企业加厚按 L1→L2→L3 阶梯开启；L4 非默认。详见 [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md)。

## 2. 各层说明

### 2.1 Pi-only 接入

仅使用导出包内 SOP / skills / handler + 用户自备 LLM。不要求 8002/8003。

### 2.2 KB 混合接入

在 L0 基础上 opt-in 回连 `POST /platform/kb/query`。断连时回退本地 skills，禁止编造引用。

### 2.3 工具代理接入

须显式允许列表；空列表 = 工具代理关闭。PolicyGate 留在 Core，扩展只转发 Bearer。

### 2.4 MCP / API ISV 接入

通过 MCP 或 REST 暴露/消费平台能力。生产 MCP 须符合 `docs/policy/mcp-stdio-prod-allowlist.md` 与成本阶梯。

### 2.5 私有化厚部署

接近全栈 aiPlat 的驻场形态；**不是**厂外默认交付，须单独合同与运维边界。

## 3. 开放边界矩阵

| 接入面 | 伙伴/集成商做什么 | 权威入口 | 平台侧治理 |
|--------|-------------------|----------|------------|
| MCP 工具 | 注册/暴露工具 | `docs/mcp/index.md` | MCP 准入 + 成本阶梯 |
| HTTP API | 调平台/Core | `docs/API/api-reference.md` | 鉴权 / 租户 / 限流 |
| A2A | Agent 间互操作 | CAPABILITIES「A2A」 | PolicyGate / 身份透传 |
| Pi Package | 薄 Runtime 包 | `packages/aiplat-pi-runtime/README.md` | 交付边界说明 |
| Skill / Handler | 贡献可执行技能 | CAPABILITIES「Skill」 | `execution_type` + lint |

## 4. 治理边界

权限、审计、数据隔离、升级责任以 `docs/security/security-architecture.md` 与 `AIPLAT_CAPABILITIES.md` 安全/治理切片为准。伙伴不得要求在 Pi 进程内重实现 PolicyGate。
