# 应用层部署指南

> 继承系统级部署指南，针对应用层的特定要求

---

## 继承规范

本文档继承 [系统级部署指南](../../docs/guides/DEPLOYMENT.md)，所有系统级规范在本层必须遵守。

---

## 部署顺序

应用层部署顺序：

```
┌─────────────────┐
│ 1. 基础设施层    │  已部署
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 核心层        │  已部署
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 平台层        │  已部署
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 应用层        │  Web UI, CLI, Gateway
└─────────────────┘
```

---

## 部署命令

```bash
# 开发环境 - Web UI
make deploy-web ENV=dev

# 开发环境 - CLI
pip install aiplat-cli --pre

# 生产环境 - Web UI
kubectl apply -f k8s/app/web/base/
kubectl apply -f k8s/app/web/overlays/prod/

# 生产环境 - Gateway
kubectl apply -f k8s/app/gateway/base/
kubectl apply -f k8s/app/gateway/overlays/prod/
```

---

## Web UI 部署

### Docker 构建

```dockerfile
# Dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-ui
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web-ui
  template:
    metadata:
      labels:
        app: web-ui
    spec:
      containers:
      - name: web-ui
        image: ai-platform/web-ui:latest
        ports:
        - containerPort: 80
        env:
        - name: API_URL
          value: "http://api.ai-platform.svc.cluster.local:8000"
---
apiVersion: v1
kind: Service
metadata:
  name: web-ui
spec:
  selector:
    app: web-ui
  ports:
  - port: 80
    targetPort: 80
```

---

## Gateway 部署

### Telegram Gateway

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telegram-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: telegram-gateway
  template:
    metadata:
      labels:
        app: telegram-gateway
    spec:
      containers:
      - name: telegram-gateway
        image: ai-platform/telegram-gateway:latest
        env:
        - name: TELEGRAM_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: telegram-secret
              key: bot-token
        - name: API_URL
          value: "http://api.ai-platform.svc.cluster.local:8000"
```

---

## 配置管理

### 环境配置

```yaml
# config/app/web.yaml
web:
  api_url: ${API_URL:http://localhost:8000}
  auth:
    enabled: true
    provider: oauth2
  
  features:
    agent_creation: true
    skill_management: true
    knowledge_base: true
```

### Gateway 配置

```yaml
# config/app/gateway.yaml
gateways:
  telegram:
    enabled: true
    bot_token: ${TELEGRAM_BOT_TOKEN}
  
  slack:
    enabled: false
    bot_token: ${SLACK_BOT_TOKEN}
    app_token: ${SLACK_APP_TOKEN}
```

---

## 健康检查

```python
@router.get("/health/ready")
async def readiness_check():
    """应用层就绪检查"""
    checks = {
        "platform": await check_platform(),
    }
    
    all_healthy = all(checks.values())
    
    if not all_healthy:
        return Response(
            content=json.dumps({"status": "not ready", "checks": checks}),
            status_code=503
        )
    
    return {"status": "ready", "checks": checks}
```

---

## 监控指标

```python
# 应用层特有指标
web_requests_total = Counter(
    'web_requests_total',
    'Web requests',
    ['path', 'method']
)

gateway_messages_total = Counter(
    'gateway_messages_total',
    'Gateway messages',
    ['gateway_type', 'status']
)

cli_commands_total = Counter(
    'cli_commands_total',
    'CLI commands',
    ['command']
)
```

---

## 部署检查清单

### 部署前检查

- [ ] 基础设施层已部署
- [ ] 核心层已部署
- [ ] 平台层已部署
- [ ] Web UI 配置完成
- [ ] Gateway 配置完成（如使用）

### 部署后检查

- [ ] Web UI 可访问
- [ ] 认证可工作
- [ ] API 调用正常
- [ ] Gateway 正常（如部署）
- [ ] 监控指标正常

---

## 相关链接

- [系统级部署指南](../../docs/guides/DEPLOYMENT.md)
- [app层开发规范](./DEVELOPMENT.md)

---

*最后更新: 2026-04-11*