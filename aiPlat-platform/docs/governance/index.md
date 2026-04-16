# governance 模块（Platform Layer 2）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 1. 定位与职责

`governance` 提供平台层的治理能力（策略与对外契约），典型包括：

- 限流/配额联动（与 `billing` 协作）
- 熔断/重试/超时策略（与 `gateway` 协作）
- 审计日志：关键操作留痕（与 `auth` 协作）
- 风险控制：敏感操作二次确认（UI/流程层配合）

## 2. 边界

- 具体指标采集与告警执行在 `aiPlat-management`
- 具体资源层面的实现细节在 `aiPlat-infra`
- governance 在 platform 层更偏“策略控制面”

## 3. 相关文档

- [平台层文档索引](../index.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)
- [管理平面（aiPlat-management）](../../../aiPlat-management/docs/index.md)

