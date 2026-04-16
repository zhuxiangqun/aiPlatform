# aiPlat-core 用户指南（To-Be 为主，As-Is 以代码事实为准）

> 说明：本文档假设存在 platform 层的统一 API 网关、鉴权与 WebSocket 流式接口；这些在当前仓库可能属于 To-Be。  
> As-Is：核心 API 入口以 `core/server.py` 为准。统一口径参见 [`ARCHITECTURE_STATUS.md`](../../ARCHITECTURE_STATUS.md)。

> 本文档面向使用 Core API 的开发者，提供核心组件的使用方法和配置示例。

---

## 该文档包含

- Agent、Skill、Memory、Knowledge、Tool 组件的使用方法
- 组件配置示例和参数说明
- 常见使用场景和操作步骤
- 异常处理和最佳实践

---

## 快速开始

### 前提条件

在使用 Core API 之前，确保：
- 已完成系统部署（参考 [运维指南](./ops/index.md)）
- 已获取 API 访问令牌（To-Be：由 platform/auth 提供）
- 已确认服务状态为健康

### 验证服务状态

**检查 Core 服务健康状态**：
```bash
# 通过 Platform HTTP API 检查
curl http://localhost:8000/health

# 预期输出
{"status": "healthy", "components": ["agent", "skill", "memory", "knowledge", "tool"]}
```

---

## Agent 使用

### 创建 ReAct Agent

**使用场景**：需要 Agent 推理并执行多步骤任务的场景。

**操作步骤**：

1. **查找可用 LLM 服务**：
```bash
curl http://localhost:8000/api/v1/core/llm/list
# 返回: ["default", "gpt-4", "claude-3", ...]
```

2. **创建 Agent 配置**：
```yaml
# agent-config.yaml
agent:
  type: react
  name: my_react_agent
  llm_service: default
  max_iterations: 10
  timeout: 300
  skills:
    - web_search
    - code_execute
    - data_analysis
  memory:
    type: conversation
    max_history: 20
```

3. **提交创建请求**：
```bash
curl -X POST http://localhost:8000/agents \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @agent-config.yaml
# 返回: {"agent_id": "agent_001", "status": "created"}
```

### 执行 Agent 任务

**单次执行**：
```bash
curl -X POST http://localhost:8000/agents/agent_001/execute \
  -H "Authorization: Bearer <token>" \
  -d '{"input": "查找 Python 异步编程最佳实践"}'
# 返回: {"execution_id": "exec_001", "status": "completed", "output": "..."}
```

**流式执行（WebSocket）**：
```bash
# 连接 WebSocket
ws://localhost:8000/api/v1/core/agents/agent_001/stream

# 发送请求
{"action": "execute", "input": "分析这段代码的性能瓶颈"}

# 接收流式输出
{"type": "thought", "content": "正在思考..."}
{"type": "action", "content": "调用工具..."}
{"type": "result", "content": "分析完成..."}
```

### 配置参数说明

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `max_iterations` | int | 最大推理迭代次数 | 10 |
| `timeout` | int | 执行超时时间（秒） | 300 |
| `llm_service` | string | LLM 服务名称 | default |
| `skills` | list | 关联的技能列表 | [] |
| `memory.type` | string | 记忆类型 | conversation |
| `memory.max_history` | int | 最大历史记录数 | 20 |

---

## Skill 使用

### 查找可用技能

**列出所有注册技能**：
```bash
curl http://localhost:8000/api/v1/core/skills
# 返回:
{
  "skills": [
    {"name": "web_search", "description": "网络搜索", "version": "1.0.0"},
    {"name": "code_execute", "description": "代码执行", "version": "1.2.0"},
    {"name": "data_analysis", "description": "数据分析", "version": "2.0.0"}
  ]
}
```

### 调用单个技能

**直接调用技能**：
```bash
curl -X POST http://localhost:8000/api/v1/core/skills/web_search/execute \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "PyTorch 分布式训练教程"}'
# 返回: {"results": [...], "count": 10}
```

### 创建自定义技能

**1. 编写技能配置文件**：
```yaml
# custom_skill.yaml
skill:
  name: document_summarizer
  description: 文档摘要生成
  version: 1.0.0
  input_schema:
    type: object
    properties:
      document_path:
        type: string
        description: 文档路径
      max_length:
        type: integer
        description: 摘要最大长度
        default: 500
  output_schema:
    type: object
    properties:
      summary:
        type: string
        description: 生成的摘要
  llm_service: default
  prompt_template: |
    请为以下文档生成简洁摘要，不超过 {{max_length}} 字：
    {{document_content}}
```

**2. 注册技能**：
```bash
curl -X POST http://localhost:8000/api/v1/core/skills/register \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @custom_skill.yaml
# 返回: {"skill_name": "document_summarizer", "status": "registered"}
```

**3. 测试技能**：
```bash
curl -X POST http://localhost:8000/api/v1/core/skills/document_summarizer/execute \
  -H "Authorization: Bearer <token>" \
  -d '{"document_path": "/path/to/doc.pdf", "max_length": 300}'
# 返回: {"summary": "..."}
```

---

## Memory 使用

### 对话记忆

**使用场景**：保持多轮对话上下文。

**配置示例**：
```yaml
memory:
  type: conversation
  max_history: 50
  storage: redis
  ttl: 3600  # 1 小时
```

**操作命令**：
```bash
# 查询对话历史
curl http://localhost:8000/api/v1/core/memory/{session_id}/history

# 清除对话历史
curl -X DELETE http://localhost:8000/api/v1/core/memory/{session_id}/history

# 设置 TTL
curl -X PATCH http://localhost:8000/api/v1/core/memory/{session_id}/config \
  -d '{"ttl": 7200}'
```

### 执行记忆

**使用场景**：保存任务执行历史，支持恢复中断的任务。

**操作命令**：
```bash
# 保存执行状态
curl -X POST http://localhost:8000/api/v1/core/memory/executions \
  -d '{"execution_id": "exec_001", "state": "interrupted", "checkpoint": {...}}

# 恢复执行
curl -X POST http://localhost:8000/api/v1/core/memory/executions/exec_001/resume
```

### 知识记忆

**使用场景**：存储外部知识，支持语义检索。

**配置示例**：
```yaml
memory:
  type: knowledge
  embedding_service: default
  vector_store: milvus
  max_entries: 10000
  similarity_threshold: 0.8
```

**操作命令**：
```bash
# 添加知识
curl -X POST http://localhost:8000/api/v1/core/memory/knowledge \
  -d '{"content": "Python best practices...", "metadata": {"source": "doc"}}

# 语义检索
curl -X POST http://localhost:8000/api/v1/core/memory/knowledge/search \
  -d '{"query": "如何优化 Python 性能", "top_k": 5}'
```

---

## Knowledge Base 使用

### 创建知识库

**操作步骤**：

1. **创建知识库配置**：
```yaml
# knowledge_base.yaml
knowledge_base:
  name: project_docs
  description: 项目技术文档
  embedding_service: default
  vector_store: milvus
  chunk_size: 512
  chunk_overlap: 50
```

2. **创建知识库**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases \
  -H "Authorization: Bearer <token>" \
  -d @knowledge_base.yaml
# 返回: {"kb_id": "kb_001", "status": "created"}
```

### 文档导入

**上传文档**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases/kb_001/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/document.pdf" \
  -F "metadata={\"category\": \"technical\"}"
```

**批量导入**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases/kb_001/batch-import \
  -H "Authorization: Bearer <token>" \
  -d '{"directory": "/path/to/docs", "file_pattern": "*.md"}'
```

**查看导入状态**：
```bash
curl http://localhost:8000/api/v1/core/knowledge-bases/kb_001/import-status
# 返回: {"status": "processing", "progress": 75, "files_processed": 15, "files_total": 20}
```

### 知识检索

**基础检索**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases/kb_001/search \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "如何配置数据库连接", "top_k": 5}'
# 返回: {"results": [...], "total": 5}
```

**带过滤器的检索**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases/kb_001/search \
  -d '{
    "query": "数据库配置",
    "top_k": 10,
    "filters": {
      "category": "technical",
      "created_after": "2025-01-01"
    }
  }'
```

**混合检索（向量 + 关键词）**：
```bash
curl -X POST http://localhost:8000/api/v1/core/knowledge-bases/kb_001/hybrid-search \
  -d '{
    "query": "API 设计最佳实践",
    "vector_weight": 0.7,
    "keyword_weight": 0.3,
    "top_k": 10
  }'
```

---

## Tool 使用

### 查找可用工具

**列出所有工具**：
```bash
curl http://localhost:8000/api/v1/core/tools
# 返回:
{
  "tools": [
    {"name": "calculator", "description": "数学计算", "category": "compute"},
    {"name": "web_search", "description": "网络搜索", "category": "search"},
    {"name": "file_io", "description": "文件操作", "category": "operation"}
  ]
}
```

### 调用工具

**直接调用**：
```bash
# 计算工具
curl -X POST http://localhost:8000/api/v1/core/tools/calculator/execute \
  -d '{"expression": "2^10 + sqrt(100)"}
# 返回: {"result": 1034}

# 文件读取工具
curl -X POST http://localhost:8000/api/v1/core/tools/file_io/execute \
  -d '{"action": "read", "path": "/path/to/file.txt"}
# 返回: {"content": "file content..."}
```

### 注册自定义工具

**配置文件示例**：
```yaml
# custom_tool.yaml
tool:
  name: api_client
  description: 外部 API 客户端
  version: 1.0.0
  category: operation
  input_schema:
    type: object
    properties:
      url:
        type: string
        description: API URL
      method:
        type: string
        enum: [GET, POST, PUT, DELETE]
        default: GET
      headers:
        type: object
        description: 请求头
      body:
        type: object
        description: 请求体
  output_schema:
    type: object
    properties:
      status:
        type: integer
        description: HTTP 状态码
      data:
        type: object
        description: 响应数据
```

**注册命令**：
```bash
curl -X POST http://localhost:8000/api/v1/core/tools/register \
  -H "Authorization: Bearer <token>" \
  -d @custom_tool.yaml
```

---

## 常见场景

### 场景 1：构建 RAG 问答系统

**步骤**：
1. 创建知识库（参考 Knowledge Base 使用章节）
2. 导入文档
3. 创建 ReAct Agent 并关联知识库检索技能
4. 执行问答

**示例配置**：
```yaml
# rag_agent.yaml
agent:
  type: react
  name: rag_qa_agent
  llm_service: default
  skills:
    - knowledge_search
  knowledge_base: kb_001
  memory:
    type: conversation
    max_history: 10
```

**执行命令**：
```bash
curl -X POST http://localhost:8000/api/v1/core/agents/rag_qa_agent/execute \
  -d '{"input": "项目的技术架构是什么？"}'
```

### 场景 2：构建数据分析 Agent

**步骤**：
1. 创建数据分析技能
2. 创建 Plan-and-Execute Agent
3. 执行数据分析任务

**示例配置**：
```yaml
# data_analysis_agent.yaml
agent:
  type: plan_and_execute
  name: data_agent
  llm_service: default
  skills:
    - data_query
    - statistical_analysis
    - visualization
  tools:
    - calculator
    - file_io
```

---

## 异常处理

### 常见错误码

| 错误码 | 含义 | 解决方法 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查请求参数格式 |
| 401 | 认证失败 | 检查 Token 是否有效 |
| 403 | 权限不足 | 联系管理员授权 |
| 404 | 资源不存在 | 检查资源 ID 是否正确 |
| 429 | 请求频率超限 | 降低请求频率或申请提额 |
| 500 | 服务内部错误 | 查看日志并联系技术支持 |
| 503 | 服务不可用 | 等待服务恢复或检查依赖服务 |

### 错误响应示例

```json
{
  "error": {
    "code": 400,
    "message": "Invalid parameter: max_iterations must be positive integer",
    "details": {
      "field": "max_iterations",
      "value": "-1",
      "expected": "positive integer"
    }
  }
}
```

---

## 性能优化

### Agent 优化

- 合理设置 `max_iterations` 避免无限循环
- 使用 `timeout` 防止执行时间过长
- 选择合适的 LLM 服务（速度 vs 质量）

### Memory 优化

- 设置合理的 `max_history` 避免内存溢出
- 使用 `ttl` 自动清理过期记忆
- 对于大量历史数据，使用知识记忆而非对话记忆

### Knowledge Base 优化

- 合理设置 `chunk_size`（一般 256-512 tokens）
- 使用 `chunk_overlap` 保持文档连贯性
- 定期清理过时文档
- 使用混合检索提高准确率

---

## 相关链接

- [← 返回核心层文档](../index.md)
- [架构师指南](./architect/index.md) - 核心层架构设计
- [开发者指南](./developer/index.md) - 核心层开发指南
- [运维指南](./ops/index.md) - 核心层运维指南

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- As-Is API 入口：`core/server.py`
- Agents/Skills/Tools endpoints：`core/server.py`
