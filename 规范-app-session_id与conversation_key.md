---
title: 规范：aiPlat-app Session ID 与 Conversation Key（企业平台默认）
date: 2026-04-18
scope: aiPlat-app（channels/sessions 权威）
status: draft
---

## 1. 目标（为什么要规定）

企业多渠道场景最怕两件事：
1) **串话**：把不同 thread/ticket 的上下文混到一个 session；  
2) **越权/泄漏**：同一用户参与多个工单或群聊线程，若按 user 聚合会把敏感上下文混在一起。

因此 session 的“自然边界”应优先绑定 **业务上下文容器**，而不是“用户”。

---

## 2. 最佳实践：conversation_key 选择优先级

推荐优先级（从高到低）：

1) `ticket_id`（工单/Case/Issue）
2) `thread_id`（Slack/Teams thread、邮件 thread、论坛/IM thread）
3) `channel_user_id`（私聊/无 thread 的平台）

统一抽象字段：
- `conversation_key_type`: `ticket|thread|user`
- `conversation_key`: 对应的外部稳定键

建议把“自然键”写成一个可唯一索引的复合 key：

```
conversation_key = "{channel}:{conversation_key_type}:{external_id}"
```

并且 **必须带 tenant 维度**（不同 tenant 可以拥有相同 external_id）：

```
unique(tenant_id, conversation_key)
```

---

## 3. session_id 的生成与稳定性

推荐做法：
- `session_id`：内部 ID，格式建议 `sess_<ulid>`
- `conversation_key`：外部稳定键，用于幂等创建与定位 session

行为约定：
- 收到消息时，先用 `(tenant_id, conversation_key)` 查 session
  - 若存在：复用 session_id
  - 若不存在：创建新 session_id，并写入映射表

---

## 4. Slack/邮件/工单示例

### Slack
- thread 内消息：用 `thread_ts` 作为 thread_id（优先）
- 非 thread（普通频道消息）：可用 `channel_id + message_ts` 作为 thread_id（或按“频道会话”策略显式配置）
- DM：用 channel_user_id

### 邮件
- 用 `Message-ID` / `Thread-Index` / `In-Reply-To` 计算 thread_id（优先）

### 工单系统
- ticket_id/issue_id/case_id 直接作为 ticket_id（最高优先）

---

## 5. 与执行（core）关联方式

app 负责把 session_id 传给 platform（再转发给 core），用于：
- per-session lane 串行化（app 层）
- memory 写入与检索（core 层，但以 session_id 作为 key）
- 审计与回放（run_id ↔ session_id）

