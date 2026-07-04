# aiPlat-platform 核心能力概述

> 本文档是 aiPlat-platform (Layer 2) 的核心能力清单，面向需要了解平台层功能的开发者。

## 一、已实现的生产级能力

### 1.1 API 网关 (api/)

全量 REST API 注册中心，负责路由分发、请求转发、统一错误处理。

**已实现**：
- 全部 4 层 (core/infra/platform/app) 的 API 路由注册
- 统一的请求/响应格式（`response_model=Dict[str, Any]`）
- 与 CoreFacade 的单向依赖（不直接调用 harness/execution）
- 健康检查端点

### 1.2 身份认证与授权 (auth/)

平台层的单一权威身份解析方。

**已实现**：
- JWT / API Key → tenant_id + actor_id + scopes 解析
- 标准透传 headers: `X-AIPLAT-REQUEST-ID`, `X-AIPLAT-TENANT-ID`, `X-AIPLAT-ACTOR-ID`, `X-AIPLAT-SCOPES`
- SSO/OIDC 集成 (Keycloak / Azure AD / Okta)
- 用户注册 → 邮箱验证 → API Key 发放完整流程

### 1.3 多租户 (tenants/)

**已实现**：
- 租户创建 / 查询 / 更新 / 删除
- 租户隔离 (tenant_id 注入到所有下游调用)
- 租户自助入驻门户
- 租户配额管理 (`tenant_quotas`)

### 1.4 限流与熔断 (governance/)

**已实现**：
- RateLimit 滑动窗口限流
- CircuitBreaker 熔断器
- Quota 配额管理
- 访问日志与审计追踪

### 1.5 消息通知 (messaging/)

**已实现** (2026-07-04)：
- 飞书 (Feishu) Webhook 集成
- 企业微信 (WeCom) Webhook 集成
- Slack Bot Token 集成
- Pipeline 失败自动广播通知
- 统一 `MessagingGateway` 抽象层 (位于 `core/harness/infrastructure/gateway/`)

### 1.6 注册中心 (registry/)

**已实现**：
- Skill 注册 / 发现 / 版本管理
- Agent 注册 / 启用 / 禁用
- 工具注册
- 技能市场发布工作流

### 1.7 计费 (billing/)

**已实现**：
- 租户用量追踪 (token 数、调用次数)
- 计费面板 (per-tenant)
- 用量导出 CSV

## 二、设计原则

1. **单一入口**：所有外部调用通过 `CoreFacade`，不直接访问 harness 内部
2. **信任下游**：platform 只做身份注入，不做权限判断（权限判断在 PolicyGate）
3. **无状态**：API gateway 无状态，支持水平扩展
4. **错误透传**：下游非 2xx 响应必须透传可诊断信息

## 三、相关文档

- [平台层规约 (CLAUDE.md)](../../CLAUDE.md)
- [系统级架构契约](../../../docs/architecture/system-architecture-contract.md)
- [文档系统治理框架](../../../docs/DOCUMENT_SYSTEM.md)
