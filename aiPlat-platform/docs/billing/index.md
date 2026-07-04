# billing 模块（Platform Layer 2：计费与用量管理）

## 定位

`billing/` 提供租户级别的用量追踪和计费能力。基于 execution_store 中的 token/call 记录聚合每租户的用量数据。

## 已实现能力

| 能力 | 状态 |
|------|:--:|
| 租户用量追踪（token 数、调用次数） | ✅ |
| Per-tenant 计费面板 | ✅ |
| 用量导出 CSV（ops/export/tenant_usage.csv） | ✅ |
| 配额超限告警 | ✅ |

## 边界

- 计费数据来自 core 层的 execution_store（通过 sys_llm_generate 每次调用的 usage 记录）
- billing 只做聚合和展示，不做实时扣费
- 实际支付对接未实现（当前为用量追踪模式）
