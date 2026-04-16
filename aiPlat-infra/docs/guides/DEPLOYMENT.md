# 基础设施层部署指南（To-Be 为主，As-Is 以代码事实为准）

> 说明：本文档包含 Docker/K8s/数据库/消息队列等基础设施部署的 To-Be 指南；本仓库未必包含对应部署工件（make/k8s 等），请以实际 ops 仓库为准。

> 继承系统级部署指南，针对基础设施层的特定要求

---

## 📋 目录

- [继承规范](#继承规范)
- [部署架构](#部署架构)
- [部署顺序](#部署顺序)
- [数据库部署](#数据库部署)
- [消息队列部署](#消息队列部署)
- [向量存储部署](#向量存储部署)
- [配置管理](#配置管理)
- [健康检查](#健康检查)
- [监控配置](#监控配置)
- [故障排查](#故障排查)

---

## 继承规范

本文档可继承系统级部署指南（若存在上层仓库/平台仓库），所有系统级规范在本层必须遵守：

- **环境管理**：dev / test / staging / prod
- **配置管理**：环境变量优先，敏感信息存 Vault
- **部署方式**：Docker Compose（开发）、Kubernetes（生产）
- **监控告警**：Prometheus + Grafana + AlertManager
- **备份恢复**：定期备份、快照

本层额外规范如下：

---

## 部署架构

### 基础设施层组件

```
┌─────────────────────────────────────────────────────────────┐
│                      aiPlat-infra                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ PostgreSQL  │  │   MySQL     │  │  MongoDB    │          │
│  │   (主数据库) │  │  (备用数据库)│  │ (文档数据库)│          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Redis     │  │  RabbitMQ   │  │   Kafka     │          │
│  │  (缓存+消息) │  │  (消息队列)  │  │  (事件流)   │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Milvus    │  │  ChromaDB   │  │   MinIO     │          │
│  │  (向量存储) │  │ (向量存储)  │  │ (对象存储)  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐                            │
│  │ LLM Gateway │  │ Config Svc  │                            │
│  │ (LLM 网关)  │  │ (配置服务) │                            │
│  └─────────────┘  └─────────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 资源需求

| 组件 | 最小配置 | 推荐配置 | 生产配置 |
|------|----------|----------|----------|
| PostgreSQL | 1 CPU, 2GB | 2 CPU, 4GB | 4+ CPU, 8+ GB |
| MySQL | 1 CPU, 2GB | 2 CPU, 4GB | 4+ CPU, 8+ GB |
| MongoDB | 1 CPU, 2GB | 2 CPU, 4GB | 4+ CPU, 8+ GB |
| Redis | 0.5 CPU, 1GB | 1 CPU, 2GB | 2+ CPU, 4+ GB |
| Milvus | 2 CPU, 4GB | 4 CPU, 8GB | 8+ CPU, 16+ GB |
| Kafka | 2 CPU, 4GB | 4 CPU, 8GB | 8+ CPU, 16+ GB |

---

## 部署顺序

### 基础服务依赖

基础设施层是其他层的依赖，必须最先部署：

```
┌─────────────────┐
│ 1. 存储层       │  PostgreSQL, MySQL, MongoDB, MinIO
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 缓存层       │  Redis
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 消息层       │  Kafka, RabbitMQ
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 搜索层       │  Milvus, ChromaDB
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. 服务层       │  LLM Gateway, Config Service
└─────────────────┘
```

### 部署命令

```bash
# 开发环境 - Docker Compose
make docker-up-infra  # To-Be：需实际提供对应 Makefile/compose

# 生产环境 - Kubernetes
kubectl apply -f k8s/infra/base/

---

## 证据索引（Evidence Index｜抽样）

- infra 可运行能力以代码与测试为准：`infra/tests/*`
kubectl apply -f k8s/infra/overlays/prod/
```

---

## 数据库部署

### PostgreSQL 部署

#### Docker Compose（开发环境）

```yaml
# docker-compose.yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: ai-platform-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

#### Kubernetes（生产环境）

```yaml
# k8s/infra/postgres.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-ssd

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-data
        persistentVolumeClaim:
          claimName: postgres-pvc
```

### 数据库迁移

```bash
# 初始化数据库
make db-migrate

# 查看迁移状态
make db-migrate-status

# 回滚迁移
make db-migrate-rollback VERSION=20260411
```

### 数据库备份

```bash
# PostgreSQL 备份
pg_dump -h $HOST -U $USER $DATABASE > backup_$(date +%Y%m%d).sql

# 自动备份脚本
0 2 * * * /usr/local/bin/backup-postgres.sh
```

---

## 消息队列部署

### Redis 部署

```yaml
# docker-compose.yaml
services:
  redis:
    image: redis:7-alpine
    container_name: ai-platform-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
```

### Kafka 部署

```yaml
# docker-compose.yaml
services:
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: ai-platform-kafka
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    ports:
      - "9092:9092"
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: ai-platform-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
```

---

## 向量存储部署

### Milvus 部署

```yaml
# docker-compose.yaml
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.15
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: 1000
      ETCD_QUOTA_BACKEND_BYTES: 4294967296
    volumes:
      - etcd_data:/etcd

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    command: minio server /minio_data
    volumes:
      - minio_data:/minio_data

  milvus:
    image: milvusdb/milvus:v2.3.3
    container_name: ai-platform-milvus
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - milvus_data:/var/lib/milvus
    ports:
      - "19530:19530"
    depends_on:
      - etcd
      - minio
```

---

## 配置管理

### 配置文件

```yaml
# config/infra/database.yaml
database:
  postgres:
    host: ${POSTGRES_HOST:localhost}
    port: ${POSTGRES_PORT:5432}
    database: ${POSTGRES_DB:ai_platform}
    user: ${POSTGRES_USER:postgres}
    password: ${POSTGRES_PASSWORD}
    min_connections: 5
    max_connections: 20
    connection_timeout: 60

  mongodb:
    host: ${MONGODB_HOST:localhost}
    port: ${MONGODB_PORT:27017}
    database: ${MONGODB_DB:ai_platform}
    user: ${MONGODB_USER:mongodb}
    password: ${MONGODB_PASSWORD}
```

### 环境变量

```bash
# .env.example

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secret>

# MongoDB
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DB=ai_platform
MONGODB_USER=mongodb
MONGODB_PASSWORD=<secret>

# LLM
OPENAI_API_KEY=<secret>
ANTHROPIC_API_KEY=<secret>

# Vector Store
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

---

## 健康检查

### 健康检查端点

```python
# infra/health.py
from fastapi import APIRouter, Response

router = APIRouter()

@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}

@router.get("/health/ready")
async def readiness_check():
    """就绪检查"""
    checks = {
        "postgres": await check_postgres(),
        "redis": await check_redis(),
        "milvus": await check_milvus(),
    }
    
    all_healthy = all(checks.values())
    
    if not all_healthy:
        return Response(
            content=json.dumps({"status": "not ready", "checks": checks}),
            status_code=503
        )
    
    return {"status": "ready", "checks": checks}

@router.get("/health/live")
async def liveness_check():
    """存活检查"""
    return {"status": "alive"}
```

### Kubernetes 健康检查

```yaml
# k8s/infra/deployment.yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 监控配置

### Prometheus 指标

```python
# infra/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# 连接池指标
db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections',
    ['database']
)

db_connections_idle = Gauge(
    'db_connections_idle',
    'Idle database connections',
    ['database']
)

# 查询指标
db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['database', 'operation'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5]
)

db_query_errors = Counter(
    'db_query_errors_total',
    'Database query errors',
    ['database', 'error_type']
)

# LLM 指标
llm_request_duration = Histogram(
    'llm_request_duration_seconds',
    'LLM request duration',
    ['provider', 'model'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60]
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'LLM tokens usage',
    ['provider', 'model', 'type']
)
```

### 告警规则

```yaml
# prometheus/alerts.yaml
groups:
  - name: infra.rules
    rules:
      - alert: DatabaseConnectionPoolExhausted
        expr: db_connections_active / db_connections_max > 0.9
        for: 5m
        annotations:
          summary: "数据库连接池即将耗尽"
          description: "数据库 {{ $labels.database }} 连接池使用率 > 90%"
      
      - alert: DatabaseQuerySlow
        expr: histogram_quantile(0.95, db_query_duration_seconds) > 1
        for: 10m
        annotations:
          summary: "数据库查询慢"
          description: "P95 查询延迟 > 1s"
      
      - alert: LLMRequestSlow
        expr: histogram_quantile(0.95, llm_request_duration_seconds) > 30
        for: 5m
        annotations:
          summary: "LLM 请求慢"
          description: "P95 LLM 请求延迟 > 30s"
```

---

## 故障排查

### 常见问题

#### 数据库连接失败

```bash
# 检查数据库状态
kubectl logs -f deployment/postgres -n ai-platform

# 检查连接池
kubectl exec -it postgres-0 -n ai-platform -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# 检查网络
kubectl exec -it <pod> -n ai-platform -- nc -zv postgres 5432
```

#### Redis 连接超时

```bash
# 检查 Redis 状态
kubectl exec -it redis-0 -n ai-platform -- redis-cli ping

# 检查内存使用
kubectl exec -it redis-0 -n ai-platform -- redis-cli info memory

# 检查连接数
kubectl exec -it redis-0 -n ai-platform -- redis-cli info clients
```

#### Milvus 查询慢

```bash
# 检查索引状态
curl http://localhost:19530/v1/vector/collections

# 检查内存使用
kubectl top pod -n ai-platform -l app=milvus

# 重建索引
# 需要通过 Milvus API 操作
```

### 日志查看

```bash
# 实时日志
kubectl logs -f deployment/ai-platform-infra -n ai-platform

# 过滤错误
kubectl logs deployment/ai-platform-infra -n ai-platform | grep ERROR

# 查看最近1小时日志
kubectl logs deployment/ai-platform-infra -n ai-platform --since=1h
```

---

## 部署检查清单

### 部署前检查

- [ ] 配置文件准备完成（`config/infra/*.yaml`）
- [ ] 密钥配置完成（Kubernetes Secrets）
- [ ] 存储卷创建完成（PVC）
- [ ] 网络策略配置完成（NetworkPolicy）
- [ ] 资源配额配置完成（ResourceQuota）

### 部署后检查

- [ ] 所有 Pod 状态为 Running
- [ ] 健康检查通过（`/health/ready`）
- [ ] 数据库连接正常
- [ ] Redis 连接正常
- [ ] Milvus 连接正常
- [ ] 日志无错误
- [ ] 监控指标正常

### 验证命令

```bash
# 验证数据库
make test-db

# 验证 Redis
make test-redis

# 验证 Milvus
make test-vector

# 验证 LLM
make test-llm

# 完整验证
make health-check
```

---

## 相关链接

- [系统级部署指南](../../../docs/guides/DEPLOYMENT.md)
- [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)
- [infra层测试指南](../testing/TESTING_GUIDE.md)
- [infra层开发规范](./DEVELOPMENT.md)

---

*最后更新: 2026-04-11*
