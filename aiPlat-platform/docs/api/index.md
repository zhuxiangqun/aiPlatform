# api 模块（Platform Layer 2：REST API 网关）

## 定位

`api/` 是 aiPlat 平台的 REST API 入口。所有外部请求通过此模块进入平台，经认证、限流后路由到下游服务。

## 已实现能力

| 能力 | 状态 |
|------|:--:|
| REST API 路由注册（4 层全覆盖: core/infra/platform/app） | ✅ |
| 统一请求/响应格式（`response_model=Dict[str, Any]`） | ✅ |
| GraphQL 查询端点 | ✅ |
| WebSocket 实时通信 | ✅ |
| 健康检查（`/health`, `/core/health`） | ✅ |
| 错误透传（下游错误信息保全） | ✅ |
| API 版本管理 | ✅ |

## 边界

- 只做路由和转发，不做业务逻辑
- 所有业务逻辑调用通过 CoreFacade 接口
- 不直接访问 harness 内部模块
- 认证/限流由中间件处理，不在路由中内嵌
