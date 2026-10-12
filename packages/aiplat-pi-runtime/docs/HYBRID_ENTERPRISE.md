# Pi + aiPlat 企业级混合（目标态）

> 产品锁定：默认 **Pi-only**；企业级 = **Pi 壳 + aiPlat 回连**。  
> 本文件描述目标态；**当前未接线**（勿标 CAPABILITIES 已接线）。

## 原则

1. 用户侧始终以 Pi（或薄 HTTP）为对话宿主——不要求用户默认安装全栈 aiPlat。
2. 包内能力（SOP / skills / handler）在离线/断连时仍可用。
3. 企业能力不复制进 Pi 进程，经认证 API 调用平台（PolicyGate 仍在平台侧执行一次）。

## 建议环境变量（草案）

| 变量 | 含义 |
|------|------|
| `AIPLAT_PLATFORM_URL` | 平台基址（如 `https://tenant.example/api`） |
| `AIPLAT_TENANT_TOKEN` / API Key | 身份注入；权限判断在平台 PolicyGate |
| `AIPLAT_ENTERPRISE=1` | 启用回连；未设则严格 Pi-only |

## 建议首批回连能力（成本阶梯从低到高）

1. **只读知识检索** — 对话前/中检索片段注入（对应平台 KB）
2. **工具代理** — 敏感工具经平台 `sys_tool_call` 等价 HTTP，带审计
3. **会话摘要回写** — 可选 Memory/SECI 入口（失败不阻断本地对话）
4. **审批门** — 高风险动作等待平台 ApprovalGate

## 非目标

- 在 Pi 内重实现 PolicyGate / Memory / SECI
- 把「厚运行时私有化」写成默认交付（仅驻场例外）

## 与厂内实验的关系

混合回连属于 **厂外企业交付**，优先级高于 `FACTORY_IN_EXPERIMENT.md` 的 ReActLoop 换心。
