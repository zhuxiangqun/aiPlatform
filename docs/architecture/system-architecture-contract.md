# 系统整体架构规范（System Architecture Contract）

> 适用范围：aiPlatform 全系统（management / app / platform / core / infra）  
> 目标：提供**系统级**的分层职责、依赖方向、跨层契约与边界约束。  
> 说明：各层的细化规范请参考各层 `docs/`，本文件只定义跨层“硬约束”和最小必要契约。

---

## 1. 系统分层与职责（MUST）

aiPlatform 采用“业务四层架构 + 独立管理系统”：

- **Management（管理平面）**：`aiPlat-management`  
  横切四层业务架构，提供运维、诊断、配置、告警、审计视图。
- **Layer 3（应用层）**：`aiPlat-app`  
  面向用户的应用入口（消息网关、多渠道接入、CLI、Workbench 等）。
- **Layer 2（平台服务层）**：`aiPlat-platform`  
  对外 API 网关与平台能力（认证鉴权、多租户、限流熔断、路由、审计等）。
- **Layer 1（AI 核心层）**：`aiPlat-core`  
  AI 运行时与核心能力（Harness/Runtime、Agents、Skills、Memory、ExecutionStore、Tools/MCP 等）。
- **Layer 0（基础设施层）**：`aiPlat-infra`  
  提供数据库、配置、向量存储、LLM 客户端、监控等基础设施，**完全独立**。

---

## 2. 依赖方向与禁止依赖（MUST）

### 2.1 静态依赖（编译时/设计时）

**允许依赖方向（单向依赖）**：

```
aiPlat-app → aiPlat-platform → aiPlat-core → aiPlat-infra
```

**禁止依赖（MUST NOT）**：
- `aiPlat-app` 直接依赖 `aiPlat-core`（必须经由 `aiPlat-platform`）
- `aiPlat-app` 直接依赖 `aiPlat-infra`
- `aiPlat-platform` 直接依赖 `aiPlat-infra`（必须经由 `aiPlat-core`）
- 任何下层依赖上层（infra/core/platform/app）

### 2.2 运行时调用链（请求处理链）

典型链路：

```
外部渠道/用户 → Layer 3（app） → Layer 2（platform） → Layer 1（core） → Layer 0（infra）
```

> 注：management 为横切管理平面，不参与业务调用链，但可调用各层“管理接口/观测接口”。

---

## 3. 跨层身份、权限与多租户透传（MUST）

### 3.1 单一权威原则

- `aiPlat-platform` 是**唯一权威**的身份与权限解析/签发方（JWT/API key → tenant/actor/scopes）。
- 下游（app/core）**只消费** platform 注入的身份信息，**不得推断**或自行扩权。

### 3.2 标准透传 Headers（platform → app/core）

platform 在调用下游服务时 **MUST** 注入/透传：

- `X-AIPLAT-REQUEST-ID`：请求唯一标识（用于审计、幂等、追踪）
- `X-AIPLAT-TENANT-ID`：租户 ID
- `X-AIPLAT-ACTOR-ID`：调用方 ID（用户或服务主体）
- `X-AIPLAT-SCOPES`：权限 scopes（推荐）
- `X-AIPLAT-ACTOR-ROLE`：可选（以 scopes 为准）

详见：[`规范-platform-鉴权与身份透传.md`](../../规范-platform-鉴权与身份透传.md)

---

## 4. 跨层执行标识与可观测契约（MUST）

### 4.1 request_id

- `request_id` 由 platform 生成并透传（见上文 `X-AIPLAT-REQUEST-ID`）。
- 所有层的日志/审计 **MUST** 打印（脱敏后）`request_id + tenant_id + actor_id`。

### 4.2 run_id / trace_id

- AI 执行（agent/skill/tool）由 `aiPlat-core` 运行时生成 `run_id`，并可输出 `trace_id`。
- management/UI 展示与排障时应以 `run_id/trace_id` 作为核心定位信息。

详见：[`规范-core-run_id-trace_id-request_id.md`](../../规范-core-run_id-trace_id-request_id.md)

---

## 5. 错误透传与网关行为（MUST）

- platform 作为网关层，对下游（core/app）的非 2xx 响应，**MUST 透传可诊断信息**（至少包含 `detail` 或等价字段）。  
- 禁止仅返回“500 Internal Server Error”而吞掉上游错误上下文（除非涉及敏感信息，需要脱敏/替换）。

---

## 6. 层内细化规范（References）

系统整体规范只定义跨层契约；各层内部规范请参考：

- `aiPlat-core`（Layer 1）
  - 核心能力层架构与执行流程（As‑Is）：[`docs/architecture/core-layer1-latest.md`](core-layer1-latest.md)
  - core 内部边界契约（harness/policy/agent/skill）：`aiPlat-core/docs/contracts/01-architecture-contract.md`
- `aiPlat-platform`（Layer 2）：`aiPlat-platform/docs/index.md`（Auth/Tenants/Gateway 等）
- `aiPlat-app`（Layer 3）：`aiPlat-app/docs/index.md`
- `aiPlat-infra`（Layer 0）：`aiPlat-infra/docs/index.md`
- `aiPlat-management`（Management）：`aiPlat-management/docs/index.md`

