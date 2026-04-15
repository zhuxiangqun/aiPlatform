# 模型管理

> 模型配置、健康检查、连通性测试

---

## 一、模块定位

模型管理模块提供 AI 平台中所有模型的统一管理能力：

- **内置模型**：配置文件定义，只读
- **本地模型**：Ollama 自动扫描，只读
- **自定义模型**：用户添加，可编辑删除

---

## 二、模型来源

| 来源 | 标签 | 可编辑 | 可删除 | 存储位置 |
|------|------|--------|--------|----------|
| 配置文件 | `内置` | ❌ | ❌ | config/infra/*.yaml |
| Ollama 本地 | `本地` | ❌ | ❌ | 动态扫描 |
| 用户添加 | `自定义` | ✅ | ✅ | data/models.json |

---

## 三、功能列表

### 3.1 模型列表

**路由**：`/infra/models`

**功能**：
- 查看所有模型（分组显示）
- 按来源筛选（内置/本地/自定义）
- 按类型筛选（chat/embedding/image/audio）
- 按状态筛选（available/unavailable/error）
- 搜索模型名称

**界面元素**：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 模型管理                                            [添加模型] [扫描] │
├─────────────────────────────────────────────────────────────────────┤
│ 筛选：[全部 ▼] [内置] [本地] [自定义]    搜索：[__________]        │
├─────────────────────────────────────────────────────────────────────┤
│ 内置模型 (蓝色标签)                                                  │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ DeepSeek V3                                          [测试]   ││
│ │ deepseek-chat | chat | openai | ✅ 可用                      ││
│ │ 端点: https://api.deepseek.com/v1                             ││
│ └─────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ 本地 Embedding                                        [测试]   ││
│ │ mxbai-embed-large | embedding | ollama | ✅ 可用             ││
│ │ 端点: http://localhost:11434                                  ││
│ └─────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│ 本地模型 (绿色标签)                                                  │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ qwen2.5-coder:32b                                    [测试]   ││
│ │ qwen2.5-coder:32b | chat | ollama | ✅ 可用                   ││
│ └─────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│ 自定义模型 (橙色标签)                                    [添加]    │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ My Custom Model                             [编辑] [删除] [测试]││
│ │ my-model | chat | custom | ⚠️ 不可用                         ││
│ │ 端点: http://192.168.1.100:8000/v1                            ││
│ └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 添加模型

**路由**：`/infra/models/add`

**功能**：
- 选择 Provider（OpenAI/Anthropic/Ollama/Custom）
- 配置模型端点
- 配置 API Key（外部模型）
- 配置模型参数（temperature, max_tokens 等）
- 连通性测试
- 保存模型

**添加流程**：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 添加模型                                                            │
├─────────────────────────────────────────────────────────────────────┤
│ 步骤 1/3: 选择 Provider                                             │
│                                                                     │
│ [OpenAI]  [Anthropic]  [Ollama]  [Custom]                          │
│                                                                     │
│ ┌───────────────┐                                                  │
│ │    OpenAI     │ ← 选中                                          │
│ │  GPT-4/3.5    │                                                  │
│ │  需要API Key  │                                                  │
│ └───────────────┘                                                  │
│                                                                     │
│                                            [下一步 →]              │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 3.3 模型详情

**路由**：`/infra/models/:modelId`

**功能**：
- 查看模型配置
- 编辑模型参数（自定义模型）
- 连通性测试
- 响应测试
- 查看使用统计
- 查看健康状态历史

---

### 3.4 连通性测试

**测试类型**：

| 测试类型 | 说明 | 检查内容 |
|---------|------|----------|
| 连通性测试 | 快速检查 | 端点可达性、API Key 有效性 |
| 响应测试 | 完整测试 | 模型响应、Token 生成、延迟 |

**测试流程**：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 连通性测试                                                          │
├─────────────────────────────────────────────────────────────────────┤
│ 模型: DeepSeek V3                                                  │
│ 端点: https://api.deepseek.com/v1                                 │
│                                                                     │
│ [测试连通性]                                                        │
│                                                                     │
│ 测试结果:                                                           │
│ ✅ 端点可达                                                         │
│ ✅ API Key 有效                                                     │
│ ✅ 模型可用                                                         │
│ ⏱️ 响应时间: 120ms                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 四、API 端点

### 4.1 模型列表

```http
GET /api/infra/models
```

**查询参数**：
- `source`: 来源筛选 (config | local | external)
- `type`: 类型筛选 (chat | embedding | image | audio)
- `enabled`: 是否启用 (true | false)
- `status`: 状态筛选 (available | unavailable | error)

**响应示例**：

```json
{
  "models": [
    {
      "id": "deepseek-chat",
      "name": "deepseek-chat",
      "display_name": "DeepSeek V3",
      "type": "chat",
      "provider": "openai",
      "source": "config",
      "enabled": true,
      "status": "available",
      "config": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.7,
        "max_tokens": 4096
      },
      "tags": ["builtin", "chat"]
    }
  ],
  "total": 10
}
```

### 4.2 添加模型

```http
POST /api/infra/models
```

**请求体**：

```json
{
  "name": "my-model",
  "display_name": "My Custom Model",
  "type": "chat",
  "provider": "custom",
  "config": {
    "base_url": "http://192.168.1.100:8000/v1",
    "api_key_env": "MY_API_KEY",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "description": "私有部署的模型"
}
```

### 4.3 更新模型配置

```http
PUT /api/infra/models/{model_id}
```

### 4.4 删除模型

```http
DELETE /api/infra/models/{model_id}
```

### 4.5 启用/禁用模型

```http
POST /api/infra/models/{model_id}/enable
POST /api/infra/models/{model_id}/disable
```

### 4.6 测试模型

```http
POST /api/infra/models/{model_id}/test/connectivity  # 连通性测试
POST /api/infra/models/{model_id}/test/response      # 响应测试
```

### 4.7 扫描本地模型

```http
GET /api/infra/models/local?endpoint=http://localhost:11434
```

### 4.8 获取 Provider 列表

```http
GET /api/infra/models/providers
```

---

## 五、数据模型

### 5.1 ModelInfo

```python
@dataclass
class ModelInfo:
    id: str                    # 模型唯一标识
    name: str                  # 模型名称
    display_name: str          # 显示名称
    type: ModelType            # chat | embedding | image | audio
    provider: str              # openai | anthropic | ollama | custom
    source: ModelSource        # config | local | external
    enabled: bool              # 是否启用
    status: ModelStatus        # available | unavailable | error | not_configured
    
    config: ModelConfig        # 模型配置参数
    stats: ModelStats          # 使用统计
    
    created_at: datetime
    updated_at: datetime
```

### 5.2 ModelConfig

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

---

## 六、配置文件

### 6.1 内置模型配置

**文件**：`config/infra/default.yaml`

```yaml
models:
  # DeepSeek 模型
  - name: deepseek-chat
    display_name: DeepSeek V3
    provider: openai
    type: chat
    api_key_env: DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    enabled: true
    config:
      temperature: 0.7
      max_tokens: 4096
    
  - name: deepseek-reasoner
    display_name: DeepSeek R1
    provider: openai
    type: chat
    api_key_env: DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    enabled: true

# Ollama 配置
ollama:
  endpoint: http://localhost:11434
  auto_scan: true
```

### 6.2 用户添加的模型

**文件**：`data/models.json`

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
      "created_at": "2026-04-13T10:00:00",
      "updated_at": "2026-04-13T10:00:00"
    }
  ]
}
```

---

## 七、状态流转

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

---

## 八、错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 模型未找到 | ID 不存在 | 返回 404 |
| 配置模型不可修改 | 内置模型只读 | 返回 403 |
| Ollama 连接失败 | 本地未运行 | 标记为 unavailable |
| API Key 无效 | 环境变量未设置 | 标记为 not_configured |

---

## 九、实现文件

### 后端

| 文件 | 功能 |
|------|------|
| `aiPlat-infra/infra/management/model/manager.py` | ModelManager 主类 |
| `aiPlat-infra/infra/management/model/config_loader.py` | YAML 配置加载 |
| `aiPlat-infra/infra/management/model/ollama_scanner.py` | Ollama 模型扫描 |
| `aiPlat-infra/infra/management/model/external_storage.py` | JSON 存储 |
| `aiPlat-infra/infra/management/model/health_checker.py` | 健康检查 |

### 前端

| 文件 | 功能 |
|------|------|
| `frontend/src/pages/Infra/Models/Models.tsx` | 模型管理页面 |
| `frontend/src/services/modelApi.ts` | 模型 API 服务 |

---

## 十、使用示例

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
    "display_name": "My Custom Model",
    "type": "chat",
    "provider": "custom",
    "config": {
      "base_url": "http://localhost:8000/v1",
      "api_key_env": "MY_API_KEY"
    }
  }'
```

### 测试模型连通性

```bash
curl -X POST http://localhost:8000/api/infra/models/deepseek-chat/test/connectivity
```

### 扫描本地 Ollama 模型

```bash
curl "http://localhost:8000/api/infra/models/local?endpoint=http://localhost:11434"
```

---

*最后更新:2026-04-13  
**版本**：v1.0  
**维护团队**：AI Platform Team