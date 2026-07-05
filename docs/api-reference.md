# aiPlat API Reference

> 完整 API 文档通过 Swagger UI 提供。所有端点支持交互式调用。

## Swagger UI

启动服务后浏览器打开：

| 层 | URL | 说明 |
|:---|:---|:---|
| Management (推荐) | `http://localhost:8000/docs` | API 网关，聚合所有层 |
| Core | `http://localhost:8002/docs` | Agent 引擎 |
| Infra | `http://localhost:8001/docs` | 模型管理 |
| Platform | `http://localhost:8003/docs` | 知识库 |

## 核心 API 端点

### Agent 管理

```bash
# 列出所有 Agent
GET /api/core/workspace/agents

# 执行 Agent
POST /api/core/workspace/agents/{agent_id}/execute
Body: {"messages": [{"role": "user", "content": "..."}]}

# 启动 Agent
POST /api/core/workspace/agents/{agent_id}/start

# 停止 Agent
POST /api/core/workspace/agents/{agent_id}/stop
```

### Pipeline

```bash
# 创建 Builder 项目
POST /api/core/builder/projects

# 运行 Pipeline
POST /api/core/pipelines/run
Body: {"pipeline_id": "...", "context": {...}}

# Pipeline 状态
GET /api/core/pipelines/{id}/status

# HITL 人工审批
POST /api/core/pipelines/{id}/hitl-resolve
```

### 诊断与监控

```bash
# 架构守卫 (76 条规则)
POST /api/diagnostics/guard/run

# 全量诊断
POST /api/diagnostics/run-all

# 4 层健康检查
GET /api/diagnostics/health/all

# 数据血缘
GET /api/diagnostics/data-lineage

# 模型层级面板
GET /api/diagnostics/model-tier
```

### 知识库

```bash
# 检索知识
POST /api/core/knowledge/retrieve
Body: {"query": "...", "collection_id": "..."}

# Wiki 页面查询
GET /api/core/wiki/pages?query=...

# 主动综合
POST /api/core/wiki/active-synthesis
```

### 模型管理

```bash
# 模型列表
GET /api/infra/models

# 模型启用/禁用
POST /api/infra/models/{model_id}/enable
POST /api/infra/models/{model_id}/disable

# 会话模型覆盖 (/model 命令)
POST /api/core/model-override
Body: {"model_name": "deepseek-v4-pro"}
```

### Skill 系统

```bash
# Skill 列表
GET /api/core/skills

# Skill 执行
POST /api/core/skills/{skill_id}/execute

# Skill 语料库搜索
POST /api/core/skills/corpus-search
Body: {"query": "..."}
```

### 安全

```bash
# 审批列表
GET /api/core/approvals

# 审批操作
POST /api/core/approvals/{id}/approve
POST /api/core/approvals/{id}/reject

# 密钥状态
GET /api/platform/onboarding/secrets-status
```

## 通用约定

| 约定 | 说明 |
|:---|:---|
| 认证 | JWT Bearer token (可选, 单用户模式无需) |
| 分页 | `?limit=100&offset=0` |
| 错误格式 | `{"detail": "error message", "code": "ERROR_CODE"}` |
| 多租户 | `X-Tenant-ID` header (可选) |
| 流式 | `?stream=true` (SSE 响应) |

## 总端点统计

```bash
# 统计所有 API 端点
find aiPlat-core/core/api/routers -name '*.py' | \
  xargs grep -cEh '@router\.(get|post|put|delete|patch)' | \
  awk '{sum+=$0} END {print sum}'
# → ~842 端点
```
