---
purpose: aiPlat-platform 项目级 AI 编程规约
scope: platform (Layer 2)
language: zh-CN
---

# aiPlat-platform AI 编程规约（平台服务层）

本文件用于约束 AI Agent 在 aiPlat-platform 仓库内的行为。

---

## 0. 优先级（从高到低）
1. 正确性与可验证性（API 契约不破、测试通过）
2. 最小改动面（Surgical Changes）
3. 简单性（Simplicity First）
4. 一致性（API 规范、错误处理、认证模式）

---

## 1) Think Before Coding：不确定先问
- 涉及 API 契约变更（路径、请求体、响应体、错误码）
- 涉及认证/授权逻辑（JWT 解析、scope 校验、租户隔离）
- 涉及新增跨层调用（是否应该走 core facade）
- 涉及限流/熔断/负载均衡策略

### 1.1 代码优先于设计文档（强制）
设计文档（`docs/`）描述目标状态，代码才是当前真实状态。两者冲突时以代码为准，设计文档标注"已过期/已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止仅凭记忆或上次审计的印象做判断，每次结论必须附带代码搜索证据（命中文件路径+行号）。

---

## 2) Simplicity First：最小实现
- 不引入未被要求的认证方式或计费模式
- API 设计遵循现有 RESTful 规范，不另起风格
- 新增 API 复用已有中间件（auth、rate-limit、audit）

---

## 3) Surgical Changes：手术式改动
- 只修改与需求直接相关的文件
- 改 API 契约时同步更新文档和 SDK（如有）
- 不改无关的中间件、路由、配置

---

## 4) Goal-Driven Execution：验收闭环
- 语法：`python -m py_compile <修改的文件>`
- API 测试：curl / pytest 验证端点行为
- 改认证/授权：必须验证权限边界不被突破

---

## 5) 项目特定：platform 层边界与契约（必须遵守）

### 5.1 层定位（来自 `docs/index.md` 和 `../../docs/index.md`）

aiPlat-platform 是 **Layer 2（平台服务层）**，对外暴露 API，提供平台级服务。

- **向上提供**：REST API、GraphQL API、WebSocket API
- **向下依赖**：只能依赖 `aiPlat-core` 的 CoreFacade（唯一入口）。所有 `from core.apps.*` 和 `from core.harness.*` 导入已全部消除（2026-05）。
- **禁止直接依赖** `aiPlat-infra`
- **禁止包含** AI 核心逻辑（Agent 执行、Skill 编排等）

### 5.2 单一权威：身份与权限

platform 是**唯一权威**的身份与权限解析/签发方。

- JWT / API key → tenant / actor / scopes 的解析只在 platform 层发生
- 下游（core/app）只消费 platform 注入的身份信息，不得推断或自行扩权
- 权限配置数据（`ROUTE_PERMISSIONS`、`SIDEBAR_MENUS`、`METHOD_RESTRICTIONS`、`SystemRole`）必须在 platform 层定义
- 调用下游服务时 MUST 注入标准透传 headers：
  - `X-AIPLAT-REQUEST-ID`
  - `X-AIPLAT-TENANT-ID`
  - `X-AIPLAT-ACTOR-ID`
  - `X-AIPLAT-SCOPES`

### 5.3 错误透传

platform 作为网关层，对下游非 2xx 响应 MUST 透传可诊断信息（至少包含 `detail` 或等价字段）。禁止仅返回 "500 Internal Server Error" 而吞掉上游错误上下文（敏感信息需脱敏）。

### 5.4 API 网关职责

- 请求路由与转发
- 认证接入与身份注入
- 限流与熔断
- 负载均衡
- 请求日志与审计追踪

网关应该是无状态的，支持水平扩展。

### 5.5 依赖方向

```
app → platform (通过 REST/GraphQL API)
platform → core (通过 CoreFacade，唯一入口)
platform → infra (禁止，应通过 core)
```

**设计文档依据**：
- `../../docs/index.md` §设计原则、§Layer 2 边界规则、§依赖规则
- `../../docs/architecture/system-architecture-contract.md` §依赖方向、§跨层身份透传、§错误透传

---

## 6) 输出要求
- 改动摘要（改了哪些文件，为什么）
- 验证结果（API 测试是否通过）
- 改 API 契约时：说明变更内容和兼容性影响


## 7) 近期架构变更（2026-05）

### Wiki 自动策展
- `_auto_wiki_update()` 已改为通过 `CoreFacade.wiki_auto_update()` 调用
- 禁止直接 `from core.harness.knowledge.wiki_engine import ...`
- 所有 Wiki 操作必须通过 CoreFacade facade 方法

### MCP 归属
- MCP（Model Context Protocol）已全部归入 aiPlat-core
- platform 不直接管理 MCP 传输或客户端实现
