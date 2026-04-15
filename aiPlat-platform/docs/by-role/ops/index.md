# 🚀 平台层运维指南

> aiPlat-platform - 部署运维与监控配置

---

## 🎯 运维关注点

作为平台层运维，您需要了解：
- **API 服务管理**：如何管理 API 服务
- **认证服务维护**：如何维护认证系统
- **限流和熔断配置**：如何配置限流和熔断
- **故障排查**：如何排查和解决问题

---

## 🚀 部署配置

### 环境要求

| 组件 | 版本要求 | 用途 | 备注 |
|------|----------|------|------|
| Python | 3.10+ | 运行环境 | 必须 |
| PostgreSQL | 13+ | 数据库 | 必须 |
| Redis | 6+ | 缓存/会话 | 必须 |
| RabbitMQ | 3.9+ | 消息队列 | 可选 |
| Nginx | 1.20+ | 反向代理 | 生产必须 |

---

### 部署方式

#### 单机部署（开发/测试）

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 2核 | 4核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB |

**启动命令**：
```bash
# 安装依赖
pip install -e .

# 初始化数据库
make db-migrate

# 启动服务
uvicorn platform.main:app --host 0.0.0.0 --port 8000

# 或使用 Make
make run-platform
```

---

#### 集群部署（生产）

| 服务 | 实例数 | 资源配置 | 说明 |
|------|--------|----------|------|
| platform | 3+ | 4核/8GB | API 服务，可水平扩展 |
| PostgreSQL | 主从 | 8核/16GB | 数据库，主从复制 |
| Redis | 3节点 | 2核/8GB | 缓存/会话，哨兵模式 |
| RabbitMQ | 3节点 | 2核/4GB | 消息队列，镜像队列 |
| Nginx | 2+ | 2核/4GB | 负载均衡 |

---

#### 容器化部署

**Docker Compose**：
```yaml
# deploy/docker-compose.yaml
version: '3.8'
services:
  platform:
    image: ai-platform/platform:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...
      - RABBITMQ_URL=amqp://...
    depends_on:
      - postgres
      - redis
      - rabbitmq
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

**Kubernetes**：
```yaml
# deploy/k8s/platform.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-platform-platform
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: platform
        image: ai-platform/platform:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

### 配置文件

**主配置文件**：`config/platform/settings.yaml`

```yaml
# config/platform/settings.yaml
platform:
  api:
    host: 0.0.0.0
    port: 8000
    workers: 4
    timeout: 60
  
  auth:
    jwt_secret: ${JWT_SECRET}
    jwt_algorithm: HS256
    jwt_expire_minutes: 60
    refresh_expire_days: 7
  
  rate_limit:
    enabled: true
    requests_per_minute: 100
    burst: 20
  
  cors:
    allowed_origins:
      - http://localhost:3000
      - https://app.example.com
  
  logging:
    level: INFO
    format: json
```

**限流配置**：`config/platform/rate_limit.yaml`

```yaml
# config/platform/rate_limit.yaml
rate_limit:
  default:
    requests_per_minute: 100
    burst: 20
  
  authenticated:
    requests_per_minute: 200
    burst: 50
  
  premium:
    requests_per_minute: 1000
    burst: 200
```

**环境变量**：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `PLATFORM_CONFIG` | 配置文件路径 | `config/platform/settings.yaml` |
| `DATABASE_URL` | 数据库连接字符串 | - |
| `REDIS_URL` | Redis 连接字符串 | - |
| `JWT_SECRET` | JWT 密钥 | - |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 📊 监控

### 关键指标

#### API 指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `http_requests_total` | HTTP 请求总数 | - | - | - |
| `http_request_duration_seconds` | HTTP 请求耗时 | < 200ms | > 500ms | > 1s |
| `http_request_errors_total` | HTTP 错误总数 | < 0.1% | > 1% | > 5% |
| `http_requests_in_flight` | 正在处理的请求 | < 100 | > 500 | > 1000 |
| `api_response_size_bytes` | API 响应大小 | < 100KB | > 1MB | > 10MB |

#### 认证指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `auth_success_total` | 认证成功次数 | - | - | - |
| `auth_failure_total` | 认证失败次数 | < 10/min | > 50/min | > 100/min |
| `auth_token_issued_total` | 令牌签发次数 | - | - | - |
| `auth_session_active_count` | 活跃会话数 | < 1000 | > 5000 | > 10000 |

#### 租户指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `tenant_count_total` | 租户总数 | - | - | - |
| `tenant_request_total` | 租户请求次数 | - | - | - |
| `tenant_quota_usage_percent` | 配额使用率 | < 70% | > 85% | > 95% |
| `tenant_resource_usage_bytes` | 资源使用量 | - | - | - |

#### 消息队列指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `mq_messages_published_total` | 消息发布总数 | - | - | - |
| `mq_messages_consumed_total` | 消息消费总数 | - | - | - |
| `mq_queue_depth` | 队列深度 | < 1000 | > 5000 | > 10000 |
| `mq_message_processing_seconds` | 消息处理耗时 | < 1s | > 5s | > 10s |

#### 限流指标

| 指标名称 | 说明 | 正常范围 | 警告阈值 | 严重阈值 |
|----------|------|----------|----------|----------|
| `rate_limit_requests_total` | 限流请求总数 | - | - | - |
| `rate_limit_rejected_total` | 被拒绝请求 | < 10/min | > 50/min | > 100/min |
| `rate_limit_burst_triggered_total` | 触发突发限制 | < 5/min | > 20/min | > 50/min |

---

### 告警规则

**告警配置文件**：`deploy/prometheus/alerts-platform.yaml`

```yaml
groups:
  - name: platform-alerts
    rules:
      - alert: HighAPIErrorRate
        expr: rate(http_request_errors_total[5m]) > 0.01
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "API 错误率过高"
          
      - alert: HighAPILatency
        expr: histogram_quantile(0.99, http_request_duration_seconds) > 0.5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "API 响应延迟过高"
          
      - alert: HighAuthFailureRate
        expr: rate(auth_failure_total[5m]) > 10
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "认证失败率过高"
          
      - alert: MessageQueueBacklog
        expr: mq_queue_depth > 5000
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "消息队列积压过多"
```

---

### Grafana 仪表盘

| 仪表盘 | Dashboard ID | 说明 |
|--------|--------------|------|
| Platform Overview | `platform-overview` | 平台层总览 |
| API Performance | `platform-api` | API 性能监控 |
| Auth Metrics | `platform-auth` | 认证指标监控 |
| Rate Limit | `platform-rate-limit` | 限流监控 |
| Message Queue | `platform-mq` | 消息队列监控 |

---

## 🔧 维护

### API 管理

**查看 API 状态**：
```bash
# 检查 API 健康状态
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs

# 查看 OpenAPI 规范
curl http://localhost:8000/openapi.json
```

**查看 API 指标**：
```bash
# 查看 Prometheus 指标
curl http://localhost:8000/metrics

# 查看实时请求
tail -f /var/log/ai-platform/platform.log | grep '"method"'
```

---

### 认证管理

**查看认证状态**：
```bash
# 查看活跃会话
redis-cli keys "session:*" | wc -l

# 查看令牌统计
aiplat auth stats --duration 1h

# 查看认证失败
grep '"auth":"failure"' /var/log/ai-platform/platform.log | tail -50
```

**清理过期会话**：
```bash
# 清理过期会话
aiplat auth cleanup-sessions --expired

# 清理过期令牌
aiplat auth cleanup-tokens --expired
```

---

### 限流管理

**查看限流状态**：
```bash
# 查看限流配置
aiplat rate-limit show

# 查看当前限流状态
aiplat rate-limit status

# 查看被限流的客户端
aiplat rate-limit blocked-clients
```

**调整限流配置**：
```bash
# 临时调整限流
aiplat rate-limit set --limit 200 --burst 50

# 永久调整限流（修改配置文件）
vi config/platform/rate_limit.yaml
systemctl restart ai-platform-platform
```

**重置限流计数**：
```bash
# 重置所有限流计数
aiplat rate-limit reset

# 重置特定客户端的限流
aiplat rate-limit reset --client <client-id>
```

---

### 消息队列管理

**查看队列状态**：
```bash
# 查看 RabbitMQ 队列状态
rabbitmqctl list_queues name messages consumers

# 查看队列深度
aiplat mq queue-depth

# 查看消费者状态
aiplat mq consumers
```

**清理队列**：
```bash
# 清理死信队列
aiplat mq purge --queue dlq

# 清理积压消息
aiplat mq purge --queue <queue-name>

# 重新入队消息
aiplat mq requeue --queue <queue-name>
```

---

### 租户管理

**查看租户状态**：
```bash
# 查看所有租户
aiplat tenant list

# 查看租户详情
aiplat tenant show <tenant-id>

# 查看租户资源使用
aiplat tenant usage <tenant-id>
```

**调整租户配额**：
```bash
# 查看当前配额
aiplat tenant quota <tenant-id>

# 调整配额
aiplat tenant quota <tenant-id> --requests 10000 --storage 100GB
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
| `request_id` | string | 是 | 请求ID |
| `user_id` | string | 否 | 用户ID |
| `tenant_id` | string | 否 | 租户ID |
| `method` | string | 是 | HTTP方法 |
| `path` | string | 是 | 请求路径 |
| `status_code` | int | 是 | 状态码 |
| `duration_ms` | int | 是 | 耗时(ms) |

**日志文件位置**：

| 文件 | 路径 | 说明 |
|------|------|------|
| 平台日志 | `/var/log/ai-platform/platform.log` | 平台层主日志 |
| API 日志 | `/var/log/ai-platform/api.log` | API 请求日志 |
| 认证日志 | `/var/log/ai-platform/auth.log` | 认证相关日志 |
| 审计日志 | `/var/log/ai-platform/audit.log` | 操作审计日志 |

**日志查询**：
```bash
# 查询最近错误
grep '"level":"ERROR"' /var/log/ai-platform/platform.log | tail -50

# 查询特定请求
grep '"request_id":"abc-123"' /var/log/ai-platform/*.log

# 统计状态码分布
grep '"status_code"' /var/log/ai-platform/api.log | jq .status_code | sort | uniq -c

# 查询慢请求（> 1s）
grep '"duration_ms"' /var/log/ai-platform/api.log | jq 'select(.duration_ms > 1000)'
```

---

## 🐛 故障排查

### 排查流程

```
发现问题 → 确认影响范围 → 查看监控仪表盘 → 分析日志 → 定位根因 → 执行恢复 → 记录复盘
```

---

### 常见问题排查

#### API 响应慢

**现象**：API 响应时间超过正常值

**排查命令**：
```bash
# 1. 检查系统资源
top
free -h

# 2. 检查慢查询
psql "$DATABASE_URL" -c \
  "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 3. 检查缓存命中率
redis-cli INFO stats | grep keyspace

# 4. 查看慢请求日志
grep '"duration_ms"' /var/log/ai-platform/api.log | jq 'select(.duration_ms > 1000)'

# 5. 检查并发连接
netstat -an | grep ESTABLISHED | wc -l
```

**常见原因与解决**：

| 原因 | 解决方案 |
|------|----------|
| 数据库慢查询 | 添加索引、优化查询 |
| 缓存未命中 | 增加缓存 TTL、预热缓存 |
| 并发过高 | 增加实例、启用限流 |
| 资源不足 | 扩容、优化资源使用 |

---

#### 认证失败

**现象**：大量认证失败或用户无法登录

**排查命令**：
```bash
# 1. 检查认证日志
grep '"auth":"failure"' /var/log/ai-platform/auth.log | tail -50

# 2. 检查 Redis 连接
redis-cli ping

# 3. 检查 JWT 配置
aiplat auth config show

# 4. 检查令牌状态
aiplat auth token verify <token>

# 5. 检查会话存储
redis-cli keys "session:*" | head -10
```

**常见原因与解决**：

| 原因 | 解决方案 |
|------|----------|
| JWT 密钥配置错误 | 检查 JWT_SECRET 环境变量 |
| Redis 连接失败 | 检查 Redis 服务状态 |
| 令牌过期 | 刷新令牌或重新登录 |
| 密码错误 | 检查密码策略、重置密码 |

---

#### 限流误杀

**现象**：正常用户被限流阻止

**排查命令**：
```bash
# 1. 查看被限流的客户端
aiplat rate-limit blocked-clients

# 2. 查看限流日志
grep '"rate_limit":"rejected"' /var/log/ai-platform/platform.log | tail -50

# 3. 检查限流配置
aiplat rate-limit show

# 4. 检查客户端请求频率
grep '"client_id":"<client-id>"' /var/log/ai-platform/api.log | tail -100
```

**解决步骤**：
1. 临时放行客户端：`aiplat rate-limit unblock <client-id>`
2. 调整限流配置
3. 添加白名单

---

#### 消息队列积压

**现象**：消息处理延迟，队列深度增加

**排查命令**：
```bash
# 1. 查看队列深度
rabbitmqctl list_queues name messages consumers

# 2. 查看消费者状态
aiplat mq consumers

# 3. 检查错误消息
grep '"level":"ERROR"' /var/log/ai-platform/mq.log | tail -50

# 4. 检查消费者日志
journalctl -u ai-platform-platform | grep consumer

# 5. 检查资源使用
top
```

**解决步骤**：
1. 增加消费者数量
2. 优化消息处理逻辑
3. 清理死信队列
4. 扩容服务实例

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
# 检查平台服务健康状态
curl http://localhost:8000/health

# 检查各组件状态
curl http://localhost:8000/health/components | jq .

# 预期响应
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "rabbitmq": "healthy",
    "auth": "healthy"
  }
}
```

---

### 紧急恢复

| 场景 | 操作 | 预计恢复时间 |
|------|------|--------------|
| API 服务无响应 | `systemctl restart ai-platform-platform` | 30秒 |
| 认证服务失败 | 检查 Redis，重启认证服务 | 1分钟 |
| 限流过严 | 临时调整限流配置 | 30秒 |
| 消息队列积压 | 增加消费者或清理队列 | 5分钟 |
| 数据库连接池耗尽 | 重启服务，增加连接池配置 | 1分钟 |

---

## 📦 备份与恢复

### 备份策略

| 数据类型 | 备份频率 | 保留时长 | 备份方式 |
|----------|----------|----------|----------|
| 用户数据 | 每天 2:00 | 30天 | `pg_dump` |
| 会话数据 | 每小时 | 7天 | Redis RDB |
| 配置文件 | 每次变更 | 永久 | Git |
| 审计日志 | 实时 | 90天 | 日志收集 |

### 备份命令

```bash
# 备份数据库
pg_dump -h localhost -U ai_platform ai_platform_db > platform_backup_$(date +%Y%m%d).sql

# 备份 Redis
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb /backup/redis_platform_$(date +%Y%m%d).rdb

# 备份配置
tar -czf config_$(date +%Y%m%d).tar.gz config/
```

### 恢复命令

```bash
# 恢复数据库
systemctl stop ai-platform-platform
psql -h localhost -U ai_platform ai_platform_db < platform_backup_20260409.sql
systemctl start ai-platform-platform

# 恢复 Redis
systemctl stop redis
cp /backup/redis_platform_20260409.rdb /var/lib/redis/dump.rdb
systemctl start redis
```

---

## 🔗 相关链接

- [← 返回平台层文档](../index.md)
- [架构师指南 →](./architect/index.md)
- [开发者指南 →](./developer/index.md)

---

*最后更新: 2026-04-09*