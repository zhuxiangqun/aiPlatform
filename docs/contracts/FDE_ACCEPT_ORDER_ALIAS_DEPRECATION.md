# FDE — `accept_order` legacy alias deprecation (D3 close-out)

| 字段 | 值 |
|------|-----|
| 版本 | v1.0 |
| 日期 | 2026-09-15 |
| 状态 | **已废弃** |
| 关联 | `FDE_DECISION_RECORD.md` D3 |

## 决议执行

- **Canonical id：** `customer_action:lock-service:accept_order`
- **Legacy alias `accept_order`：** 自本版本起 **不再注册**（`aliases: []`）
- **Handler 符号** `builtin_handlers.accept_order`：**保留**（实现函数名，非 action id）

## 调用面清理

| 入口 | 要求 |
|------|------|
| Registry.execute / get | 使用 canonical id |
| UI ActionCards | 由 Registry 列表驱动，不硬编码 alias |
| `scripts/bench_accept_order_p95.py` | 仅断言 canonical |
| 单测 | 不再 `reg.get("accept_order")` |

## 迁移

旧客户端若仍传 `accept_order`，将得到 `not registered` / handler missing。请改为 canonical id。
