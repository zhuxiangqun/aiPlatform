# Gateway 多入口层（多渠道）方案与现状

本文用于对齐 OpenClaw/Hermes 式“可选 Gateway 入口层”的落地方式：将外部渠道（Slack/Telegram/WhatsApp/Webhook…）统一收敛到 aiPlat 的 Harness 执行入口，并复用既有 **policy / approval / run_events / audit / DLQ** 能力。

> 结论：aiPlat-core 已具备 Gateway MVP（HTTP 统一入口 + Slack 适配 + pairing/token/dedup/DLQ）。下一步主要是**补齐更多渠道适配器**与**交付（delivery）侧 connector 抽象**，而不是重新设计核心执行链路。

---

## 1. 现状（已实现的 Gateway MVP）

### 1.1 统一执行入口

- `POST /gateway/execute`
  - 入参：`GatewayExecuteRequest`（`core/schemas.py`）
    - `channel`：渠道名（如 `slack` / `telegram` / `webhook`）
    - `kind`：`agent|skill|tool|graph`
    - `target_id`：目标（agent_id / skill_name / tool_name / graph_id）
    - `user_id/session_id`：可选；缺省时支持通过 pairing 解析
    - `channel_user_id`：外部用户标识（用于 pairing）
    - `tenant_id`：可选
    - `payload/options`：原样透传到 Harness
  - 行为要点（`core/server.py`）：
    - 将 `channel/tenant/channel_user_id/request_id` 注入 `payload.context` 用于可观测与审计
    - 可选 token 鉴权：`AIPLAT_GATEWAY_REQUIRE_AUTH=true`
    - 支持 request_id 幂等去重：复用 ExecutionStore 映射（避免平台重试造成重复执行）
    - 复用 Harness 执行：保证 policy/approval/trace/run_events 一致

### 1.2 Slack 适配与通用 Webhook

服务端已提供 Slack 相关入口（`core/server.py`）：
- `POST /gateway/slack/command`
- `POST /gateway/slack/events`

以及更通用的 webhook 消息入口：
- `POST /gateway/webhook/message`

这些入口的职责应保持“薄”：**将外部协议转换为 GatewayExecuteRequest** 并调用 `/gateway/execute`（或同等内部函数）。

### 1.3 Pairing / Token / DLQ

ExecutionStore 已包含 Gateway 基础表（`core/services/execution_store.py`）：
- `gateway_pairings`：`(channel, channel_user_id) -> (tenant_id, user_id, session_id)`
- `gateway_tokens`：用于网关鉴权（token 的 sha256 存储）
- `connector_delivery_dlq` / `job_delivery_dlq`：用于交付失败的 DLQ（重试/查看/清理）

服务端暴露了管理 API（`core/server.py`）：
- Pairings：`GET/POST/DELETE /gateway/pairings`
- Tokens：`GET/POST/DELETE /gateway/tokens...`
- DLQ：`GET/POST/DELETE /gateway/dlq...`

---

## 2. 目标（吸收 OpenClaw/Hermes 的“多入口”价值点）

1. **多渠道统一入口**：不同渠道只做协议适配，核心执行链路不分叉。
2. **统一治理**：所有渠道都走同一套 policy/approval/audit/run_events。
3. **可靠交付**：渠道回包失败可入 DLQ、可重试、可观察。
4. **幂等与去重**：平台重试/事件重复投递不会重复执行。

---

## 3. 推荐的扩展接口（Adapter / Delivery）

### 3.1 Channel Adapter（入站）

每个渠道适配器只做三件事：
1. 校验签名/鉴权（Slack signing secret、Telegram secret token、WhatsApp webhook verify 等）
2. 抽取 `channel_user_id` / `tenant_id` / `request_id` / 文本消息
3. 组装 `GatewayExecuteRequest` 并调用 `/gateway/execute`

建议统一一个内部结构（伪代码）：

```python
def parse_inbound(request) -> GatewayExecuteRequest:
    return GatewayExecuteRequest(
        channel="telegram",
        kind="agent",
        target_id="default",
        channel_user_id=...,
        tenant_id=...,
        payload={"input": {"text": ...}, "context": {"request_id": ...}},
    )
```

### 3.2 Connector Delivery（出站）

不同渠道对“回复”可能是：
- webhook response（同步）
- API sendMessage（异步）
- 多段消息/附件/线程（Slack thread、Telegram reply_to_message_id）

建议逐步收敛为：
1. 执行阶段产出标准化 `delivery_intent`（要发给谁、发什么、是否 thread）
2. 由 connector 层负责实际发送；失败入 `connector_delivery_dlq`

aiPlat 已具备 connector DLQ 表结构，下一步是补齐：
- connector 抽象接口（send / render / chunk）
- 各渠道 connector 实现（slack/telegram/whatsapp）

---

## 4. 安全与治理建议（默认最小权限）

1. **强制鉴权（推荐）**
   - 生产启用：`AIPLAT_GATEWAY_REQUIRE_AUTH=true`
   - 每个 tenant 使用独立 token（`gateway_tokens`）
2. **Pairing 约束**
   - 仅允许在已 pairing 的 `channel_user_id` 上执行敏感工具
   - 将 `channel_user_id` 写入 run_events/audit，便于追溯
3. **渠道级限流**
   - 按 `(tenant_id, channel, channel_user_id)` 做限流（可先在 API 网关层做）
4. **policy/approval 复用**
   - Gateway 入口不得绕过 PolicyGate/ApprovalGate

---

## 5. 最小落地清单（从“已有 MVP”到“多渠道可用”）

### P0（1-2 天）
- [ ] Telegram inbound adapter：`/gateway/telegram/webhook`
- [ ] Telegram delivery connector：sendMessage + 入 `connector_delivery_dlq`
- [ ] 统一 message -> GatewayExecuteRequest 的转换与单测（request_id、pairing、tenant 注入）

### P1（2-4 天）
- [ ] WhatsApp（推荐走 Twilio）inbound/outbound connector
- [ ] 支持 rich message（markdown/blocks）渲染与分片（长消息拆分）
- [ ] 渠道级 retry/backoff 策略与 DLQ 批量重试

### P2（可选）
- [ ] 多 workspace / 多 tenant 的 routing 策略（按 token / header / pairing）
- [ ] 对接企业 IM（飞书/企微）适配器

---

## 6. 验收要点（建议）

1. 同一 `request_id` 重放不会重复执行（返回同一 run_id）
2. pairing 缺失时仍可执行（若允许），但审计中能看到 channel_user_id
3. 启用 auth 时，无 token 直接 401/403
4. 出站失败必入 DLQ，且可通过 API 重试成功

