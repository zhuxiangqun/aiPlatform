# 🚀 运维指南

> aiPlatform - 部署运维与监控配置

---

## 🎯 运维关注点

作为运维，您需要了解：
- **如何部署**：如何部署和配置系统
- **如何监控**：如何配置监控和告警
- **如何维护**：如何维护和升级系统
- **故障排查**：如何排查和解决问题

---

## 🚀 部署

### 部署架构

aiPlatform 支持三种部署方式：

#### 单机部署（开发/测试）

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB |

**服务组件**（全部运行在同一主机）：
- aiPlat-app（Gateway + Web UI）
- aiPlat-platform（API 服务）
- aiPlat-core（核心能力）
- aiPlat-infra（基础设施代理）
- PostgreSQL / Redis / Milvus（依赖服务）

**启动命令**：
```bash
# 使用 Docker Compose 启动
docker-compose up -d

# 或使用 Make 命令
make deploy-single
```

---

#### 集群部署（生产）

| 服务 | 实例数 | 资源配置 | 说明 |
|------|--------|----------|------|
| aiPlat-platform | 3+ | 4核/8GB | API 服务，可水平扩展 |
| aiPlat-core | 3+ | 4核/8GB | 核心能力，可水平扩展 |
| aiPlat-app (Gateway) | 2+ | 2核/4GB | 网关服务，可水平扩展 |
| PostgreSQL | 主从 | 8核/16GB + 100GB SSD | 数据库，主从复制 |
| Redis | 3 节点集群 | 2核/8GB | 缓存，哨兵模式 |
| Milvus | 3 节点 | 8核/32GB + 200GB | 向量数据库，集群模式 |

**集群拓扑**：
```
                        用户请求
                           │
                    ┌──────▼──────┐
                    │Load Balancer│
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │ Gateway-1   │   │ Gateway-2   │   │ Gateway-3   │  ← Layer 3 (app)
  │ (消息网关)  │   │ (消息网关)  │   │ (消息网关)  │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │ Platform-1  │   │ Platform-2  │   │ Platform-3  │  ← Layer 2
  │ (API 网关)  │   │ (API 网关)  │   │ (API 网关)  │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                    ┌──────▼──────┐
                    │ Core Cluster│  ← Layer 1
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │ PostgreSQL  │   │   Redis     │   │   Milvus    │  ← Layer 0
  │  Cluster    │   │  Cluster    │   │  Cluster    │
  └─────────────┘   └─────────────┘   └─────────────┘
```

**调用链说明**：
- 消息网关（Layer 3）：负责渠道适配、消息格式转换、协议转换
- API 网关（Layer 2）：负责认证授权、限流熔断、路由分发、负载均衡
- 所有安全策略在 API 网关统一实施

---

#### 容器化部署

| 方式 | 配置文件位置 | 启动命令 |
|------|--------------|----------|
| Docker Compose | `deploy/docker-compose.yaml` | `docker-compose up -d` |
| Kubernetes | `deploy/k8s/` | `kubectl apply -f deploy/k8s/` |
| Helm Chart | `deploy/helm/ai-platform/` | `helm install ai-platform ./deploy/helm` |

**Docker 镜像**：
| 镜像 | 说明 |
|------|------|
| `ai-platform/platform:latest` | 平台服务 |
| `ai-platform/core:latest` | 核心能力 |
| `ai-platform/gateway:latest` | 网关服务 |
| `ai-platform/infra:latest` | 基础设施代理 |

**Kubernetes 资源配置**：
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
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
```

---

### 环境配置对照表

| 配置项 | 开发环境 | 测试环境 | 生产环境 |
|--------|----------|----------|----------|
| 数据库 | SQLite / 内PostgreSQL | 测试 PostgreSQL | 生产 PostgreSQL 集群 |
| LLM | Mock LLM | 测试 API（配额有限） | 生产 API + 备用 |
| 日志级别 | DEBUG | INFO | WARNING |
| 认证 |跳过/测试密钥 | 测试密钥 | OAuth2 + JWT |
| 限流 | 无 | 宽松（1000/min） | 严格（100/min） |
| 缓存 | 本地内存 | Redis 单节点 | Redis 集群 |
| 向量存储 | FAISS 本地 | Milvus 单节点 | Milvus 集群 |
| 监控 | 无 | Prometheus + Grafana | 完整监控栈 |

---

### 配置管理

**配置文件位置**：
| 配置类型 | 文件位置 | 说明 |
|----------|----------|------|
| 主配置 | `config/settings.yaml` | 系统主配置 |
| 环境配置 | `config/environments/{env}.yaml` | 环境特定配置 |
| 密钥配置 | 环境变量 / Vault | 敏感配置 |

**配置优先级**（高到低）：
1. 环境变量
2. 密钥管理服务（Vault / K8s Secrets）
3. 环境配置文件
4. 默认配置文件

---

## 📊 容量规划

### 扩容阈值

| 指标 | 扩容阈值 | 扩容建议 | 说明 |
|------|----------|----------|------|
| API 响应时间(P99) | > 1s 持续 5 分钟 | 增加 platform 实例 | 单实例支持约 100 QPS |
| CPU 使用率 | > 70% 持续 10 分钟 | 增加实例或升级配置 | 建议预留 30% 余量 |
| 内存使用率 | > 80% 持续 10 分钟 | 增加实例或升级配置 | 建议预留 20% 余量 |
| 数据库连接数 | > 80% 上限 | 增加连接池或数据库实例 | 监控连接池使用率 |
| 缓存命中率 | < 70% | 增加缓存容量或优化缓存策略 | 缓存命中率应 > 80% |
| LLM 调用延迟 | > 10s 持续 5 分钟 | 增加并发数或切换提供商 | 考虑降级策略 |

### 容量计算公式

| 组件 | 计算公式 | 说明 |
|------|----------|------|
| Platform 实例数 | QPS / 100 | 单实例预估支持 100 QPS |
| Core 实例数 | Agent 调用数 / 50 | 单实例预估支持 50 并发 Agent |
| 数据库存储 | 日增数据量 × 30 天 | 保留 30 天数据 |
| 日志存储 | 日增日志 × 30 天 × 2 | 保留 30 天 + 1 倍缓冲 |
| Redis 内存 | 数据量 × 1.5 | 数据量 + 50% 缓冲 |

### 扩容操作示例

**水平扩容 Platform**：
```bash
# Kubernetes 扩容
kubectl scale deployment ai-platform-platform --replicas=5

# Docker Compose 扩容
docker-compose up -d --scale platform=5
```

**垂直扩容数据库**：
```bash
# 增加数据库实例配置
# 修改 deploy/k8s/database.yaml
# resources.requests.memory: "16Gi"
# resources.requests.cpu: "8"
```

---

## 🔒 安全加固

### 网络安全

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| API 访问 | 仅内网或 VPN | 不直接暴露公网 |
| 管理端口 | 限制 IP 白名单 | 仅运维 IP 可访问 |
| TLS | 启用 | 生产环境必须启用 HTTPS |
| 跨域配置 | 限制域名 | 仅允许指定域名 |

### 密钥管理

| 密钥类型 | 存储方式 | 轮换周期 | 说明 |
|----------|----------|----------|------|
| LLM API Key | Vault / K8s Secret | 90 天 | 定期轮换备用 Key |
| 数据库密码 | Vault / K8s Secret | 90 天 | 使用强密码策略 |
| JWT Secret | 环境变量 + Vault | 180 天 | 签发令牌密钥 |
| Redis 密码 | Vault / K8s Secret | 90 天 | 启用 Redis 认证 |
| 加密密钥 | Vault / HSM | 365 天 | 用于数据加密 |

### 安全配置检查

```bash
# 检查敏感配置是否硬编码
grep -r "api_key\|password\|secret" config/ --exclude="*.example"
# 预期：只在环境变量或密钥管理服务中配置

# 检查日志是否包含敏感信息
grep -r "password\|secret\|token" /var/log/ai-platform/
# 预期：无敏感信息输出

# 检查 TLS 配置
openssl s_client -connect localhost:8000 -showcerts
# 预期：证书有效、协议版本 >= TLS 1.2

# 检查数据库访问权限
psql -c "\du" | grep -v "^$" | wc -l
# 预期：仅必要的用户和角色
```

### 安全基线检查清单

| 检查项 | 频率 | 检查方式 |
|--------|------|----------|
| 系统补丁 | 月度 | `yum update --security` |
| 依赖漏洞 | 周度 | `safety check` / `npm audit` |
| 密钥轮换 | 季度 | 密钥管理系统检查 |
| 日志审计 | 日度 | 日志分析工具 |
| 权限审计 | 月度 | 数据库权限检查 |

---

## 📊 监控

### 监控架构

```
┌─────────────────┐┌─────────────────┐
│  应用服务││  基础设施       │
│/metrics         ││/metrics         │
└────────┬────────┘└────────┬────────┘
         │                   │
         └─────────┬─────────┘
                   │
         ┌────────▼────────┐
         │  Prometheus      │
         │  (采集+存储)     │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  Grafana         │
         │  (可视化)        │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │ AlertManager    │
         │  (告警)          │
         └─────────────────┘
```

---

### 指标采集方式

| 指标类型 | 采集工具 | 端点/方式 | 采集间隔 |
|----------|----------|-----------|----------|
| 系统指标 | Prometheus Node Exporter | :9100/metrics | 15s |
| 应用指标 | Prometheus | :8000/metrics | 15s |
| 业务指标 | 结构化日志 → Loki| 日志文件 | 实时 |
| LLM 调用 | 自定义指标 | 通过 API 上报 | 每次调用 |
| 数据库指标 | PostgreSQL Exporter | :9187/metrics | 15s |
| 缓存指标 | Redis Exporter | :9121/metrics | 15s |

---

### 关键指标与告警阈值

| 指标 | 正常范围 | 警告阈值 | 严重阈值 | 检查频率 |
|------|----------|----------|----------|----------|
| CPU 使用率 | < 50% | > 70% | > 90% | 1分钟 |
| 内存使用率 | < 60% | > 80% | > 95% | 1分钟 |
| 磁盘使用率 | < 60% | > 80% | > 90% | 5分钟 |
| API 响应时间(P99) | < 200ms | > 500ms | > 1s | 1分钟 |
| API 错误率 | < 0.1% | > 1% | > 5% | 1分钟 |
| LLM 调用延迟 | < 2s | > 5s | > 10s | 每次调用 |
| LLM 错误率 | < 1% | > 5% | > 10% | 1分钟 |
| 数据库连接数 | < 50 | > 80 | > 100 | 5分钟 |
| 数据库查询时间 | < 100ms | > 500ms | > 1s | 1分钟 |
| 缓存命中率 | > 80% | < 70% | < 50% | 5分钟 |
| Redis 内存使用 | < 70% | > 85% | > 95% | 5分钟 |

---

### 告警规则配置

**告警规则文件**：`deploy/prometheus/alerts.yaml`

**告警分级**：
| 级别 | 名称 | 触发条件 | 通知方式 | 响应时间 |
|------|------|----------|----------|----------|
| P0 | 紧急 | 严重阈值 | 电话+短信+邮件 | 5 分钟 |
| P1 | 警告 | 警告阈值 | 邮件+钉钉 | 30 分钟 |
| P2 | 提醒 | 异常但可自愈 | 日志记录 | 24 小时 |

**告警规则示例**：
```yaml
# deploy/prometheus/alerts.yaml
groups:
  - name: ai-platform-alerts
    rules:
      - alert: HighCPUUsage
        expr: cpu_usage > 70
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "CPU 使用率过高"
          
      - alert: HighMemoryUsage
        expr: memory_usage > 80
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "内存使用率过高"
```

---

### 可视化仪表盘

| 仪表盘 | Grafana Dashboard ID | 访问路径 | 说明 |
|--------|---------------------|----------|------|
| 系统总览 | `ai-platform-overview` | `/d/overview` | 系统整体状态 |
| API 性能 | `ai-platform-api` | `/d/api` | API 响应时间、错误率 |
| LLM 使用统计 | `ai-platform-llm` | `/d/llm` | LLM 调用次数、延迟、成本 |
| Agent 执行监控 | `ai-platform-agents` | `/d/agents` | Agent 执行状态、成功率 |
| 数据库监控 | `ai-platform-database` | `/d/database` | 数据库连接、查询性能 |
| 缓存监控 | `ai-platform-cache` | `/d/cache` | 缓存命中率、内存使用 |

---

## 🔧 维护

### 日志管理

#### 日志格式规范

所有日志采用结构化 JSON 格式：

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `timestamp` | ISO8601 | 是 | 日志时间 | `2026-04-09T10:30:00Z` |
| `level` | string | 是 | 日志级别 | `INFO` |
| `service` | string | 是 | 服务名称 | `ai-platform-platform` |
| `trace_id` | string | 是 | 分布式追踪 ID | `abc-123-def` |
| `span_id` | string | 否 | span ID | `span-456` |
| `message` | string | 是 | 日志内容 | `Agent execution completed` |
| `duration_ms` | int | 否 | 操作耗时(ms) | `1250` |
| `user_id` | string | 否 | 用户 ID | `user-001` |
| `tenant_id` | string | 否 | 租户 ID | `tenant-001` |
| `error` | object | 否 | 错误信息 | `{"code": "E001", "msg": "..."}` |

**日志示例**：
```json
{
  "timestamp": "2026-04-09T10:30:00.123Z",
  "level": "INFO",
  "service": "ai-platform-platform",
  "trace_id": "abc-123-def",
  "message": "Agent execution completed",
  "duration_ms": 1250,
  "user_id": "user-001",
  "tenant_id": "tenant-001"
}
```

---

#### 日志级别使用规范

| 级别 | 使用场景 | 生产环境 |
|------|----------|----------|
| DEBUG | 详细调试信息 | 关闭 |
| INFO | 关键操作信息 | 开启 |
| WARNING | 警告信息 | 开启 |
| ERROR | 错误信息 | 开启 |
| CRITICAL | 严重错误 | 开启 |

---

#### 日志文件位置

| 服务 | 日志路径 | 轮转策略 |
|------|----------|----------|
| aiPlat-platform | `/var/log/ai-platform/platform.log` | 每天/100MB，保留30天 |
| aiPlat-core | `/var/log/ai-platform/core.log` | 每天/100MB，保留30天 |
| aiPlat-app (Gateway) | `/var/log/ai-platform/gateway.log` | 每天/100MB，保留30天 |
| aiPlat-infra | `/var/log/ai-platform/infra.log` | 每天/100MB，保留30天 |
| PostgreSQL | `/var/log/postgresql/` | 系统管理 |
| Redis | `/var/log/redis/` | 系统管理 |

---

#### 日志查询命令

**查询最近 1 小时的错误日志**：
```bash
grep '"level":"ERROR"' /var/log/ai-platform/platform.log | grep "2026-04-09T1"
```

**查询特定 trace_id 的所有日志**：
```bash
grep '"trace_id":"abc-123-def"' /var/log/ai-platform/*.log
```

**统计各服务错误数**：
```bash
grep -r '"level":"ERROR"' /var/log/ai-platform/ | cut -d/ -f5 | sort | uniq -c
```

**实时查看日志**：
```bash
# 使用 jq（推荐）
tail -f /var/log/ai-platform/platform.log | jq .

# 使用 grep（降级方案）
tail -f /var/log/ai-platform/platform.log | grep -E '"level":"ERROR"'

# 使用 python（通用方案）
tail -f /var/log/ai-platform/platform.log | python -m json.tool
```

---

### 数据备份

#### 备份策略

| 数据类型 | 备份频率 | 保留时长 | 备份方式 | 存储位置 |
|----------|----------|----------|----------|----------|
| PostgreSQL | 每天 2:00 全量 | 30 天 | `pg_dump` | S3/OSS |
| PostgreSQL WAL | 每小时 | 7 天 | 归档 | S3/OSS |
| Redis | 每天 3:00 | 7 天 | RDB | 本地 + S3 |
| Milvus | 每天 4:00 | 14 天 | 快照 | S3/OSS |
| 配置文件 | 每次变更 | 永久 | Git | Git仓库 |

---

#### 备份命令

**数据库备份**：
```bash
# 全量备份
pg_dump -h localhost -U ai_platform ai_platform_db > backup_$(date +%Y%m%d).sql

# 压缩备份
pg_dump -h localhost -U ai_platform ai_platform_db | gzip > backup_$(date +%Y%m%d).sql.gz

# 验证备份
pg_restore --list backup_$(date +%Y%m%d).sql
```

**Redis 备份**：
```bash
# 触发 RDB 快照
redis-cli BGSAVE

# 复制 RDB 文件
cp /var/lib/redis/dump.rdb /backup/redis_$(date +%Y%m%d).rdb
```

**配置备份**：
```bash
# 备份配置目录
tar -czf config_$(date +%Y%m%d).tar.gz config/

# 推送到 Git
git add config/ && git commit -m "backup config"
git push
```

---

#### 恢复命令

**数据库恢复**：
```bash
# 停止服务
systemctl stop ai-platform-platform

# 恢复数据库
psql -h localhost -U ai_platform ai_platform_db < backup_20260409.sql

# 重启服务
systemctl start ai-platform-platform
```

**Redis 恢复**：
```bash
# 停止 Redis
systemctl stop redis

# 恢复 RDB 文件
cp /backup/redis_20260409.rdb /var/lib/redis/dump.rdb

# 启动 Redis
systemctl start redis
```

**恢复前验证**：
```bash
# 验证数据库备份文件完整性
pg_restore --list backup_20260409.sql | head -20

# 在测试环境先恢复验证（推荐）
createdb test_restore
psql -d test_restore < backup_20260409.sql

# 验证关键表
psql -d test_restore -c "SELECT COUNT(*) FROM agents;"
psql -d test_restore -c "SELECT COUNT(*) FROM skills;"

# 清理测试数据库
dropdb test_restore
```

---

### 升级维护

#### 升级流程

1. **准备阶段**：
   - 通知相关用户
   - 备份所有数据
   - 准备回滚方案

2. **执行阶段**：
   - 停止旧版本服务
   - 部署新版本服务
   - 执行数据库迁移
   - 启动新版本服务

3. **验证阶段**：
   - 执行健康检查
   - 验证核心功能
   - 监控错误日志

4. **回滚方案**：
   - 停止新版本服务
   - 恢复数据库备份
   - 启动旧版本服务

---

#### 版本兼容性

| 升级路径 | 数据库迁移 | 配置变更 | 回滚支持 |
|----------|------------|----------|----------|
| 1.x → 1.y | 小版本无需 | 否 | 是 |
| 1.x → 2.0 | 需要 | 需要 | 仅备份恢复 |

---

## 🐛 故障排查

### 排查流程

```
发现问题 → 确认影响范围 → 查看监控仪表盘 → 分析日志 → 定位根因 → 执行恢复 → 记录复盘
```

---

### 健康检查端点

| 服务 | 健康检查端点 | 预期响应 |
|------|--------------|----------|
| platform | `GET /health` | `{"status":"healthy"}` |
| platform | `GET /ready` | `{"status":"ready"}` |
| core | `GET /health` | `{"status":"healthy"}` |
| PostgreSQL | TCP 5432 | 可连接 |
| Redis | `PING` | `PONG` |
| Milvus | TCP 19530 | 可连接 |

**健康检查命令**：
```bash
# 检查所有服务健康状态
make health-check

# 检查单个服务
curl http://localhost:8000/health
```

---

### 常见问题排查步骤

#### 数据库连接失败

**现象**：API 返回 500，日志包含 `connection refused`

**排查步骤**：
```bash
# 1. 检查数据库进程
systemctl status postgresql

# 2. 检查连接数
psql "$DATABASE_URL" -c "SELECT count(*) FROM pg_stat_activity;"

# 3. 检查配置
cat .env | grep DATABASE_URL

# 4. 测试连接
psql "$DATABASE_URL" -c "SELECT 1"

# 5. 检查网络
telnet <db_host> 5432
```

**恢复方案**：
1. 重启数据库服务：`systemctl restart postgresql`
2. 检查连接池配置：`config/platform/database.yaml`
3. 扩容数据库连接数

---

#### LLM 调用失败

**现象**：Agent 执行超时，返回 `LLM provider error`

**排查步骤**：
```bash
# 1. 检查 API 密钥有效性
curl -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.openai.com/v1/models

# 2. 检查配额
curl -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.openai.com/v1/dashboard/billing/usage

# 3. 检查网络
ping api.openai.com

# 4. 检查限流（查看返回头）
curl -I -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.openai.com/v1/chat/completions
```

**恢复方案**：
1. 切换备用 LLM 提供商：修改 `config/core/llm.yaml`
2. 等待配额重置
3. 联系 LLM 提供商

---

#### 性能下降

**现象**：API 响应时间从 200ms 上升到 2s

**排查步骤**：
```bash
# 1. 检查系统资源
top
htop
free -h

# 2. 检查慢查询
psql "$DATABASE_URL" -c \
  "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 3. 检查缓存命中率
redis-cli INFO stats | grep keyspace

# 4. 检查 LLM 调用延迟
grep '"duration_ms"' /var/log/ai-platform/core.log | tail -100

# 5. 检查并发连接
netstat -an | grep ESTABLISHED | wc -l
```

**恢复方案**：
1. 扩容服务实例
2. 增加缓存 TTL
3. 优化慢查询
4. 检查是否有资源泄露

---

#### 内存不足

**现象**：服务 OOM，日志包含 `Out of memory`

**排查步骤**：
```bash
# 1. 检查内存使用
free -h
cat /proc/meminfo

# 2. 检查进程内存
ps aux --sort=-%mem | head -10

# 3. 检查 JVM/Python 内存（如果适用）
# Python: 使用 memory_profiler

# 4. 检查缓存配置
redis-cli CONFIG GET maxmemory
```

**恢复方案**：
1. 增加系统内存
2. 减少缓存大小
3. 优化内存使用
4. 重启服务

---

### 紧急恢复操作

| 场景 | 操作 | 预计恢复时间 |
|------|------|--------------|
| 服务无响应 | `systemctl restart ai-platform-platform` | 30秒 |
| 数据库损坏 | 从最近备份恢复 | 15分钟 |
| LLM 完全不可用 | 切换备用提供商（修改配置） | 5分钟 |
| 磁盘空间不足 | `docker system prune -a` | 5分钟 |
| 缓存失效 | `redis-cli FLUSHALL` 然后预热 | 10分钟 |
| 配置错误 | Git 回滚配置，重启服务 | 5分钟 |

---

## 📖 各层运维指南

### 基础设施层运维

**详细文档**：[aiPlat-infra/docs/by-role/ops/index.md](../../aiPlat-infra/docs/by-role/ops/index.md)

**运维要点**：
- 数据库监控和优化
- LLM API 管理
- 向量存储维护
- 配置管理

**常用命令**：
```bash
# 检查数据库状态
make db-status

# 检查 Redis 状态
make redis-status

# 检查 Milvus 状态
make milvus-status
```

---

### 核心层运维

**详细文档**：[aiPlat-core/docs/by-role/ops/index.md](../../aiPlat-core/docs/by-role/ops/index.md)

**运维要点**：
- Agent 和 Skill 管理
- 编排引擎监控
- 性能调优

**常用命令**：
```bash
# 查看 Agent 状态
aiplat agent list

# 查看 Skill 状态
aiplat skill list

# 重启核心服务
systemctl restart ai-platform-core
```

---

### 平台层运维

**详细文档**：[aiPlat-platform/docs/by-role/ops/index.md](../../aiPlat-platform/docs/by-role/ops/index.md)

**运维要点**：
- API 服务监控
- 认证服务维护
- 限流和熔断配置

**常用命令**：
```bash
# 查看 API 健康状态
curl http://localhost:8000/health

# 查看限流配置
aiplat config get rate_limit

# 重启平台服务
systemctl restart ai-platform-platform
```

---

### 应用层运维

**详细文档**：[aiPlat-app/docs/by-role/ops/index.md](../../aiPlat-app/docs/by-role/ops/index.md)

**运维要点**：
- Gateway 服务管理
- CLI 工具维护
- Web UI 部署

**常用命令**：
```bash
# 查看 Gateway 状态
systemctl status ai-platform-gateway

# 查看 Web UI 状态
systemctl status ai-platform-web

# 重启应用服务
systemctl restart ai-platform-app
```

---

## 🔗 相关链接

- [← 返回主文档](../index.md)
- [架构师指南 →](../architect/index.md)
- [开发者指南 →](../developer/index.md)

---

*最后更新: 2026-04-10*