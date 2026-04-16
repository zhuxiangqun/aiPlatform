# 🚀 核心层运维指南（To-Be 为主，As-Is 以代码事实为准）

> 说明：本文档多数内容为平台化部署/运维的 To-Be 示例（PostgreSQL/Redis/K8s 等）。当前仓库是否包含对应部署工件需以实际 ops 仓库为准。  
> As-Is：核心服务入口参见 `core/server.py`。统一口径参见 [`ARCHITECTURE_STATUS.md`](../../ARCHITECTURE_STATUS.md)。

> aiPlat-core - 部署运维与监控配置

---

## 🎯 运维关注点

作为核心层运维，您需要了解：
- **Agent/Skill 管理**：如何管理智能体和技能
- **编排引擎监控**：如何监控工作流执行
- **性能调优**：如何优化核心层性能
- **故障排查**：如何排查和解决问题

---

## 🚀 部署配置

### 环境要求

| 组件 | 版本要求 | 用途 | 备注 |
|------|----------|------|------|
| Python | 3.10+ | 运行环境 | 必须 |
| PostgreSQL | 13+ | 数据库 | To-Be |
| Redis | 6+ | 缓存/编排状态 | To-Be |
| Milvus | 2.0+ | 向量数据库 | 可选 |

---

### 部署方式

#### 单机部署（开发/测试）

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB |

**启动命令**：
```bash
# 安装依赖
pip install -e .

# To-Be：初始化数据库/迁移（当前仓库未必提供）
# make db-migrate

# As-Is：以 `core/server.py` 为主要入口（uvicorn 启动方式与配置以实际部署为准）

---

## 证据索引（Evidence Index｜抽样）

- 服务入口：`core/server.py`
```

---

#### 集群部署（生产）

| 服务 | 实例数 | 资源配置 | 说明 |
|------|--------|----------|------|
| core | 3+ | 4核/8GB | 核心能力，可水平扩展 |
| PostgreSQL | 主从 | 8核/16GB | 数据库，主从复制 |
| Redis | 3 节点 | 2核/8GB | 编排状态存储 |

---

#### 容器化部署

**Docker 镜像**：
```bash
# 构建镜像
docker build -t ai-platform/core:latest -f Dockerfile.core .

# 运行容器
docker run -d \
  --name ai-platform-core \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  -p 8001:8000 \
  ai-platform/core:latest
```

**Kubernetes 配置**：
```yaml
# deploy/k8s/core.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-platform-core
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: core
        image: ai-platform/core:latest
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ai-platform-secrets
              key: database-url
```

---

### 配置文件

**主配置文件**：`config/core/settings.yaml`

```yaml
# config/core/settings.yaml
core:
  agents:
    registry_file: config/core/agents.yaml
    max_concurrent: 10
    timeout: 300
  
  skills:
    registry_file: config/core/skills.yaml
    max_concurrent: 20
    timeout: 60
  
  orchestration:
    engine: langgraph
    max_steps: 100
    checkpoint_enabled: true
  
  memory:
    short_term:
      backend: redis
      ttl: 3600
    long_term:
      backend: postgresql
  
  knowledge:
    vector_store: milvus
    embedding_model: text-embedding-3-small
  
  logging:
    level: INFO
    format: json
```

**环境变量**：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `CORE_CONFIG` | 配置文件路径 | `config/core/settings.yaml` |
| `DATABASE_URL` | 数据库连接字符串 | - |
| `REDIS_URL` | Redis 连接字符串 | - |
| `MILVUS_HOST` | Milvus 主机 | `localhost` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 📊 监控

### 监控架构

```
┌─────────────────┐
│  Core Service   │
│  /metrics       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Prometheus     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Grafana        │
└─────────────────┘
```

---

### 关键指标

#### Agent 指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `agent_executions_total` | Agent 执行总数 | - | - | - |
| `agent_execution_duration_seconds` | Agent 执行耗时 | < 30s | > 60s | > 120s |
| `agent_execution_success_rate` | Agent 成功率 | > 95% | < 90% | < 80% |
| `agent_active_count` | 活跃 Agent 数 | < 10 | > 50 | > 100 |

#### Skill 指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `skill_calls_total` | Skill 调用总数 | - | - | - |
| `skill_call_duration_seconds` | Skill 调用耗时 | < 10s | > 30s | > 60s |
| `skill_call_success_rate` | Skill 成功率 | > 95% | < 90% | < 80% |
| `skill_timeout_count` | Skill 超时次数 | < 5/min | > 10/min | > 20/min |

#### 编排指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `workflow_executions_total` | 工作流执行总数 | - | - | - |
| `workflow_execution_duration_seconds` | 工作流执行耗时 | < 60s | > 120s | > 300s |
| `workflow_step_count` | 工作流步骤数 | < 20 | > 50 | > 100 |
| `workflow_checkpoint_size` | 检查点大小 | < 1MB | > 5MB | > 10MB |

#### 记忆指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `memory_store_size_bytes` | 记忆存储大小 | < 1GB | > 5GB | > 10GB |
| `memory_retrieval_duration_seconds` | 记忆检索耗时 | < 0.5s | > 1s | > 2s |
| `memory_hit_rate` | 记忆命中率 | > 60% | < 40% | < 20% |

#### 模型指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `model_calls_total` | 模型调用总数 | - | - | - |
| `model_call_duration_seconds` | 模型调用耗时 | < 5s | > 10s | > 30s |
| `model_tokens_total` | Token 使用总量 | - | - | - |
| `model_error_rate` | 模型错误率 | < 1% | > 5% | > 10% |

#### 系统指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `cpu_usage_percent` | CPU 使用率 | < 50% | > 70% | > 90% |
| `memory_usage_percent` | 内存使用率 | < 60% | > 80% | > 95% |
| `goroutine_count` | 协程/线程数 | < 100 | > 500 | > 1000 |

---

### 告警规则

**告警配置文件**：`deploy/prometheus/alerts-core.yaml`

```yaml
groups:
  - name: core-alerts
    rules:
      - alert: AgentExecutionSlow
        expr: histogram_quantile(0.99, agent_execution_duration_seconds) > 60
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Agent 执行耗时过高"
          
      - alert: AgentSuccessRateLow
        expr: agent_execution_success_rate < 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Agent 成功率过低"
```

---

### Grafana 仪表盘

| 仪表盘 | Dashboard ID | 说明 |
|--------|--------------|------|
| Core Overview | `core-overview` | 核心层总览 |
| Agent Performance | `core-agents` | Agent 性能监控 |
| Skill Performance | `core-skills` | Skill 性能监控 |
| Workflow Performance | `core-workflows` | 工作流性能监控 |

---

## 🔧 维护

### Agent 管理

**查看 Agent 状态**：
```bash
# 查看所有 Agent
aiplat agent list

# 查看特定 Agent
aiplat agent show <agent-name>

# 查看 Agent 执行历史
aiplat agent history <agent-name> --limit 100
```

**启用/禁用 Agent**：
```bash
# 禁用 Agent
aiplat agent disable <agent-name>

# 启用 Agent
aiplat agent enable <agent-name>

# 重新加载 Agent 配置
aiplat agent reload <agent-name>
```

**清理 Agent 状态**：
```bash
# 清理过期的 Agent 状态
aiplat agent cleanup --older-than 7d

# 清理失败的 Agent 执行记录
aiplat agent cleanup --status failed --older-than 1d
```

---

### Skill 管理

**查看 Skill 状态**：
```bash
# 查看所有 Skill
aiplat skill list

# 查看特定 Skill
aiplat skill show <skill-name>

# 查看 Skill 执行统计
aiplat skill stats <skill-name>
```

**注册/注销 Skill**：
```bash
# 注册 Skill
aiplat skill register <skill-file.yaml>

# 注销 Skill
aiplat skill unregister <skill-name>

# 更新 Skill
aiplat skill update <skill-name> <skill-file.yaml>
```

---

### 编排管理

**查看工作流状态**：
```bash
# 查看运行中的工作流
aiplat workflow list --status running

# 查看工作流详情
aiplat workflow show <workflow-id>

# 查看工作流步骤
aiplat workflow steps <workflow-id>
```

**管理工作流**：
```bash
# 暂停工作流
aiplat workflow pause <workflow-id>

# 恢复工作流
aiplat workflow resume <workflow-id>

# 取消工作流
aiplat workflow cancel <workflow-id>

# 重试失败的工作流
aiplat workflow retry <workflow-id>
```

**清理检查点**：
```bash
# 查看检查点大小
aiplat workflow checkpoints --size

# 清理过期检查点
aiplat workflow cleanup-checkpoints --older-than 7d

# 压缩检查点
aiplat workflow compact-checkpoints
```

---

### 记忆管理

**查看记忆状态**：
```bash
# 查看记忆存储大小
aiplat memory stats

# 查看短期记忆
aiplat memory list --type short-term

# 查看长期记忆
aiplat memory list --type long-term
```

**清理记忆**：
```bash
# 清理过期记忆
aiplat memory cleanup --expired

# 清理特定用户的记忆
aiplat memory cleanup --user <user-id>

# 压缩记忆存储
aiplat memory compact
```

---

### 日志管理

**日志格式规范**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `timestamp` | ISO8601 | 是 | 日志时间 |
| `level` | string | 是 | 日志级别 |
| `service` | string | 是 | 服务名称 |
| `trace_id` | string | 是 | 追踪ID |
| `agent_id` | string | 否 | Agent ID |
| `skill_id` | string | 否 | Skill ID |
| `message` | string | 是 | 日志内容 |
| `duration_ms` | int | 否 | 耗时(ms) |

**日志文件位置**：

| 文件 | 路径 | 说明 |
|------|------|------|
| 核心日志 | `/var/log/ai-platform/core.log` | 核心层主日志 |
| Agent 日志 | `/var/log/ai-platform/agents.log` | Agent 执行日志 |
| Skill 日志 | `/var/log/ai-platform/skills.log` | Skill 调用日志 |
| 编排日志 | `/var/log/ai-platform/orchestration.log` | 工作流执行日志 |

**日志查询**：
```bash
# 查询最近 Agent 错误
grep '"level":"ERROR"' /var/log/ai-platform/agents.log | tail -50

# 查询特定 trace_id 的日志
grep '"trace_id":"abc-123"' /var/log/ai-platform/*.log

# 统计 Agent 执行次数
grep '"agent_id"' /var/log/ai-platform/agents.log | wc -l
```

---

## 🐛 故障排查

### 排查流程

```
发现问题 → 确认影响范围 → 查看监控指标 → 分析日志 → 定位根因 → 执行恢复 → 记录复盘
```

---

### 常见问题排查

#### Agent 执行失败

**现象**：Agent 执行返回错误，成功率下降

**排查命令**：
```bash
# 1. 检查 Agent 配置
aiplat agent show <agent-name> --config

# 2. 查看最近错误日志
grep '"level":"ERROR"' /var/log/ai-platform/agents.log | tail -50

# 3. 检查依赖服务
curl http://localhost:8000/health
redis-cli ping

# 4. 检查模型连接
aiplat model test --provider <provider-name>

# 5. 查看 Agent 执行详情
aiplat agent history <agent-name> --limit 10 --verbose
```

**常见原因与解决**：

| 原因 | 解决方案 |
|------|----------|
| 模型调用失败 | 检查 API 密钥、配额、网络 |
| 超时 | 增加超时配置、优化执行逻辑 |
| 内存不足 | 扩容内存、减少并发 |
| 依赖服务不可用 | 检查服务状态、重启服务 |

---

#### Skill 调用超时

**现象**：Skill 调用耗时过长，超时错误增加

**排查命令**：
```bash
# 1. 查看超时配置
aiplat config get skill.timeout

# 2. 查看 Skill 执行统计
aiplat skill stats <skill-name> --duration 1h

# 3. 检查外部服务响应时间
curl -w "%{time_total}" http://external-service/health

# 4. 查看并发情况
redis-cli info stats | grep connected_clients

# 5. 检查网络延迟
ping <external-service-host>
```

**解决步骤**：
1. 增加超时配置：`config/core/skills.yaml` 中修改 `timeout`
2. 优化 Skill 执行逻辑
3. 增加并发限制
4. 使用异步执行

---

#### 工作流执行卡住

**现象**：工作流长时间无进展，步骤不执行

**排查命令**：
```bash
# 1. 查看工作流状态
aiplat workflow show <workflow-id> --verbose

# 2. 查看检查点状态
aiplat workflow checkpoints <workflow-id>

# 3. 检查 Redis 连接
redis-cli ping

# 4. 查看编排引擎日志
grep '"level":"ERROR"' /var/log/ai-platform/orchestration.log | tail -50

# 5. 检查步骤执行状态
aiplat workflow steps <workflow-id> --status pending
```

**解决步骤**：
1. 检查是否有阻塞步骤
2. 检查 Redis 是否可用
3. 重试工作流：`aiplat workflow retry <workflow-id>`
4. 如必要，取消并重新执行

---

#### 记忆检索慢

**现象**：记忆检索延迟超过正常值

**排查命令**：
```bash
# 1. 检查记忆存储大小
aiplat memory stats

# 2. 检查数据库查询性能
psql "$DATABASE_URL" -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 3. 检查索引状态
psql "$DATABASE_URL" -c "\d+ memory_table"

# 4. 检查 Redis 内存
redis-cli info memory

# 5. 检查向量索引状态
# (Milvus 命令)
```

**解决步骤**：
1. 清理过期记忆
2. 优化数据库索引
3. 增加 Redis 内存
4. 优化向量索引

---

### 健康检查

**健康检查端点**：

| 端点 | 路径 | 说明 |
|------|------|------|
| 健康检查 | `GET /health` | 整体健康状态 |
| 就绪检查 | `GET /ready` | 服务是否就绪 |
| 组件检查 | `GET /health/components` | 各组件状态 |

**健康检查命令**：
```bash
# 检查核心服务健康状态
curl http://localhost:8001/health

# 检查各组件状态
curl http://localhost:8001/health/components | jq .

# 预期响应
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "milvus": "healthy",
    "agents": "healthy"
  }
}
```

---

### 紧急恢复

| 场景 | 操作 | 预计恢复时间 |
|------|------|--------------|
| 核心服务无响应 | `systemctl restart ai-platform-core` | 30秒 |
| Agent 全部失败 | 检查模型配置，切换备用提供商 | 5分钟 |
| 工作流全部卡住 | 清理 Redis 检查点，重启服务 | 2分钟 |
| 记忆存储损坏 | 从备份恢复，重建索引 | 15分钟 |
| Redis 不可用 | 重启 Redis，恢复检查点 | 1分钟 |

---

## 📦 备份与恢复

### 备份策略

| 数据类型 | 备份频率 | 保留时长 | 备份方式 |
|----------|----------|----------|----------|
| Agent 配置 | 每次变更 | 永久 | Git |
| Skill 配置 | 每次变更 | 永久 | Git |
| 工作流检查点 | 每小时 | 7天 | Redis RDB |
| 记忆数据 | 每天 | 30天 | PostgreSQL |

### 备份命令

```bash
# 备份 Agent 配置
aiplat agent export > agents_backup_$(date +%Y%m%d).yaml

# 备份 Skill 配置
aiplat skill export > skills_backup_$(date +%Y%m%d).yaml

# 备份工作流检查点
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb /backup/redis_core_$(date +%Y%m%d).rdb

# 备份记忆数据
pg_dump -h localhost -U ai_platform ai_platform_db > core_backup_$(date +%Y%m%d).sql
```

### 恢复命令

```bash
# 恢复 Agent 配置
aiplat agent import < agents_backup.yaml

# 恢复 Skill 配置
aiplat skill import < skills_backup.yaml

# 恢复工作流检查点
systemctl stop redis
cp /backup/redis_core_20260409.rdb /var/lib/redis/dump.rdb
systemctl start redis

# 恢复记忆数据
psql -h localhost -U ai_platform ai_platform_db < core_backup_20260409.sql
```

---

## 🔗 相关链接

- [← 返回核心层文档](../index.md)
- [架构师指南 →](./architect/index.md)
- [开发者指南 →](./developer/index.md)

---

*最后更新: 2026-04-14*
