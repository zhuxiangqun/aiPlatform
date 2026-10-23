# 契约草案 runtime-fp-001

| 项 | 内容 |
|----|------|
| 状态 | 启用 · 草案 |
| 字段 | instance_id, deploy_version, config_version, health, heartbeat_at, event_types[], offline_until, command_authz |
| 生产者 | Pi Thin |
| 消费者 | 诊断（引用）、运维 |
| 离线 | 必须同时满足 `pi-thin-offline.md` |
| 错误 | 过期/超 TTL/denied_ops → 停止或拒绝 |
| owner | Pi 临时 R |
