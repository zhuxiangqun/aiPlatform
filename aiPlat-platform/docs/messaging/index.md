# messaging 模块（Platform Layer 2：消息通知）

## 定位

`messaging/` 提供面向用户的实时通知和消息推送。不同于 app 层的 Message Gateway（多渠道适配），platform 层的 messaging 负责通知的触发和分发。

## 已实现能力

| 能力 | 代码位置 | 状态 |
|------|---------|:--:|
| 飞书 Webhook 通知 | core/harness/infrastructure/gateway/messaging.py | ✅ |
| 企业微信 Webhook 通知 | 同上 | ✅ |
| Slack Bot Token 通知 | 同上 | ✅ |
| Pipeline 失败自动广播 | pipeline_engine.py → _notify_pipeline_failure() | ✅ |
| Email 通知 (SMTP) | core/harness/infrastructure/ | ✅ |

## 环境变量

| 变量 | 说明 |
|------|------|
| `AIPLAT_FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |
| `AIPLAT_WECOM_WEBHOOK` | 企业微信机器人 Webhook URL |
| `AIPLAT_SLACK_BOT_TOKEN` | Slack Bot Token (xoxb-...) |
| `AIPLAT_SMTP_*` | SMTP 邮件配置 |

## 边界

- 不处理渠道适配（渠道在 app 层）
- 不管理消息模板（模板在 core 层）
- 只负责触发和分发，不做消息持久化
