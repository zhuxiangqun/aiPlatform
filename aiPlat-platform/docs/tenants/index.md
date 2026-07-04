# tenants 模块（Platform Layer 2：多租户管理）

## 定位

platform 的 `tenants/` 模块提供多租户创建、隔离、配额管理。所有 API 调用均需携带 `tenant_id`，核心层（core）通过透传 headers 获取租户上下文。

## 已实现能力

| 能力 | 状态 |
|------|:--:|
| 租户 CRUD（创建/查询/更新/删除） | ✅ |
| tenant_id 注入到所有下游调用 | ✅ |
| 租户自助入驻门户（register → verify email → API key） | ✅ |
| 租户配额管理（tenant_quotas） | ✅ |
| 租户用量追踪（tokens/calls） | ✅ |

## 边界

- 租户数据隔离在 core 层执行（知识库、Wiki、GraphIndex 全部按 tenant_id/domain_id 隔离）
- platform 只管理租户元数据（名称、配额、状态），不存储租户业务数据
- 跨租户查询被 PolicyGate 在核心层阻断
