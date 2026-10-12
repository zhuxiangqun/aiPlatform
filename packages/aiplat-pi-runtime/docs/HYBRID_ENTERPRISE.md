# Pi + aiPlat 企业级混合

> 产品锁定：默认 **Pi-only**；企业级 = **Pi 壳 + aiPlat 回连**。  
> **已接线**：只读 KB + 允许列表工具代理。其余项仍按阶梯推进。

## 原则

1. 用户侧始终以 Pi（或薄 HTTP）为对话宿主——不要求用户默认安装全栈 aiPlat。
2. 包内能力（SOP / skills / handler）在离线/断连时仍可用。
3. 企业能力不复制进 Pi 进程，经认证 API 调用平台（PolicyGate 仍在平台/Core 侧执行一次）。

## 环境变量

| 变量 | 含义 |
|------|------|
| `AIPLAT_PLATFORM_URL` | 平台基址（如 `https://tenant.example/api` 或 `:8003`） |
| `AIPLAT_CORE_URL` | 可选；工具执行基址（`:8002` 或 `…/api/core`）。未设时从 PLATFORM_URL 推导 |
| `AIPLAT_TENANT_TOKEN` / API Key | 身份注入；权限判断在平台 PolicyGate / RBAC |
| `AIPLAT_ENTERPRISE=1` | 启用回连；未设则严格 Pi-only |
| `AIPLAT_KB_COLLECTION_ID` | KB 集合（默认 `default`） |
| `AIPLAT_ENTERPRISE_TOOLS` | **工具允许列表**（逗号分隔）。空 = 工具代理关闭（仅 KB） |

## 回连能力阶梯

| # | 能力 | 状态 | 入口 |
|---|------|:----:|------|
| 1 | 只读知识检索 | ✅ | `aiplat_kb_retrieve` → `POST /platform/kb/query` |
| 2 | 工具代理（允许列表） | ✅ | `aiplat_tool_execute` → `POST …/tools/{name}/execute` |
| 3 | 会话摘要回写 Memory/SECI | 待接线 | 失败不阻断本地对话 |
| 4 | 审批门 ApprovalGate | 待接线 | 高风险动作等待平台 |

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=http://127.0.0.1:8003   # or http://host:8000/api
export AIPLAT_TENANT_TOKEN=<bearer>
# KB only by default; add tools:
export AIPLAT_ENTERPRISE_TOOLS=calculator
# optional: export AIPLAT_CORE_URL=http://127.0.0.1:8002

pi -e .
# /aiplat-status          → enterprise_hybrid / enterprise_tools
# /aiplat-enterprise      → KB reconnect status
# tools: aiplat_kb_retrieve | aiplat_tool_execute
```

Offline gates:

```bash
node packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
```

## 非目标

- 在 Pi 内重实现 PolicyGate / Memory / SECI
- 无允许列表时开放任意平台工具
- 把「厚运行时私有化」写成默认交付（仅驻场例外）

## 与厂内实验的关系

混合回连属于 **厂外企业交付**，优先级高于 `FACTORY_IN_EXPERIMENT.md` 的 ReActLoop 换心。
