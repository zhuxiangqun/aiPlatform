# 平台层部署指南

> 继承系统级部署指南，针对平台层的特定要求

---

## 继承规范

本文档继承 [系统级部署指南](../../docs/guides/DEPLOYMENT.md)，所有系统级规范在本层必须遵守。

---

## 部署顺序

平台层部署顺序：

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
│ 3. 平台配置      │  API 路由、认证配置、限流规则
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 平台服务      │  API Gateway、Auth Service、Tenant Service
└─────────────────┘
```

---

## 部署命令

```bash
# 开发环境
make deploy-platform ENV=dev

# 生产环境
kubectl apply -f k8s/platform/base/
kubectl apply -f k8s/platform/overlays/prod/
```

---

## 配置管理

### API Gateway 配置

```yaml
# config/platform/gateway.yaml
gateway:
  port: 8000
  rate_limit:
    requests_per_minute: 100
    burst: 200
  
  routes:
    - path: /api/v1/agents
      service: agent-service
    - path: /api/v1/skills
      service: skill-service
```

### 认证配置

```yaml
# config/platform/auth.yaml
auth:
  jwt_secret: ${JWT_SECRET}
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  
  providers:
    - type: oauth2
      name: google
      client_id: ${GOOGLE_CLIENT_ID}
      client_secret: ${GOOGLE_CLIENT_SECRET}
```

---

## 健康检查

```python
@router.get("/health/ready")
async def readiness_check():
    """平台层就绪检查"""
    checks = {
        "core": await check_core_service(),
        "database": await check_database(),
        "redis": await check_redis(),
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
# 平台层特有指标
api_requests_total = Counter(
    'api_requests_total',
    'API requests',
    ['method', 'path', 'status']
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'path'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5]
)

auth_requests_total = Counter(
    'auth_requests_total',
    'Auth requests',
    ['provider', 'status']
)
```

---

## 部署检查清单

### 部署前检查

- [ ] 基础设施层已部署
- [ ] 核心层已部署
- [ ] API 路由配置完成
- [ ] 认证配置完成
- [ ] 限流规则配置完成

### 部署后检查

- [ ] API Gateway 运行正常
- [ ] 认证服务正常
- [ ] API 可访问
- [ ] 认证可工作
- [ ] 监控指标正常

---

## 相关链接

- [系统级部署指南](../../docs/guides/DEPLOYMENT.md)
- [platform层开发规范](./DEVELOPMENT.md)

---

*最后更新: 2026-04-11*