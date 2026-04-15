# AI Platform 部署指南

> 系统级部署指南 - 各层必须遵循

---

## 📋 目录

- [部署架构](#部署架构)
- [环境管理](#环境管理)
- [部署顺序](#部署顺序)
- [部署方式](#部署方式)
- [配置管理](#配置管理)
- [监控告警](#监控告警)
- [日志管理](#日志管理)
- [备份恢复](#备份恢复)
- [故障排查](#故障排查)
- [安全加固](#安全加固)

---

## 部署架构

### 整体架构

```
                         ┌─────────────────────┐
                         │   负载均衡          │
                         │   (Nginx/ALB)       │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            ┌───────▼───────┐       │       ┌───────▼───────┐
            │  消息网关      │       │       │  Web UI       │
            │  (Layer 3)    │       │       │  (Layer 3)    │
            └───────┬───────┘       │       └───────┬───────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   API 网关          │
                         │   (Layer 2)         │
                         │   认证、限流、路由  │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   核心服务          │
                         │   (Layer 1)         │
                         │   Agent、Skill、编排│
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            ┌───────▼───────┐ ┌─────▼─────┐ ┌───────▼───────┐
            │  数据库       │ │  LLM      │ │  向量存储     │
            │  PostgreSQL   │ │  API      │ │  Milvus      │
            │  MongoDB      │ │           │ │              │
            └───────────────┘ └───────────┘ └───────────────┘
                    │               │               │
                         ┌──────────▼──────────┐
                         │   基础设施层        │
                         │   (Layer 0)         │
                         └─────────────────────┘
```

### 部署拓扑

| 环境 | 架构 | 说明 |
|------|------|------|
| **开发环境** | 单机 Docker Compose | 本地开发、快速迭代 |
| **测试环境** | 单机 Kubernetes（Minikube） | 功能测试、集成测试 |
| **预发环境** | 多节点 Kubernetes（类生产） | 性能测试、安全测试 |
| **生产环境** | 多节点高可用 Kubernetes | 正式服务、高可用 |

---

## 环境管理

### 环境分类

| 环境类型 | 用途 | 数据 | 隔离性 | 访问权限 |
|----------|------|------|--------|----------|
| **开发** | 本地开发 | Mock/内存 | 开发机 | 开发者 |
| **测试** | 功能测试 | 测试数据 | 命名空间隔离 | 开发者、测试 |
| **预发** | 类生产测试 | 脱敏数据 | 环境隔离 | 开发者、测试、运维 |
| **生产** | 正式服务 | 生产数据 | 完全隔离 | 运维 |

### 环境配置

**配置优先级**（从高到低）：

1. 环境变量
2. 密钥管理服务（Vault / Kubernetes Secrets）
3. 配置文件
4. 默认值

**配置文件结构**：

```
config/
├── base/                    # 基础配置
│   ├── database.yaml
│   ├── llm.yaml
│   └── vector.yaml
│
├── environments/           # 环境配置
│   ├── dev.yaml           # 开发环境
│   ├── test.yaml          # 测试环境
│   ├── staging.yaml       # 预发环境
│   └── prod.yaml          # 生产环境
│
└── secrets/                # 敏感配置（不提交）
    ├── database.yaml
    ├── llm.yaml
    └── vault.yaml
```

### 环境变量规范

**命名规范**：

```bash
# 格式：<SERVICE>_<COMPONENT>_<KEY>

# 数据库
DATABASE_POSTGRES_HOST=localhost
DATABASE_POSTGRES_PORT=5432
DATABASE_POSTGRES_USER=postgres
DATABASE_POSTGRES_PASSWORD=secret

# LLM
LLM_OPENAI_API_KEY=sk-xxx
LLM_OPENAI_MODEL=gpt-4

# 向量存储
VECTOR_MILVUS_HOST=localhost
VECTOR_MILVUS_PORT=19530
```

**敏感信息管理**：

| 类型 | 存储位置 | 示例 |
|------|----------|------|
| 数据库密码 | Vault / K8s Secrets | `DATABASE_POSTGRES_PASSWORD` |
| API Key | Vault / K8s Secrets | `LLM_OPENAI_API_KEY` |
| 证书 | Vault / K8s Secrets | TLS 证书 |
| 配置文件 | Git（加密） | `config/secrets/*.enc.yaml` |

---

## 部署顺序

### 层级依赖关系

```
aiPlat-infra (Layer 0)    ← 最底层，最先部署
       ↓
aiPlat-core (Layer 1)    ← 依赖 infra
       ↓
aiPlat-platform (Layer 2) ← 依赖 core
       ↓
aiPlat-app (Layer 3)     ← 最上层，最后部署
```

### 部署流程

```
┌─────────────────────────────────────────────────────────┐
│ Step 1: 部署基础设施（Layer 0）                          │
├─────────────────────────────────────────────────────────┤
│ - PostgreSQL / MySQL / MongoDB                          │
│ - Redis / RabbitMQ / Kafka                              │
│ - Milvus / ChromaDB                                     │
│ - MinIO / S3                                            │
│ - 日志、监控、追踪基础设施                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待基础设施就绪
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 2: 部署核心服务（Layer 1）                         │
├─────────────────────────────────────────────────────────┤
│ - 配置服务依赖的数据库、向量存储                       │
│ - 部署 core 服务                                        │
│ - 健康检查                                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待核心服务就绪
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 3: 部署平台服务（Layer 2）                         │
├─────────────────────────────────────────────────────────┤
│ - 配置平台服务依赖的 core 服务                         │
│ - 部署 platform 服务                                    │
│ - 配置认证、多租户、计费                               │
│ - 健康检查                                              │
└────────────────────────┬────────────────────────────────┘
                         │ 等待平台服务就绪
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 4: 部署应用服务（Layer 3）                         │
├─────────────────────────────────────────────────────────┤
│ - 配置应用依赖的平台服务                                │
│ - 部署消息网关                                          │
│ - 部署 Web UI                                           │
│ - 部署 CLI                                              │
│ - 健康检查                                              │
└─────────────────────────────────────────────────────────┘
```

### 部署命令

```bash
# 部署基础设施（Layer 0）
make deploy-infra ENV=prod

# 部署核心服务（Layer 1）
make deploy-core ENV=prod

# 部署平台服务（Layer 2）
make deploy-platform ENV=prod

# 部署应用服务（Layer 3）
make deploy-app ENV=prod

# 一键部署所有层
make deploy-all ENV=prod
```

---

## 部署方式

### Docker Compose（开发环境）

**适用场景**：本地开发、快速迭代

**目录结构**：

```
docker/
├── docker-compose.yaml          # 基础服务
├── docker-compose.dev.yaml      # 开发覆盖
└── docker-compose.override.yaml # 本地覆盖（不提交）
```

**部署命令**：

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f [service]

# 停止服务
docker-compose down

# 清理数据
docker-compose down -v
```

### Kubernetes（生产环境）

**目录结构**：

```
k8s/
├── base/                    # 基础配置
│   ├── infra/
│   ├── core/
│   ├── platform/
│   └── app/
│
├── overlays/                # 环境覆盖
│   ├── dev/
│   ├── test/
│   ├── staging/
│   └── prod/
│
└── charts/                  # Helm Charts
    ├── infra/
    ├── core/
    ├── platform/
    └── app/
```

**部署命令**：

```bash
# 使用 kubectl
kubectl apply -k k8s/overlays/prod

# 使用 Helm
helm upgrade --install ai-platform ./k8s/charts/ \
  --namespace ai-platform \
  --values k8s/overlays/prod/values.yaml

# 使用 Kustomize
kustomize build k8s/overlays/prod | kubectl apply -f -
```

### GitOps（推荐）

**使用 ArgoCD**：

```yaml
# argocd/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-platform
spec:
  project: default
  source:
    repoURL: https://github.com/org/ai-platform.git
    targetRevision: main
    path: k8s/overlays/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: ai-platform
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**优势**：
- 自动同步
- 版本控制
- 审计追踪
- 回滚便利

---

## 配置管理

### 配置中心

**方案选择**：

| 方案 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **环境变量** | 简单配置 | 简单、通用 | 无版本控制 |
| **ConfigMap** | Kubernetes | 原生支持 | 手动管理 |
| **Vault** | 敏感信息 | 安全、动态 | 复杂 |
| **Consul** | 服务发现+配置 | 动态、分布式 | 复杂 |
| **Apollo** | 大规模 | 动态、可视化 | 重量级 |

**推荐方案**：
- **开发环境**：环境变量 + ConfigMap
- **测试环境**：ConfigMap + Vault
- **生产环境**：Vault + Consul

### 配置热更新

```yaml
# Kubernetes ConfigMap 热更新
apiVersion: v1
kind: ConfigMap
metadata:
  name: ai-platform-config
  annotations:
    config.k8s.io/function: |
      container:
        image: gcr.io/kustomize-functions/example-update
---
# 应用自动重新加载配置
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-platform-core
spec:
  template:
    metadata:
      annotations:
        config-hash: "<configmap-hash>"
```

---

## 监控告警

### 监控架构

```
┌─────────────┐
│  应用程序   │
└──────┬──────┘
       │ 指标导出
       ▼
┌─────────────┐     ┌─────────────┐
│ Prometheus  │────→│  Grafana    │
│ (指标存储)  │     │  (可视化)   │
└─────────────┘     └─────────────┘
       │
       │ 告警
       ▼
┌─────────────┐
│ AlertManager│
│ (告警通知)  │
└─────────────┘
```

### 监控指标

**基础指标**：

| 类别 | 指标 | 说明 |
|------|------|------|
| **系统** | CPU、内存、磁盘、网络 | 基础资源使用 |
| **应用** | QPS、延迟、错误率 | 应用性能 |
| **业务** | Agent 调用、Token 使用量 | 业务指标 |
| **自定义** | 自定义指标 | 特殊需求 |

**关键指标**：

```yaml
# Prometheus 规则示例
groups:
  - name: ai-platform.rules
    rules:
      # 错误率告警
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
          /
          sum(rate(http_requests_total[5m])) by (service)
          > 0.05
        for: 10m
        annotations:
          summary: "服务 {{ $labels.service }} 错误率 > 5%"

      # 延迟告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
          > 2
        for: 10m
        annotations:
          summary: "服务 {{ $labels.service }} P95 延迟 > 2s"

      # LLM 调用延迟告警
      - alert: LLMHighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(llm_request_duration_seconds_bucket[5m])) by (le, model))
          > 30
        for: 5m
        annotations:
          summary: "模型 {{ $labels.model }} P95 延迟 > 30s"
```

### 告警渠道

| 优先级 | 渠道 | 响应时间 | 示例场景 |
|--------|------|----------|----------|
| P0 | 电话 + IM + 邮件 | 5 分钟 | 服务不可用、数据丢失 |
| P1 | IM + 邮件 | 15 分钟 | 性能严重下降、关键错误 |
| P2 | IM | 1 小时 | 非关键错误、资源预警 |
| P3 | 邮件 | 1 天 | 信息通知 |

---

## 日志管理

### 日志架构

```
┌─────────────┐
│  应用程序   │
│ (结构化日志)│
└──────┬──────┘
       │ stdout/stderr
       ▼
┌─────────────┐
│ Fluentd     │
│ (日志收集)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│ Elasticsearch│────→│ Kibana      │
│ (日志存储)  │     │ (可视化)    │
└─────────────┘     └─────────────┘
```

### 日志规范

**日志格式**（JSON）：

```json
{
  "timestamp": "2026-04-11T10:00:00Z",
  "level": "INFO",
  "service": "ai-platform-core",
  "trace_id": "abc123",
  "span_id": "def456",
  "message": "Agent executed successfully",
  "agent_id": "agent-123",
  "user_id": "user-456",
  "duration_ms": 1500,
  "tokens": {
    "input": 100,
    "output": 200
  }
}
```

**日志级别**：

| 级别 | 使用场景 |
|------|----------|
| **DEBUG** | 开发调试（生产关闭） |
| **INFO** | 正常操作、关键路径 |
| **WARN** | 非预期情况、可恢复错误 |
| **ERROR** | 错误、需要关注 |
| **FATAL** | 严重错误、服务终止 |

**敏感信息脱敏**：

```python
# ❌ 禁止记录敏感信息
logger.info(f"User login: {username}, password: {password}")

# ✅ 正确做法
logger.info(f"User login: {username}, password: ***")

# ✅ 使用脱敏函数
logger.info(f"User login: {username}, password: {mask(password)}")
```

### 日志保留

| 日志类型 | 保留策略 | 存储 |
|----------|----------|------|
| **访问日志** | 7 天 | Elasticsearch |
| **应用日志** | 30 天 | Elasticsearch |
| **错误日志** | 90 天 | Elasticsearch |
| **审计日志** | 365 天 | 对象存储 + 数据库 |
| **系统日志** | 30 天 | Elasticsearch |

---

## 备份恢复

### 备份策略

**数据库备份**：

| 类型 | 频率 | 保留 | 方式 |
|------|------|------|------|
| **全量备份** | 每天 | 7 天 | pg_dump / mysqldump |
| **增量备份** | 每小时 | 24 小时 | WAL 归档 |
| **快照备份** | 每天 | 3 天 | 云盘快照 |

**配置备份**：

```bash
# Kubernetes 配置备份
kubectl get all,configmaps,secrets -n ai-platform -o yaml > backup-$(date +%Y%m%d).yaml

# Vault 备份
vault operator raft snapshot save backup-$(date +%Y%m%d).snap
```

### 恢复流程

```
┌─────────────────┐
│ 发生故障        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 确认故障范围    │
│ - 服务影响？    │
│ - 数据影响？    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 选择恢复方案    │
│ - 服务重启      │
│ - 数据恢复      │
│ - 配置回滚      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 执行恢复        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 验证恢复        │
│ - 健康检查      │
│ - 功能验证      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 记录事件        │
│ - 故障原因      │
│ - 恢复步骤      │
│ - 预防措施      │
└─────────────────┘
```

### 恢复命令

```bash
# PostgreSQL 恢复
pg_restore -h $HOST -U $USER -d $DATABASE backup.dump

# MySQL 恢复
mysql -h $HOST -u $USER -p $DATABASE < backup.sql

# MongoDB 恢复
mongorestore --host $HOST --port $PORT --username $USER --password $PASSWORD /backup/path

# Kubernetes 恢复
kubectl apply -f backup-20260411.yaml

# Vault 恢复
vault operator raft snapshot restore backup-20260411.snap
```

---

## 故障排查

### 常见故障

| 故障类型 | 症状 | 排查步骤 |
|----------|------|----------|
| **服务启动失败** | Pod CrashLoopBackOff | 检查日志、配置、依赖 |
| **数据库连接失败** | 连接超时 | 检查网络、认证、连接数 |
| **LLM 调用超时** | 响应慢 | 检查 API、限流、并发 |
| **内存溢出** | OOM Killed | 检查内存使用、泄漏 |
| **磁盘满** | 写入失败 | 清理日志、扩容 |

### 排查流程

```
┌─────────────────┐
│ 发现故障        │
│ - 监控告警      │
│ - 用户反馈      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 确认故障        │
│ - 服务状态      │
│ - 日志分析      │
│ - 指标分析      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 定位根因        │
│ - 应用问题？    │
│ - 基础设施？    │
│ - 外部依赖？    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 临时修复        │
│ - 重启服务      │
│ - 回滚版本      │
│ - 限流降级      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 永久修复        │
│ - 修复代码      │
│ - 优化配置      │
│ - 加强监控      │
└─────────────────┘
```

### 排查命令

```bash
# Kubernetes 排查
kubectl get pods -n ai-platform
kubectl describe pod <pod-name> -n ai-platform
kubectl logs <pod-name> -n ai-platform --tail=100 -f
kubectl exec -it <pod-name> -n ai-platform -- sh

# 数据库排查
kubectl exec -it postgres-0 -n ai-platform -- psql -U postgres
kubectl exec -it mysql-0 -n ai-platform -- mysql -u root -p
kubectl exec -it mongodb-0 -n ai-platform -- mongosh

# 网络排查
kubectl exec -it <pod-name> -n ai-platform -- curl http://service-name
kubectl exec -it <pod-name> -n ai-platform -- nslookup service-name
kubectl exec -it <pod-name> -n ai-platform -- ping service-name

# 日志排查
kubectl logs -l app=ai-platform-core -n ai-platform --since=1h
kubectl logs -l app=ai-platform-core -n ai-platform | grep ERROR
```

---

## 安全加固

### 网络安全

**网络策略**：

```yaml
# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ai-platform-network-policy
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ai-platform
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: ai-platform
```

**TLS 加密**：

```yaml
# TLS 配置
apiVersion: v1
kind: Secret
metadata:
  name: ai-platform-tls
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-cert>
  tls.key: <base64-encoded-key>
```

### 访问控制

**RBAC 配置**：

```yaml
# ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ai-platform-core
  namespace: ai-platform

---
# Role
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ai-platform-core
  namespace: ai-platform
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list"]

---
# RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ai-platform-core
  namespace: ai-platform
subjects:
  - kind: ServiceAccount
    name: ai-platform-core
roleRef:
  kind: Role
  name: ai-platform-core
  apiGroup: rbac.authorization.k8s.io
```

### 密钥管理

**禁止事项**：

- ❌ 禁止在代码中硬编码密钥
- ❌ 禁止在 Git 中提交明文密钥
- ❌ 禁止在日志中记录密钥
- ❌ 禁止在容器镜像中打包密钥

**正确做法**：

```bash
# 使用 Kubernetes Secrets
kubectl create secret generic ai-platform-secrets \
  --from-literal=database-password='xxx' \
  --from-literal=openai-api-key='xxx' \
  -n ai-platform

# 使用 Vault
vault kv put secret/ai-platform/database password=xxx
vault kv put secret/ai-platform/openai api-key=xxx
```

### 安全检查清单

- [ ] 所有服务使用 TLS 加密
- [ ] 敏感信息存储在 Vault / Kubernetes Secrets
- [ ] 配置 RBAC 权限
- [ ] NetworkPolicy 限制网络访问
- [ ] Pod Security Policy/Policies 配置
- [ ] 容器镜像扫描漏洞
- [ ] 定期更新依赖版本
- [ ] 审计日志记录所有操作

---

## 各层部署规范

各层在遵循系统级部署规范的基础上，需遵循各自的特定规范：

| 层级 | 特殊要求 | 文档 |
|------|----------|------|
| **infra** | 数据库迁移、数据备份 | [infra 部署规范](../../aiPlat-infra/docs/guides/DEPLOYMENT.md) |
| **core** | 模型预加载、Agent 初始化 | [core 部署规范](../../aiPlat-core/docs/guides/DEPLOYMENT.md) |
| **platform** | API 网关、认证配置 | [platform 部署规范](../../aiPlat-platform/docs/guides/DEPLOYMENT.md) |
| **app** | 前端构建、静态资源 | [app 部署规范](../../aiPlat-app/docs/guides/DEPLOYMENT.md) |

---

## 📌 检查清单

### 部署前检查

- [ ] 配置文件准备完成
- [ ] 密钥配置完成（Vault / Secrets）
- [ ] 镜像构建完成并推送
- [ ] 数据库迁移脚本准备
- [ ] 健康检查配置完成
- [ ] 监控告警配置完成

### 部署后检查

- [ ] 所有服务健康检查通过
- [ ] 日志正常输出
- [ ] 监控指标正常
- [ ] 功能验证完成
- [ ] 性能验证完成
- [ ] 文档更新完成

### 发布检查

- [ ] CHANGELOG 已更新
- [ ] 版本号已更新
- [ ] Git tag 已创建
- [ ] 文档已更新
- [ ] 发布说明已发布

---

*最后更新: 2026-04-11*