# auth 模块（Platform Layer 2）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 1. 定位与职责

`auth` 模块负责平台层的认证授权能力，为所有对外 API 提供统一安全入口：

- 登录/会话（如适用）
- Token/JWT 校验与签发
- RBAC/ABAC 权限校验
- 多租户鉴权（与 `tenants` 协作）
- 审计日志（与 `governance` 协作）

## 2. 依赖与边界

- `auth` 是平台层公共能力，**应被 api/gateway 等模块复用**
- `auth` 不应包含 Agent/Skill 等业务逻辑；业务逻辑在 `aiPlat-core`

## 3. 相关文档

- [平台层文档索引](../index.md)
- [平台层开发规范](../guides/DEVELOPMENT.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)

