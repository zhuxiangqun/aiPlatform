# 模型管理系统

## 概述

模型管理系统负责管理 AI 平台中的所有模型，包括配置文件中的内置模型、本地 Ollama 模型以及用户添加的外部模型。

## 架构

```
┌────────────────────────────────────────────────────────────────────────┐
│                        前端 (React + Tailwind CSS)                      │
├────────────────────────────────────────────────────────────────────────┤
│  /infra/models                    │  /infra/services                   │
│  模型管理页面                      │  推理服务管理页面                    │
│  - 模型列表/状态                   │  - 服务实例列表                      │
│  - 添加/配置模型                   │  - 部署/扩缩容                       │
│  - 启用/禁用/测试                  │  - 监控/日志                         │
└────────────────────────────────────┴────────────────────────────────────┘
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     aiPlat-management (8000)                           │
│                         路由层 + API 网关                                │
│                    /api/infra/models → 转发到 infra                     │
└────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       aiPlat-infra (8001)                               │
├────────────────────────────────────────────────────────────────────────┤
│  ModelManager                                                          │
│  ├── ConfigLoader      ← 读取 config/infra/*.yaml                      │
│  ├── OllamaScanner     ← 扫描 Ollama 本地模型                           │
│  ├── ExternalStorage   ← 读写 data/models.json                         │
│  └── HealthChecker     ← 模型健康检查                                   │
└────────────────────────────────────────────────────────────────────────┘
```

## 模型来源

| 来源 | 标签 | 可编辑 | 可删除 | 存储位置 |
|------|------|--------|--------|----------|
| 配置文件 | `内置` | ❌ | ❌ | config/infra/*.yaml |
| Ollama 本地 | `本地` | ❌ | ❌ | 动态扫描 |
| 用户添加 | `自定义` | ✅ | ✅ | data/models.json |

## 数据模型

### ModelInfo

```python
@dataclass
class ModelInfo:
    id: str                    # 模型唯一标识
    name: str                  # 模型名称（如 gpt-4, llama3:7b）
    display_name: str         # 显示名称
    type: ModelType            # chat | embedding | image | audio
    provider: str             # openai | anthropic | ollama | custom
    source: ModelSource        # config | local | external
    enabled: bool              # 是否启用
    status: ModelStatus        # available | unavailable | error | not_configured
    
    config: ModelConfig        # 模型配置参数
    stats: ModelStats          # 使用统计
    
    created_at: datetime
    updated_at: datetime
```

### ModelConfig

```python
@dataclass
class ModelConfig:
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: List[str] = None
    
    # Provider 特定配置
    api_key_env: str = None      # API Key 环境变量名
    base_url: str = None         # 自定义端点
    headers: Dict[str, str] = None
```

## API 端点

### 模型列表

```
GET /api/infra/models
```

查询参数：
- `source`: 来源筛选 (config | local | external)
- `type`: 类型筛选 (chat | embedding | image)
- `enabled`: 是否启用 (true | false)
- `status`: 状态筛选 (available | unavailable | error)

响应：
```json
{
  "models": [
    {
      "id": "openai:gpt-4",
      "name": "gpt-4",
      "displayName": "GPT-4",
      "type": "chat",
      "provider": "openai",
      "source": "config",
      "enabled": true,
      "status": "available",
      "config": { ... },
      "stats": { ... }
    }
  ],
  "total": 10
}
```

### 获取模型详情

```
GET /api/infra/models/{model_id}
```

### 添加模型

```
POST /api/infra/models
```

请求体：
```json
{
  "name": "my-llama3",
  "displayName": "My Llama3",
  "type": "chat",
  "provider": "custom",
  "config": {
    "baseUrl": "http://192.168.1.100:8000/v1",
    "apiKeyEnv": "MY_LLM_API_KEY",
    "temperature": 0.7,
    "maxTokens": 4096
  },
  "description": "私有部署的 Llama3 模型"
}
```

### 更新模型配置

```
PUT /api/infra/models/{model_id}
```

### 删除模型

```
DELETE /api/infra/models/{model_id}
```

### 启用/禁用模型

```
POST /api/infra/models/{model_id}/enable
POST /api/infra/models/{model_id}/disable
```

### 测试模型

```
POST /api/infra/models/{model_id}/test/connectivity  # 连通性测试
POST /api/infra/models/{model_id}/test/response      # 响应测试
```

### 扫描本地模型

```
GET /api/infra/models/local?endpoint=http://localhost:11434
```

### 获取 Provider 列表

```
GET /api/infra/models/providers
```

响应：
```json
{
  "providers": [
    {
      "id": "openai",
      "name": "OpenAI",
      "type": "external",
      "requiresApiKey": true,
      "capabilities": ["chat", "embedding", "image", "audio"]
    },
    {
      "id": "ollama",
      "name": "Ollama",
      "type": "local",
      "requiresApiKey": false,
      "capabilities": ["chat", "embedding"]
    }
  ]
}
```

## 配置文件格式

### config/infra/default.yaml

```yaml
# 模型配置
models:
  # OpenAI 模型
  - name: gpt-4
    provider: openai
    type: chat
    api_key_env: OPENAI_API_KEY
    enabled: true
    
  - name: gpt-3.5-turbo
    provider: openai
    type: chat
    api_key_env: OPENAI_API_KEY
    enabled: true
    
  - name: text-embedding-ada-002
    provider: openai
    type: embedding
    api_key_env: OPENAI_API_KEY
    enabled: true
    
  # Anthropic 模型
  - name: claude-3-opus
    provider: anthropic
    type: chat
    api_key_env: ANTHROPIC_API_KEY
    enabled: true

# Ollama 配置
ollama:
  endpoint: http://localhost:11434
  auto_scan: true
```

### data/models.json (用户添加的模型)

```json
{
  "external_models": [
    {
      "id": "custom-1",
      "name": "my-llama3",
      "display_name": "My Llama3",
      "type": "chat",
      "provider": "custom",
      "enabled": true,
      "status": "available",
      "config": {
        "base_url": "http://192.168.1.100:8000/v1",
        "api_key_env": "MY_LLM_API_KEY",
        "temperature": 0.7,
        "max_tokens": 4096
      },
      "description": "私有部署的 Llama3 模型",
      "tags": ["custom", "llama"],
      "created_at": "2026-04-12T10:00:00",
      "updated_at": "2026-04-12T10:00:00"
    }
  ]
}
```

## 前端页面

### 模型列表

| 字段 | 说明 |
|------|------|
| 模型名称 | 显示名称 + 实际名称 |
| 类型 | chat / embedding / image / audio |
| Provider | openai / anthropic / ollama / custom |
| 来源 | 内置 / 本地 / 自定义 |
| 状态 | 可用 / 不可用 / 错误 / 未配置 |
| 启用 | 开关（内置模型不可切换）|
| 操作 | 测试连通性 / 配置 / 删除 |

### 添加模型弹窗

1. 选择 Provider
2. 配置端点（本地模型需要Ollama 端点）
3. 配置参数（API Key、温度、最大 Token 等）
4. 测试连通性
5. 保存

## 状态流转

```
┌─────────────┐    测试通过    ┌──────────┐    启用    ┌─────────┐
│  未配置     │ ───────────→ │  已配置   │ ────────→ │  已启用 │
└─────────────┘              └──────────┘           └─────────┘
                                  │                      │
                             测试失败                禁用/下线
                                  ↓                      ↓
                             ┌──────────┐           ┌─────────┐
                             │  不可用   │ ←──────── │  已禁用 │
                             └──────────┘           └─────────┘
```

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 模型未找到 | ID 不存在 | 返回 404 |
| 配置模型不可修改 | 内置模型只读 | 返回 403 |
| Ollama 连接失败 | 本地未运行 | 标记为 unavailable |
| API Key 无效 | 环境变量未设置 | 标记为 not_configured |

## 使用示例

### 查询所有模型

```bash
curl http://localhost:8000/api/infra/models
```

### 添加自定义模型

```bash
curl -X POST http://localhost:8000/api/infra/models \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-model",
    "displayName": "My Custom Model",
    "type": "chat",
    "provider": "custom",
    "config": {
      "baseUrl": "http://localhost:8000/v1",
      "apiKeyEnv": "MY_API_KEY"
    }
  }'
```

### 测试模型连通性

```bash
curl -X POST http://localhost:8000/api/infra/models/openai:gpt-4/test/connectivity
```

### 扫描本地 Ollama 模型

```bash
curl "http://localhost:8000/api/infra/models/local?endpoint=http://localhost:11434"
```

---

*最后更新:2026-04-13