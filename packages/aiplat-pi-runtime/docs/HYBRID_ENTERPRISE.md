# Pi + aiPlat 企业级混合

> 产品锁定：默认 **Pi-only**；企业级 = **Pi 壳 + aiPlat 回连**。  
> **已接线**：只读 KB + 允许列表工具代理 + **原生工具门禁桥** + **会话摘要 Memory 回写**。审批门仍按阶梯推进。  
> **分层**：Pi = 执行/薄宿主；aiPlat = 治理/工厂。不是两套平权产品。

## 原则

1. 用户侧始终以 Pi（或薄 HTTP）为对话宿主——不要求用户默认安装全栈 aiPlat。
2. 包内能力（SOP / skills / handler）在离线/断连时仍可用。
3. 企业能力不复制进 Pi 进程，经认证 API 调用平台（PolicyGate 仍在平台/Core 侧执行一次）。
4. **能力重叠 ≠ 交付重复**：平台白皮书里的 Agent/工具/多模型不取消 Pi 交付；Pi 解决「产物怎么带走、怎么轻量跑」。
5. 对外入口：企业客户认 aiPlat（或本混合回连）；禁止叙事成「再装一套平行平台」。
6. **企业意图下原生副作用不得绕过平台门禁**：`AIPLAT_ENTERPRISE=1` 时默认拦截 bash/write/edit/powershell，迫使副作用走 `aiplat_tool_execute`。

## 环境变量

| 变量 | 含义 |
|------|------|
| `AIPLAT_PLATFORM_URL` | 平台基址（如 `https://tenant.example/api` 或 `:8003`） |
| `AIPLAT_CORE_URL` | 可选；工具执行基址。裸 `http://host:8002` 会自动补 `/api/core`；也可直接写 `…/api/core`。未设时从 PLATFORM_URL 推导（`:8003`→`:8002/api/core`，`…/api`→`…/api/core`） |
| `AIPLAT_TENANT_TOKEN` / API Key | 身份注入；权限判断在平台 PolicyGate / RBAC |
| `AIPLAT_ENTERPRISE=1` | 启用回连意图；未设则严格 Pi-only。**同时默认打开原生工具门禁**（无需 URL/token） |
| `AIPLAT_KB_COLLECTION_ID` | KB 集合（默认 `default`） |
| `AIPLAT_ENTERPRISE_TOOLS` | **工具允许列表**（逗号分隔）。空 = 工具代理关闭（仅 KB） |
| `AIPLAT_ENTERPRISE_ALLOW_NATIVE=1` | 信任运维逃生：关闭原生门禁（bash/write 等恢复） |
| `AIPLAT_ENTERPRISE_TOOL_GATE=0` | 仅关闭原生门禁，保留 KB/工具混合 |
| `AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST` | 额外放行原生工具（可覆盖默认 block，如 `bash`） |
| `AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST` | 额外拦截原生工具（如 `read`） |
| `AIPLAT_ENTERPRISE_MEMORY=1` | 启用会话摘要回写（须同时有 URL/token）；空=关闭 |
| `AIPLAT_ENTERPRISE_MEMORY_AUTO=0` | 仅关闭 `session_shutdown` 自动 flush；保留 `aiplat_memory_capture` 工具 |
| `AIPLAT_ENTERPRISE_SESSION_ID` | 可选；写入 capture 的 `session_id` |

## 回连能力阶梯

| # | 能力 | 状态 | 入口 |
|---|------|:----:|------|
| 1 | 只读知识检索 | ✅ | `aiplat_kb_retrieve` → `POST /platform/kb/query` |
| 2 | 工具代理（允许列表） | ✅ | `aiplat_tool_execute` → `POST …/tools/{name}/execute` |
| 3 | 原生工具门禁桥 | ✅ | `enterprise_tool_gate.ts`：`tool_call` block + `setActiveTools`；默认禁 bash/write/edit/powershell |
| 4 | 会话摘要回写 Memory | ✅ | `enterprise_memory.ts` → `POST /platform/memory/capture`；工具 + `session_shutdown` 软 flush；失败不阻断 |
| 5 | 审批门 ApprovalGate | 待接线 | 高风险动作等待平台 |

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=http://127.0.0.1:8003   # or http://host:8000/api
export AIPLAT_TENANT_TOKEN=<bearer>
# KB only by default; add tools:
export AIPLAT_ENTERPRISE_TOOLS=calculator
# optional: export AIPLAT_CORE_URL=http://127.0.0.1:8002   # auto → …/api/core
# native gate is ON by default (bash/write/edit blocked). Escape:
# export AIPLAT_ENTERPRISE_ALLOW_NATIVE=1
# export AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST=bash
# memory writeback (opt-in):
export AIPLAT_ENTERPRISE_MEMORY=1
# export AIPLAT_ENTERPRISE_MEMORY_AUTO=0   # keep tool, skip session_shutdown flush

pi -e .
# /aiplat-status          → enterprise_hybrid / tools / tool_gate / memory
# /aiplat-enterprise      → KB reconnect status
# /aiplat-memory          → memory writeback status
# tools: aiplat_kb_retrieve | aiplat_tool_execute | aiplat_memory_capture
```

Offline gates:

```bash
node packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_memory_smoke.mjs
```

## 非目标

- 在 Pi 内重实现 PolicyGate / MemoryManager / SECI（门禁桥只 **拦截/引导**；Memory 桥只 **投递** capture API）
- 无允许列表时开放任意平台工具
- 把「厚运行时私有化」写成默认交付（仅驻场例外）

## 与厂内实验的关系

混合回连属于 **厂外企业交付**，优先级高于 `FACTORY_IN_EXPERIMENT.md` 的 ReActLoop 换心。
