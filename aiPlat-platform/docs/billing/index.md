# billing 模块（Platform Layer 2）

> 本文档为**骨架**：用于补齐文档引用与边界说明，后续可按实现细节逐步完善。

## 1. 定位与职责

`billing` 负责平台层的计费/计量/配额策略（策略与对外契约），典型能力：

- 租户配额（GPU/请求数/Token/存储）
- 计量维度：请求量、成功率、Token 消耗、调用时长
- 费用模型：按量/包年包月（视业务需要）
- 与审计/治理联动：超额告警、限流策略

## 2. 边界

- 指标采集与底层计量数据来源在 `aiPlat-infra`/`aiPlat-management`
- platform 负责“对外策略与权限”，不直接采集底层指标

## 3. 相关文档

- [平台层文档索引](../index.md)
- [租户管理（tenants）](../tenants/index.md)
- [管理平面（aiPlat-management）](../../../aiPlat-management/docs/index.md)

