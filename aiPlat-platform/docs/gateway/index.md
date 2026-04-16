# gateway 模块（Platform Layer 2：API Gateway）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 重要说明：区分两类网关

系统存在两类“网关”，名称相同但职责不同：

- **API Gateway（platform / Layer 2）**：认证、限流、路由分发、负载均衡、审计
- **Message Gateway（app / Layer 3）**：多渠道接入（Telegram/Slack/WebChat）、协议转换、消息格式统一

本文档描述的是 **API Gateway（platform）**。

## 1. 定位与职责

- API 路由与转发（REST/GraphQL）
- 统一认证授权入口（对接 `auth`）
- 限流、熔断、重试、超时
- 灰度/版本路由（如适用）
- 访问日志与审计（对接 `governance`）

## 2. 边界

- 不处理业务编排与执行（Agent Loop / Skill 执行在 `aiPlat-core`）
- 不做渠道适配（渠道接入在 `aiPlat-app/channels`）

## 3. 相关文档

- [平台层文档索引](../index.md)
- [平台层开发规范](../guides/DEVELOPMENT.md)
- [应用层文档索引（Message Gateway）](../../../aiPlat-app/docs/index.md)

