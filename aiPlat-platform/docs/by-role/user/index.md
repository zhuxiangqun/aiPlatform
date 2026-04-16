# 📖 平台层用户指南

> aiPlat-platform - 平台服务使用指南

---

## 🎯 本指南适合谁？

本指南适合需要使用平台服务的用户：
- **应用开发者**：通过 API 调用平台能力
- **系统集成人员**：集成平台到现有系统
- **租户管理员**：管理租户和用户
- **普通用户**：使用平台功能

---

## 🚀 快速开始

### 获取 API 访问令牌

**步骤 1：登录获取令牌**
```bash
curl -X POST https://api.example.com/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your-email@example.com",
    "password": "your-password"
  }'
```

返回：
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**步骤 2：使用令牌访问 API**
```bash
curl -X GET https://api.example.com/api/v1/agents \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

---

### 常用 API 端点

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 认证 | POST | `/api/v1/auth/token` | 获取访问令牌 |
| 刷新令牌 | POST | `/api/v1/auth/refresh` | 刷新访问令牌 |
| Agent 列表 | GET | `/api/v1/agents` | 获取所有 Agent |
| Agent 执行 | POST | `/api/v1/agents/{id}/execute` | 执行 Agent |
| Skill 列表 | GET | `/api/v1/skills` | 获取所有 Skill |
| 知识库列表 | GET | `/api/v1/knowledge` | 获取所有知识库 |
| 用户信息 | GET | `/api/v1/users/me` | 获取当前用户信息 |

---

## 📖 核心功能使用

### 一、用户认证

#### 登录认证

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user@example.com",
    "password": "password123"
  }'
```

**响应示例**：
```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 刷新令牌

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJ0eXAi..."
  }'
```

#### 用户信息

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/users/me \
  -H "Authorization: Bearer <token>"
```

**响应示例**：
```json
{
  "id": "user-123",
  "email": "user@example.com",
  "name": "张三",
  "role": "developer",
  "tenant_id": "tenant-456",
  "created_at": "2026-04-09T10:00:00Z"
}
```

---

### 二、Agent 管理

#### 获取 Agent 列表

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/agents \
  -H "Authorization: Bearer <token>"
```

**响应示例**：
```json
{
  "agents": [
    {
      "id": "agent-001",
      "name": "customer-support",
      "display_name": "客服助手",
      "type": "chat",
      "status": "active",
      "created_at": "2026-04-09T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

#### 创建 Agent

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/agents \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-agent",
    "display_name": "我的助手",
    "type": "chat",
    "config": {
      "model": "gpt-4",
      "temperature": 0.7,
      "max_tokens": 2000,
      "system_prompt": "你是一个友好的助手"
    }
  }'
```

**参数说明**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | Agent 唯一标识 |
| display_name | string | 否 | 显示名称 |
| type | string | 是 | Agent 类型：chat、code、rag、tool |
| config.model | string | 是 | 模型：gpt-4、gpt-3.5-turbo、claude-3 |
| config.temperature | number | 否 | 温度（0-1），默认 0.7 |
| config.max_tokens | number | 否 | 最大输出，默认 2000 |
| config.system_prompt | string | 否 | 系统提示词 |

#### 更新 Agent

**请求示例**：
```bash
curl -X PUT https://api.example.com/api/v1/agents/my-agent \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "更新后的助手",
    "config": {
      "temperature": 0.5
    }
  }'
```

#### 删除 Agent

**请求示例**：
```bash
curl -X DELETE https://api.example.com/api/v1/agents/my-agent \
  -H "Authorization: Bearer <token>"
```

---

### 三、Agent 执行

#### 同步执行

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/agents/my-agent/execute \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "你好，请介绍一下你自己"
  }'
```

**响应示例**：
```json
{
  "execution_id": "exec-123",
  "agent_id": "my-agent",
  "status": "completed",
  "output": "你好！我是 AI 助手...",
  "duration_ms": 1250,
  "tokens_used": {
    "input": 10,
    "output": 50,
    "total": 60
  }
}
```

#### 流式执行（SSE）

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/agents/my-agent/execute/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "input": "写一个快速排序算法"
  }'
```

**响应格式**（Server-Sent Events）：
```
event: token
data: {"content": "以下是"}

event: token
data: {"content": "快速排序"}

event: done
data: {"execution_id": "exec-123"}
```

#### 查询执行状态

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/executions/exec-123 \
  -H "Authorization: Bearer <token>"
```

**响应示例**：
```json
{
  "execution_id": "exec-123",
  "agent_id": "my-agent",
  "status": "completed",
  "input": "你好，请介绍一下你自己",
  "output": "你好！我是 AI 助手...",
  "created_at": "2026-04-09T10:00:00Z",
  "completed_at": "2026-04-09T10:00:01Z",
  "duration_ms": 1250
}
```

#### 查询执行历史

**请求示例**：
```bash
curl -X GET "https://api.example.com/api/v1/agents/my-agent/history?limit=10" \
  -H "Authorization: Bearer <token>"
```

**参数说明**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | number | 否 | 返回数量，默认 20 |
| offset | number | 否 | 偏移量，默认 0 |
| start_date | string | 否 | 开始日期（ISO 8601）|
| end_date | string | 否 | 结束日期（ISO 8601）|

---

### 四、Skill 管理

#### 获取 Skill 列表

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/skills \
  -H "Authorization: Bearer <token>"
```

**响应示例**：
```json
{
  "skills": [
    {
      "id": "skill-001",
      "name": "weather",
      "display_name": "天气查询",
      "description": "查询指定城市的天气",
      "type": "tool",
      "status": "active"
    }
  ],
  "total": 1
}
```

#### 为 Agent 配置 Skill

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/agents/my-agent/skills \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_ids": ["skill-001", "skill-002"]
  }'
```

---

### 五、知识库管理

#### 创建知识库

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/knowledge \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-knowledge",
    "display_name": "我的知识库",
    "description": "存储我的私有文档",
    "embedding_model": "text-embedding-3-small"
  }'
```

#### 上传文档

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/knowledge/my-knowledge/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf" \
  -F "metadata={\"category\":\"product\"}"
```

**支持的文件格式**：
- 文档：.pdf, .docx, .txt, .md
- 表格：.csv, .xlsx
- 最大文件大小：50 MB

#### 查询知识库

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/knowledge/my-knowledge/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "公司的报销流程是什么？",
    "top_k": 5
  }'
```

**响应示例**：
```json
{
  "results": [
    {
      "content": "报销流程说明...",
      "score": 0.85,
      "document_id": "doc-001",
      "metadata": {
        "file_name": "报销制度.pdf",
        "page": 5
      }
    }
  ],
  "total": 5
}
```

#### 关联知识库到 Agent

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/agents/my-agent/knowledge \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_ids": ["knowledge-001"]
  }'
```

---

### 六、会话管理

#### 创建会话

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/sessions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "title": "客服对话"
  }'
```

#### 发送消息

**请求示例**：
```bash
curl -X POST https://api.example.com/api/v1/sessions/session-123/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "如何重置密码？"
  }'
```

#### 获取会话历史

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/sessions/session-123/messages \
  -H "Authorization: Bearer <token>"
```

---

### 七、租户管理

#### 获取租户信息

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/tenants/me \
  -H "Authorization: Bearer <token>"
```

**响应示例**：
```json
{
  "id": "tenant-456",
  "name": "我的公司",
  "plan": "pro",
  "quota": {
    "api_calls": 10000,
    "storage": 10737418240,
    "agents": 10
  },
  "usage": {
    "api_calls": 256,
    "storage": 107374182,
    "agents": 3
  }
}
```

#### 查看配额使用

**请求示例**：
```bash
curl -X GET https://api.example.com/api/v1/tenants/me/usage \
  -H "Authorization: Bearer <token>"
```

---

## ⚙️ 错误处理

### 错误响应格式

**格式**：
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid parameter",
    "details": {
      "field": "name",
      "reason": "Name is required"
    }
  }
}
```

### HTTP 状态码

| 状态码 | 说明 | 常见原因 |
|--------|------|----------|
| 200 | 成功 | 请求成功 |
| 201 | 创建成功 | 资源创建成功 |
| 400 | 请求错误 | 参数验证失败 |
| 401 | 未认证 | Token 无效或过期 |
| 403 | 无权限 | 没有操作权限 |
| 404 | 未找到 | 资源不存在 |
| 429 | 请求过多 | 触发限流 |
| 500 | 服务器错误 | 内部错误 |

### 常见错误码

| 错误码 | 说明 | 解决方法 |
|--------|------|----------|
| `VALIDATION_ERROR` | 参数验证失败 | 检查请求参数 |
| `UNAUTHORIZED` | 未认证 | 刷新或重新获取 Token |
| `FORBIDDEN` | 无权限 | 联系管理员分配权限 |
| `NOT_FOUND` | 资源不存在 | 检查资源 ID |
| `RATE_LIMIT_EXCEEDED` | 请求过多 | 降低请求频率 |
| `QUOTA_EXCEEDED` | 配额用尽 | 升级套餐或等待重置 |

---

## 📊 API 限流

### 限流规则

| 用户类型 | 每分钟请求数 | 突发请求数 |
|----------|--------------|------------|
| 免费 | 60 | 20 |
| 标准 | 200 | 50 |
| 专业 | 1000 | 200 |
| 企业 | 无限制 | 无限制 |

### 限流响应头

```
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 150
X-RateLimit-Reset: 1712640000
```

### 处理限流

**最佳实践**：
1. 检查 `X-RateLimit-Remaining` 头
2. 当剩余请求 < 10 时，减慢请求速度
3. 收到 429 时，等待 `X-RateLimit-Reset` 后重试

**示例代码**：
```python
import time
import requests

def call_api_with_retry(url, headers, max_retries=3):
    for i in range(max_retries):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            reset_time = int(response.headers.get('X-RateLimit-Reset', 60))
            time.sleep(reset_time)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

---

## 🔗 SDK 使用

### Python SDK

**安装**：
```bash
pip install aiplat-platform-sdk
```

**使用示例**：
```python
# 伪代码：当前仓库未提供 platform Python SDK 包（仅有文档与接口契约）。
# 如需客户端：建议基于 platform 的 OpenAPI/REST 契约生成，或直接用 requests/httpx 封装。
import httpx

# 创建客户端
client = httpx.AsyncClient(
    base_url="https://api.example.com",
    headers={"Authorization": "Bearer your-access-token"},
)

# 执行 Agent
resp = await client.post(
    "/api/v1/agents/my-agent/execute",
    json={"input": "你好，请介绍一下你自己"},
)
print(resp.json())

# 查询知识库
resp = await client.post(
    "/api/v1/knowledge/my-knowledge/query",
    json={"query": "公司的报销流程是什么？", "top_k": 5},
)
for item in resp.json().get("items", []):
    print(item.get("content"), item.get("score"))
```

### JavaScript SDK

**安装**：
```bash
npm install @aiplat/platform-sdk
```

**使用示例**：
```javascript
import { PlatformClient } from '@aiplat/platform-sdk';

// 创建客户端
const client = new PlatformClient({
  apiUrl: 'https://api.example.com',
  token: 'your-access-token'
});

// 执行 Agent
const result = await client.agents.execute({
  agentId: 'my-agent',
  input: '你好，请介绍一下你自己'
});

console.log(result.output);

// 查询知识库
const results = await client.knowledge.query({
  knowledgeId: 'my-knowledge',
  query: '公司的报销流程是什么？',
  topK: 5
});

results.forEach(result => {
  console.log(result.content, result.score);
});
```

---

## 🐛 常见问题

### Q：Token 过期怎么办？

**原因**：Token 有效期默认 24 小时

**解决方法**：
1. 使用 refresh_token 刷新
2. 或重新登录获取新 Token

```bash
curl -X POST https://api.example.com/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your-refresh-token"}'
```

### Q：API 返回 429 错误？

**原因**：请求过于频繁，触发限流

**解决方法**：
1. 降低请求频率
2. 检查限流响应头
3. 等待限流重置后重试

### Q：如何处理大文件上传？

**方法一：分块上传**
```bash
# 上传大文件（使用 multipart/form-data）
curl -X POST https://api.example.com/api/v1/knowledge/my-knowledge/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@large-document.pdf" \
  -F "chunk_size=10485760"
```

**方法二：先上传到存储，再导入**
```bash
# 1. 获取上传 URL
curl -X POST https://api.example.com/api/v1/storage/upload-url \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"file_name": "large-document.pdf", "file_size": 104857600}'

# 2. 上传文件到 URL
curl -X PUT "<upload-url>" \
  -H "Content-Type: application/pdf" \
  --data-binary @large-document.pdf

# 3. 导入文件
curl -X POST https://api.example.com/api/v1/knowledge/my-knowledge/import \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"file_url": "<file-url>"}'
```

### Q：如何并发执行多个 Agent？

**使用异步 API**：
```bash
# 使用异步执行
curl -X POST https://api.example.com/api/v1/agents/my-agent/execute/async \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input": "分析这份数据"}'

# 返回执行 ID
# {"execution_id": "exec-123"}

# 查询执行状态
curl -X GET https://api.example.com/api/v1/executions/exec-123 \
  -H "Authorization: Bearer <token>"
```

---

## 📞 获取帮助

| 问题类型 | 联系方式 |
|----------|----------|
| API 使用问题 | 查看在线文档 |
| 功能建议 | 提交工单 |
| Bug 反馈 | 提交工单 |
| 紧急问题 | 电话支持 |

---

## 🔗 相关链接

- [← 返回平台层文档](../../index.md)
- [开发者指南](../developer/index.md)
- [API 参考文档](../../api/index.md)

---

*最后更新: 2026-04-09*
