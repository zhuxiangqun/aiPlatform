# messaging 模块（Platform Layer 2）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 1. 定位与职责

`messaging` 提供平台层的消息/事件能力（面向业务系统的“平台抽象”）：

- 事件发布/订阅（对外契约）
- Topic/Queue 的逻辑抽象（不绑定具体中间件实现）
- 可靠性策略：重试、幂等、死信（策略层）

## 2. 与 infra 的关系

底层消息中间件（Kafka/RabbitMQ/Redis Streams 等）的具体实现属于 **aiPlat-infra (Layer 0)**。

平台层应当：

- 只定义“事件契约/Topic 命名/权限/租户隔离”
- 通过 core/infra 抽象间接落地到具体消息系统

## 3. 相关文档

- [平台层文档索引](../index.md)
- [基础设施层 messaging 文档](../../../aiPlat-infra/docs/messaging/index.md)

