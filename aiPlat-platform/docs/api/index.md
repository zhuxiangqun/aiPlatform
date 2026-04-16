# api 模块（Platform Layer 2）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 1. 定位与职责

`api` 模块位于 **aiPlat-platform（Layer 2）**，对外提供平台级 REST/GraphQL API，承担“对外契约层”职责：

- 对外暴露端点（REST/GraphQL）
- 认证与授权接入（依赖 `auth` 模块）
- 请求校验、参数转换、响应规范化
- 统一错误码与错误格式
- 限流/熔断/审计等治理能力（可与 `gateway/governance` 协作）

## 2. 依赖与边界

- ✅ 允许依赖：`aiPlat-core`（通过门面/Facade 访问核心能力）
- ❌ 禁止依赖：`aiPlat-infra`（基础设施访问必须经由 core 间接完成）
- ❌ 禁止依赖：`aiPlat-app`

> 核心业务逻辑（Agent Loop、Skill/Memory/Knowledge 具体处理）必须在 **aiPlat-core**。

## 3. 产出物

- OpenAPI/Swagger（REST）
- GraphQL schema（如启用）
- API 版本策略（如 `/api/v1`）

## 4. 相关文档

- [平台层文档索引](../index.md)
- [平台层开发规范](../guides/DEVELOPMENT.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)
- [核心层文档索引](../../../aiPlat-core/docs/index.md)

