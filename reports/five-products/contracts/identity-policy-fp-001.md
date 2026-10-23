# 契约草案 id-policy-fp-001

| 项 | 内容 |
|----|------|
| 状态 | 启用 · 草案 |
| 字段 | tenant_id, actor_id\|service_id, scopes[], audience, request_id, trace_id, product_id, environment_id, authn_source, expires_at |
| 生产者 | aiPlat（require_auth / _resolve_identity / PolicyGate） |
| 消费者 | FDE API、Bundle 发布面、目标服务校验 |
| 错误 | 未认证/伪造 → 401/403；过期 → 拒绝 |
| 失联 | 控制面不可达 → 高风险副作用 fail-closed；低风险离线见 Pi 策略 |
| 验收 | 伪造身份失败；Pi 客户端 gate 不能放行服务端已拒 |
| owner | 架构临时 R |
