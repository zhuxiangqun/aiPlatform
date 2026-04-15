# 👨‍💻 平台层开发者指南

> aiPlat-platform - 开发指南与最佳实践

---

## 🎯 开发者关注点

作为平台层开发者，您需要了解：
- **如何使用**：如何调用平台服务（API、认证、租户等）
- **如何扩展**：如何添加新的 API、中间件、服务
- **如何测试**：如何编写单元测试和集成测试
- **最佳实践**：开发中的最佳实践

---

## 🛠️ 开发环境搭建

### 前置条件

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Python | 3.10+ | 后端开发 |
| PostgreSQL | 13+ | 数据库 |
| Redis | 6+ | 缓存 |
| Docker | 20.10+ | 本地服务 |

### 安装依赖

```bash
cd aiPlat-platform
pip install -e .
```

### 配置环境

```bash
# 复制配置模板
cp config/platform/api.yaml.example config/platform/api.yaml
cp config/platform/auth.yaml.example config/platform/auth.yaml
cp config/platform/tenants.yaml.example config/platform/tenants.yaml

# 编辑配置文件
vi config/platform/api.yaml
```

### 启动服务

```bash
# 启动依赖服务
make docker-up-platform

# 启动平台服务
make run-platform

# 访问 API 文档
# http://localhost:8000/docs
```

### 验证环境

```bash
# 测试 API 连接
make test-api

# 测试数据库连接
make test-db

# 测试认证
make test-auth
```

---

## 🚀 快速开始

### 5 分钟跑起来

**步骤一：初始化数据库**
```bash
make db-migrate
make db-seed
```

**步骤二：启动服务**
```bash
make run-platform
```

**步骤三：测试 API**
```bash
# 健康检查
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs
```

---

## 📖 核心模块使用

### api - API 服务

**详细文档**：[api 模块文档](../api/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建路由文件 | 在 `platform/api/routes/` 下创建 `my_route.py` | `platform/api/routes/` |
| 定义路由 | 使用路由装饰器定义端点 | `platform/api/routes/my_route.py` |
| 添加处理器 | 实现 `Handler` 类 | `platform/api/handlers/` |
| 注册路由 | 在 `platform/api/__init__.py` 中注册 | `platform/api/__init__.py` |

**如何添加新的 API 端点**：

1. **创建路由文件**：在 `platform/api/routes/` 下创建 `my_route.py`
2. **定义路由**：使用路由装饰器定义端点路径和方法
3. **实现处理器**：实现请求处理逻辑，调用核心层服务
4. **添加 Schema**：定义请求和响应的数据模式
5. **注册路由**：在 `platform/api/__init__.py` 中注册路由
6. **编写测试**：在 `tests/integration/platform/api/` 下添加测试文件

**路由定义示例**：
- GET 请求：查询资源
- POST 请求：创建资源
- PUT 请求：更新资源
- DELETE 请求：删除资源

**相关文件位置**：
- 路由定义：`platform/api/routes/`
- 处理器：`platform/api/handlers/`
- Schema：`platform/api/schemas/`
- 测试文件：`tests/integration/platform/api/`

---

### auth - 认证授权

**详细文档**：[auth 模块文档](../auth/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 用户注册 | 调用 `UserService.register(user_data)` | `platform/auth/services/user.py` |
| 用户登录 | 调用 `AuthService.login(username, password)` | `platform/auth/services/auth.py` |
| 生成令牌 | 调用 `TokenService.generate_token(user)` | `platform/auth/services/token.py` |
| 验证令牌 | 调用 `TokenService.verify_token(token)` | `platform/auth/services/token.py` |
| 检查权限 | 调用 `PermissionService.check_permission(user, resource, action)` | `platform/auth/services/permission.py` |

**认证流程**：
1. 用户注册/登录
2. 生成 JWT 令牌
3. 客户端存储令牌
4. 请求时携带令牌
5. 服务端验证令牌

**相关文件位置**：
- 用户服务：`platform/auth/services/user.py`
- 认证服务：`platform/auth/services/auth.py`
- 令牌服务：`platform/auth/services/token.py`
- 权限服务：`platform/auth/services/permission.py`

---

### tenants - 租户管理

**详细文档**：[tenants 模块文档](../tenants/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建租户 | 调用 `TenantService.create(tenant_data)` | `platform/tenants/services/tenant.py` |
| 获取租户 | 调用 `TenantService.get(tenant_id)` | `platform/tenants/services/tenant.py` |
| 检查配额 | 调用 `QuotaService.check_quota(tenant_id, resource)` | `platform/tenants/services/quota.py` |
| 数据隔离 | 使用 `tenant_id` 过滤查询 | `platform/tenants/middleware/` |

**租户隔离方式**：
- **逻辑隔离**：通过 `tenant_id` 字段过滤
- **数据隔离**：通过数据库 schema 隔离
- **资源隔离**：通过资源配额限制

**相关文件位置**：
- 租户服务：`platform/tenants/services/tenant.py`
- 配额服务：`platform/tenants/services/quota.py`
- 命名空间服务：`platform/tenants/services/namespace.py`

---

### gateway - 服务网关

**详细文档**：[gateway 模块文档](../gateway/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 配置路由 | 编辑 `config/platform/routes.yaml` | `config/platform/routes.yaml` |
| 添加限流 | 调用 `RateLimitService.configure(config)` | `platform/gateway/services/rate_limit.py` |
| 配置熔断 | 调用 `CircuitBreakerService.configure(config)` | `platform/gateway/services/circuit_breaker.py` |
| 添加中间件 | 在 `platform/gateway/middleware/` 下创建中间件 | `platform/gateway/middleware/` |

**如何添加新的中间件**：

1. **创建中间件文件**：在 `platform/gateway/middleware/` 下创建 `my_middleware.py`
2. **实现中间件**：实现 `Middleware` 接口的 `process_request()` 和 `process_response()` 方法
3. **注册中间件**：在 `platform/gateway/__init__.py` 中注册中间件
4. **配置中间件**：在配置文件中添加中间件配置
5. **编写测试**：添加单元测试

**相关文件位置**：
- 路由服务：`platform/gateway/services/routing.py`
- 限流服务：`platform/gateway/services/rate_limit.py`
- 熔断服务：`platform/gateway/services/circuit_breaker.py`
- 中间件：`platform/gateway/middleware/`

---

### messaging - 消息服务

**详细文档**：[messaging 模块文档](../messaging/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 发送消息 | 调用 `ProducerService.send(topic, message)` | `platform/messaging/services/producer.py` |
| 接收消息 | 调用 `ConsumerService.subscribe(topic, handler)` | `platform/messaging/services/consumer.py` |
| 创建队列 | 调用 `QueueService.create(queue_name)` | `platform/messaging/services/queue.py` |
| 订阅主题 | 调用 `TopicService.subscribe(topic, handler)` | `platform/messaging/services/topic.py` |

**消息类型**：
- **任务消息**：执行特定任务
- **事件消息**：通知状态变更
- **告警消息**：通知异常情况

**相关文件位置**：
- 生产者服务：`platform/messaging/services/producer.py`
- 消费者服务：`platform/messaging/services/consumer.py`
- 队列服务：`platform/messaging/services/queue.py`

---

### deployment - 部署服务

**详细文档**：[deployment 模块文档](../deployment/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建部署 | 调用 `DeploymentService.create(deployment_config)` | `platform/deployment/services/deployment.py` |
| 更新版本 | 调用 `VersionService.update(service_id, version)` | `platform/deployment/services/version.py` |
| 回滚版本 | 调用 `DeploymentService.rollback(deployment_id)` | `platform/deployment/services/deployment.py` |
| 检查状态 | 调用 `DeploymentService.check_status(deployment_id)` | `platform/deployment/services/deployment.py` |

**部署策略**：
- **滚动更新**：逐步替换旧版本
- **蓝绿部署**：新旧版本并存，流量切换
- **金丝雀发布**：小流量测试新版本

**相关文件位置**：
- 部署服务：`platform/deployment/services/deployment.py`
- 版本服务：`platform/deployment/services/version.py`

---

### registry - 服务注册

**详细文档**：[registry 模块文档](../registry/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 注册服务 | 调用 `RegistryService.register(service_info)` | `platform/registry/services/registry.py` |
| 发现服务 | 调用 `DiscoveryService.discover(service_name)` | `platform/registry/services/discovery.py` |
| 健康检查 | 调用 `RegistryService.health_check(service_id)` | `platform/registry/services/registry.py` |
| 注销服务 | 调用 `RegistryService.deregister(service_id)` | `platform/registry/services/registry.py` |

**相关文件位置**：
- 注册服务：`platform/registry/services/registry.py`
- 发现服务：`platform/registry/services/discovery.py`

---

### billing - 计费服务

**详细文档**：[billing 模块文档](../billing/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取套餐 | 调用 `PlanService.list()` | `platform/billing/services/plan.py` |
| 统计用量 | 调用 `UsageService.record(tenant_id, resource, amount)` | `platform/billing/services/usage.py` |
| 生成账单 | 调用 `BillService.generate(tenant_id, period)` | `platform/billing/services/bill.py` |
| 开具发票 | 调用 `InvoiceService.create(bill_id)` | `platform/billing/services/invoice.py` |

**相关文件位置**：
- 套餐服务：`platform/billing/services/plan.py`
- 用量服务：`platform/billing/services/usage.py`
- 账单服务：`platform/billing/services/bill.py`

---

### governance - 治理服务

**详细文档**：[governance 模块文档](../governance/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建策略 | 调用 `PolicyService.create(policy_config)` | `platform/governance/services/policy.py` |
| 执行规则 | 调用 `RuleService.execute(rule_id, context)` | `platform/governance/services/rule.py` |
| 记录审计 | 调用 `AuditService.log(action, resource, user)` | `platform/governance/services/audit.py` |
| 检查合规 | 调用 `ComplianceService.check(entity)` | `platform/governance/services/compliance.py` |

**相关文件位置**：
- 策略服务：`platform/governance/services/policy.py`
- 规则服务：`platform/governance/services/rule.py`
- 审计服务：`platform/governance/services/audit.py`

---

## 🔧 如何扩展

### 添加新的 API 路由

**步骤**：

1. **创建路由文件**：在 `platform/api/routes/` 下创建路由文件
2. **定义路由**：使用路由装饰器定义端点
3. **实现处理器**：实现业务逻辑
4. **定义 Schema**：定义请求和响应的数据模式
5. **注册路由**：在 `platform/api/__init__.py` 中注册
6. **编写测试**：添加单元测试和集成测试
7. **更新文档**：更新 API 文档

### 添加新的中间件

**步骤**：

1. **创建中间件文件**：在 `platform/gateway/middleware/` 下创建中间件
2. **实现接口**：实现 `Middleware` 接口的方法
3. **注册中间件**：在 `platform/gateway/__init__.py` 中注册
4. **配置中间件**：在配置文件中添加中间件配置
5. **编写测试**：添加单元测试

### 添加新的认证方式

**步骤**：

1. **创建认证处理器**：在 `platform/auth/handlers/` 下创建处理器
2. **实现认证逻辑**：实现认证验证逻辑
3. **注册认证方式**：在认证配置中添加新的认证方式
4. **编写测试**：添加认证测试

---

## 🧪 测试

### 测试目录结构

```
tests/
├── unit/platform/           # 单元测试
│   ├── api/
│   │   └── test_routes.py
│   ├── auth/
│   │   └── test_auth.py
│   └── tenants/
│       └── test_tenant.py
├── integration/platform/    # 集成测试
│   ├── test_api_flow.py
│   └── test_auth_flow.py
└── fixtures/               # 测试数据
    └── platform/
        ├── test_users.json
        └── test_tenants.json
```

### 运行测试

| 命令 | 用途 | 前置条件 |
|------|------|----------|
| `make test-platform-unit` | 运行平台层单元测试 | 无 |
| `make test-platform-integration` | 运行平台层集成测试 | Docker 服务启动 |
| `make test-platform-all` | 运行平台层所有测试 | Docker 服务启动 |
| `make test-platform-coverage` | 生成覆盖率报告 | 无 |

### 测试编写规范

| 规范 | 说明 |
|------|------|
| 测试文件命名 | `test_{模块名}.py` |
| 测试类命名 | `Test{功能名}` |
| 测试函数命名 | `test_{功能}_{场景}` |
| Mock 使用 | 使用 `conftest.py` 提供公共 fixture |
| 集成测试标记 | 使用 `@pytest.mark.integration` |

### Mock 示例

**测试 fixture**（在 `conftest.py` 中定义）：
- `mock_db_client`：模拟数据库客户端
- `mock_auth_service`：模拟认证服务
- `mock_tenant_context`：模拟租户上下文
- `test_client`：测试 API 客户端

---

## 📋 最佳实践

### API 开发

| 要求 | 说明 |
|------|------|
| 版本管理 | API 应该有清晰的版本管理，如 `/api/v1/` |
| 文档完整 | API 应该有完整的 OpenAPI 文档 |
| 错误处理 | API 应该有统一的错误响应格式 |
| 权限检查 | API 应该检查用户权限 |

### 认证开发

| 要求 | 说明 |
|------|------|
| 密码加密 | 密码应该使用 bcrypt 加密存储 |
| 令牌管理 | JWT 令牌应该有过期时间 |
| 审计日志 | 认证操作应该记录审计日志 |
| 多因素认证 | 敏感操作应该支持多因素认证 |

### 租户开发

| 要求 | 说明 |
|------|------|
| 数据隔离 | 租户数据应该完全隔离 |
| 配额检查 | 关键操作前应该检查配额 |
| 审计日志 | 租户操作应该记录审计日志 |
| 资源清理 | 租户删除时应该清理所有资源 |

### 网关开发

| 要求 | 说明 |
|------|------|
| 无状态 | 网关应该是无状态的 |
| 限流策略 | 限流应该支持多种策略 |
| 熔断恢复 | 熔断应该支持自动恢复 |
| 健康检查 | 负载均衡应该支持健康检查 |

---

## 🔧 常见问题排查

### API 问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 请求404 | 路由未注册或路径错误 | 1. 检查路由注册<br>2. 检查路由路径 |
| 请求401 | 未认证或令牌无效 | 1. 检查认证令牌<br>2. 检查令牌是否过期 |
| 请求403 | 权限不足 | 1. 检查用户角色<br>2. 检查资源权限 |
| 请求500 | 服务内部错误 | 1. 查看错误日志<br>2. 检查异常堆栈 |

### 认证问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 登录失败 | 用户名或密码错误 | 1. 检查用户名密码<br>2. 检查用户是否被锁定 |
| 令牌验证失败 | 令牌过期或无效 | 1. 检查令牌有效期<br>2. 检查令牌签名 |
| 权限检查失败 | 权限配置错误 | 1. 检查用户角色<br>2. 检查权限配置 |

### 租户问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 租户创建失败 | 配额不足或名称冲突 | 1. 检查配额限制<br>2. 检查租户名称 |
| 数据隔离失败 | 查询未过滤 `tenant_id` | 1. 检查查询语句<br>2. 检查中间件配置 |
| 配额超限 | 资源使用超过限制 | 1. 检查配额配置<br>2. 清理未使用资源 |

### 网关问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 路由失败 | 路由配置错误 | 1. 检查路由配置<br>2. 检查路由优先级 |
| 限流触发 | 请求超过限流阈值 | 1. 检查限流配置<br>2. 增加限流阈值 |
| 熔断触发 | 后端服务不可用 | 1. 检查后端服务状态<br>2. 检查熔断配置 |

---

## 📖 相关链接

- [← 返回平台层文档](../index.md)
- [架构师指南 →](../by-role/architect/index.md)
- [运维指南 →](../by-role/ops/index.md)

---

*最后更新: 2026-04-09*