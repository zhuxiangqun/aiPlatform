# AttributionSchema — Agent 效果归因协议

> 版本: 1.0 · 2026-07-17  
> 目的: 定义外部业务系统向 aiPlatform 回传 Agent 效果的标准化协议  
> 适用: 所有通过 aiPlatform 部署的 AI Agent 的客户侧集成

---

## 1. 会话追踪标识

客户在调用 Agent API 时，必须在请求中携带 `X-AiPlatform-Session-ID` header：

```http
POST /api/agent/chat HTTP/1.1
X-AiPlatform-Session-ID: sess_123abc
```

aiPlatform 在 Agent 的每次回复中都会返回此标识。客户系统需要将其与自身的业务会话关联存储。

---

## 2. 效果数据回传（后续实现）

> **接口预留，当前版本尚未上线。建议客户侧先做 Session-ID 关联存储，待接口上线后批量回传。**

```
POST /api/platform/attribution
Content-Type: application/json

{
  "session_id": "sess_123abc",          // 必填，aiPlatform 会话标识
  "external_session_id": "crm_deal_456", // 可选，客户侧业务会话标识
  "events": [
    {
      "timestamp": "2026-07-17T10:30:00Z",
      "event_type": "deal_won",           // deal_won | deal_lost | deal_pending | page_view | add_to_cart | booking_confirmed
      "deal_amount": 1299.00,             // 可选，成交金额（元）
      "deal_currency": "CNY",             // 可选，币种
      "conversion_stage": "purchase",      // 可选，转化阶段标识
      "metadata": {}                     // 可选，业务自定义字段
    }
  ]
}
```

---

## 3. 数据用途

回传的效果数据将用于：
- **Agent 效果评估**：计算转化率、客单价等业务指标
- **质量优化**：关联低转化率会话 → 分析 Agent 回复质量 → 自动改进
- **FDE 周报**：纳入周度复盘报告，供 FDE 与客户共同审查

---

## 4. 数据安全

- 效果数据按 `tenant_id` 严格隔离
- 不存储客户侧的个人身份信息（PII）
- 仅 `tenant` 管理员和 aiPlatform FDE 可见

---

## 5. 联系方式

如有技术问题，联系 aiPlatform FDE 团队。
