# Services 应用服务

> workbench 的子模块，提供前端与后端的 API 通信封装

---

## 一、模块定位

Services 模块负责前端与后端的通信，封装 API 调用逻辑：

- **API 调用封装**：封装 HTTP 请求逻辑
- **请求拦截**：处理认证、超时、重试
- **响应转换**：解析后端响应
- **缓存管理**：提供缓存能力

---

## 二、服务架构

```
┌─────────────────────────────────────────────────────┐
│              Frontend Services                      │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Agent  │  │  Skill  │  │ Knowledge│        │
│  │ Service │  │ Service │  │ Service │        │
│  └──────────┘  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Tool   │  │ Session │  │  Auth   │        │
│  │ Service │  │ Service │  │ Service │        │
│  └──────────┘  └──────────┘  └──────────┘        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              HTTP Client (Axios)                    │
└─────────────────────────────────────────────────────┘
```

---

## 三、核心服务

### 3.1 AgentService

```typescript
class AgentService {
  // 获取 Agent 列表
  list(filters?: AgentFilters): Promise<Agent[]>
  
  // 获取 Agent 详情
  get(agentId: string): Promise<Agent>
  
  // 创建 Agent
  create(config: CreateAgentConfig): Promise<Agent>
  
  // 更新 Agent
  update(agentId: string, config: UpdateAgentConfig): Promise<Agent>
  
  // 删除 Agent
  delete(agentId: string): Promise<void>
  
  // 发布 Agent
  publish(agentId: string): Promise<void>
  
  // 测试 Agent
  test(agentId: string, input: string): Promise<TestResult>
}
```

### 3.2 SkillService

```typescript
class SkillService {
  // 获取 Skill 列表
  list(filters?: SkillFilters): Promise<Skill[]>
  
  // 获取 Skill 详情
  get(skillId: string): Promise<Skill>
  
  // 注册 Skill
  register(config: RegisterSkillConfig): Promise<Skill>
  
  // 测试 Skill
  test(skillId: string, input: string): Promise<TestResult>
  
  // 发布 Skill
  publish(skillId: string): Promise<void>
}
```

### 3.3 KnowledgeService

```typescript
class KnowledgeService {
  // 获取知识库列表
  list(): Promise<Knowledge[]>
  
  // 获取知识库详情
  get(knowledgeId: string): Promise<Knowledge>
  
  // 创建知识库
  create(config: CreateKnowledgeConfig): Promise<Knowledge>
  
  // 上传文档
  upload(knowledgeId: string, file: File): Promise<void>
  
  // 检索
  search(knowledgeId: string, query: string): Promise<SearchResult[]>
}
```

### 3.4 ToolService

```typescript
class ToolService {
  // 获取工具列表
  list(): Promise<Tool[]>
  
  // 获取工具详情
  get(toolId: string): Promise<Tool>
  
  // 注册工具
  register(config: RegisterToolConfig): Promise<Tool>
  
  // 获取使用统计
  getStats(toolId: string): Promise<ToolStats>
}
```

### 3.5 SessionService

```typescript
class SessionService {
  // 获取会话列表
  list(): Promise<Session[]>
  
  // 获取会话详情
  get(sessionId: string): Promise<Session>
  
  // 获取消息历史
  getHistory(sessionId: string, limit?: number): Promise<Message[]>
  
  // 发送消息
  sendMessage(sessionId: string, content: string): Promise<Message>
  
  // 删除会话
  delete(sessionId: string): Promise<void>
}
```

### 3.6 AuthService

```typescript
class AuthService {
  // 登录
  login(username: string, password: string): Promise<AuthResult>
  
  // 登出
  logout(): Promise<void>
  
  // 获取当前用户
  getCurrentUser(): Promise<User>
  
  // 刷新 Token
  refreshToken(): Promise<AuthResult>
  
  // API Key 管理
  listApiKeys(): Promise<APIKey[]>
  createApiKey(config: CreateAPIKeyConfig): Promise<APIKey>
  revokeApiKey(keyId: string): Promise<void>
}
```

---

## 四、HTTP 客户端配置

```typescript
// axios instance
const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
client.interceptors.request.use((config) => {
  // 添加 JWT Token
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token 过期，尝试刷新
      await authService.refreshToken()
    }
    return Promise.reject(error)
  }
)
```

---

## 五、设计原则

1. **单例模式**：每个服务应该是单例
2. **超时控制**：API 调用应该有超时
3. **统一错误处理**：错误有统一的处理方式
4. **缓存策略**：缓存应该有失效策略

---

## 六、相关文档

- [aiPlat-app 总览](../index.md)
- [workbench 模块](../workbench/index.md)