# Layer 2 - 平台层管理

> Management 如何管理平台层

---

## 一、管理接口

### 1.1 Platform 管理接口

Management 通过调用 platform 层的管理接口来管理平台层。

**管理接口定义**：

```python
class PlatformManager:
    """platform 层管理接口"""
    
    async def get_status() -> Status:
        """获取 platform 层整体状态"""
        
    async def get_metrics() -> List[Metric]:
        """获取 platform 层监控指标"""
        
    async def health_check() -> HealthStatus:
        """检查 platform 层健康状态"""
        
    async def get_config() -> Dict[str, Any]:
        """获取 platform 层配置"""
        
    async def update_config(config: Dict[str, Any]) -> None:
        """更新 platform 层配置"""
        
    async def diagnose() -> DiagnosisResult:
        """诊断 platform 层问题"""
```

### 1.2 调用示例

```python
from management.dashboard import PlatformAdapter

# 创建适配器
adapter = PlatformAdapter(endpoint="http://localhost:8003")

# 获取状态
status = await adapter.get_status()
print(f"platform 状态: {status.status}")

# 获取指标
metrics = await adapter.get_metrics()
for metric in metrics:
    print(f"{metric.name}: {metric.value}")

# 健康检查
health = await adapter.health_check()
```

---

## 二、状态管理

### 2.1 整体状态

Management 可以获取 platform 层的整体状态：

| 组件 | 状态类型 | 说明 |
|------|---------|------|
| API | healthy/degraded/unhealthy | API 服务状态 |
| Auth | healthy/degraded/unhealthy | 认证服务状态 |
| Tenants | healthy/degraded/unhealthy | 租户服务状态 |
| Billing | healthy/degraded/unhealthy | 计费服务状态 |
| Gateway | healthy/degraded/unhealthy | 网关服务状态 |
| Registry | healthy/degraded/unhealthy | 注册服务状态 |

---

## 三、指标采集

### 3.1 采集的指标

**API 指标**：
- `api.requests.total` - 请求总数
- `api.requests.per_second` - 每秒请求数
- `api.response.time.avg` - 平均响应时间
- `api.error.rate` - 错误率

**Auth 指标**：
- `auth.tokens.active` - 活跃 Token 数
- `auth.authentications.total` - 认证总次数
- `auth.failed.attempts` - 失败尝试数

**Tenant 指标**：
- `tenants.total` - 租户总数
- `tenants.active.users` - 活跃用户数
- `tenants.storage.usage` - 存储使用量

---

## 四、配置管理

###4.1 可管理的配置项

Management 可以管理 platform 层的以下配置：

**API 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| api.rate_limit.requests | int | 1000 | 每分钟最大请求数 |
| api.rate_limit.burst | int | 100 | 突发请求数 |
| api.timeout.seconds | int | 30 | API 超时时间（秒） |
| api.max_body_size | int | 10485760 | 最大请求体大小（字节） |
| api.cors.origins | list | [] | CORS 允许的源 |

**Auth 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| auth.token.expiration | int | 3600 | Token 过期时间（秒） |
| auth.token.refresh_expiration | int | 604800 | 刷新Token 过期时间（秒） |
| auth.token.issuer | string | "aiplat" | Token 签发者 |
| auth.api_key.max_keys | int | 10 | 每个 API Key 最大数量 |
| auth.api_key.rotation_days | int | 90 | API Key 轮换周期（天） |

**Tenant 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| tenant.quota.storage | int | 10737418240 | 租户存储配额（字节） |
| tenant.quota.requests | int | 100000 | 租户请求数配额 |
| tenant.quota.tokens | int | 1000000 | 租户 Token 配额 |
| tenant.max_users | int | 100 | 租户最大用户数 |
| tenant.max_agents | int | 50 | 租户最大 Agent 数 |

**Billing 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| billing.billing_cycle | int | 30 | 计费周期（天） |
| billing.grace_period | int | 7 | 宽限期（天） |
| billing.overage_rate | float | 0.1 | 超额费率 |

### 4.2 配置读取示例

```python
from management.config import ConfigManager

# 创建配置管理器
config_manager = ConfigManager(endpoint="http://localhost:8003")

# 获取 platform 层配置
config = await config_manager.get_config("platform")

# 读取具体配置项
api_rate_limit = config.get("api.rate_limit.requests")
token_expiration = config.get("auth.token.expiration")
tenant_quota = config.get("tenant.quota.storage")

print(f"API Rate Limit: {api_rate_limit} req/min")
print(f"Token Expiration: {token_expiration} seconds")
print(f"Tenant Storage Quota: {tenant_quota} bytes")
```

### 4.3 配置更新示例

```python
from management.config import ConfigManager

config_manager = ConfigManager(endpoint="http://localhost:8003")

# 更新配置
await config_manager.update_config("platform", {
    "api.rate_limit.requests": 2000,
    "auth.token.expiration": 7200,
    "tenant.quota.storage": 21474836480 # 20GB
})

# 回滚配置
await config_manager.rollback("platform", version="v1")
```

---

## 五、健康检查

### 5.1 检查项列表

Management 对 platform 层进行以下健康检查：

**API 服务检查**：
- 服务是否响应正常
- 响应时间是否在阈值内
- 错误率是否低于阈值

**Auth 服务检查**：
- 认证服务是否可用
- Token 签发是否正常
- API Key 验证是否正常

**Tenant 服务检查**：
- 租户服务是否正常
- 租户配额是否充足
- 租户隔离是否有效

**Billing 服务检查**：
- 计费服务是否运行
- 账单生成是否正常
-费用计算是否准确

**Gateway 检查**：
- 网关是否健康
- 路由是否正常
- 负载均衡是否正常

**Registry 检查**：
- 注册服务是否正常
- 服务发现是否可用
- 心跳检测是否正常

### 5.2 健康检查示例

```python
from management.diagnostics import PlatformHealthChecker

# 创建健康检查器
checker = PlatformHealthChecker(endpoint="http://localhost:8003")

# 执行健康检查
health = await checker.health_check()

# 检查结果示例
{
    "status": "healthy",
    "checks": {
        "api": {
            "status": "healthy",
            "response_time": 0.05,
            "error_rate": 0.001
        },
        "auth": {
            "status": "healthy",
            "token_issuance": "ok",
            "api_key_validation": "ok"
        },
        "tenants": {
            "status": "healthy",
            "total_tenants": 10,
            "active_tenants": 8,
            "quota_usage": 0.65
        },
        "billing": {
            "status": "healthy",
            "billing_cycle": "active",
            "last_billing": "2026-04-01"
        },
        "gateway": {
            "status": "healthy",
            "routes": 15,
            "backends": 5
        },
        "registry": {
            "status": "healthy",
            "services": 10,
            "instances": 25
        }
    },
    "uptime": 86400,
    "last_check": "2026-04-12T00:00:00Z"
}
```

### 5.3 健康状态判断

| 状态 | 条件 | 说明 |
|------|------|------|
| healthy | 所有检查项通过 | 系统运行正常 |
| degraded | 部分检查项警告 | 系统运行但性能下降 |
| unhealthy | 关键检查项失败 | 系统无法正常提供服务 |

---

## 六、告警规则

### 6.1 预定义告警规则

| 规则名称 | 条件 | 严重性 | 说明 | 处理建议 |
|---------|------|--------|------|----------|
| `api_error_rate_high` | error_rate > 5% | warning | API 错误率过高 | 检查 API 日志，排查错误源 |
| `api_error_rate_critical` | error_rate > 20% | critical | API 错误率极高 | 立即排查，可能需要回滚 |
| `api_response_time_slow` | latency > 1000ms | warning | API 响应慢 | 检查后端服务负载 |
| `api_response_time_critical` | latency > 5000ms | critical | API 响应极慢 | 检查后端服务是否正常 |
| `auth_service_down` | status == unhealthy | critical | 认证服务不可用 | 重启认证服务 |
| `auth_token_failures_high` | failure_rate > 5% | warning | Token 验证失败率高 | 检查 Token 配置和密钥 |
| `tenant_quota_exceeded` | usage > quota | warning | 租户配额超限 | 提醒租户升级套餐 |
| `tenant_storage_full` | usage > 95% | critical | 租户存储快满 | 清理数据或扩容 |
| `billing_service_error` | status == unhealthy | critical | 计费服务错误 | 检查计费服务日志 |

### 6.2 告警规则配置示例

```python
from management.alerting import AlertRule, AlertEngine

# 创建告警规则
api_error_rule = AlertRule(
    name="api_error_rate_high",
    layer="platform",
    metric="api.error_rate",
    condition=">",
    threshold=0.05,# 5%
    duration=300,  # 5分钟
    severity="warning",
    message="API 错误率过高: {value}%"
)

# 添加到告警引擎
engine = AlertEngine()
engine.add_rule(api_error_rule)

# 评估告警
alerts = await engine.evaluate(metrics)
```

### 6.3 告警通知配置

```yaml
# config/alert_rules.yaml
rules:
  - name: api_error_rate_high
    layer: platform
    metric: api.error_rate
    condition: ">"
    threshold: 0.05
    duration: 300
    severity: warning
    notifiers:
      - type: email
        recipients:
          - ops@example.com
      - type: slack
        channel: "#alerts"
```

---

## 七、Dashboard 展示

### 7.1 状态总览

状态总览：

```
┌─────────────────────────────────────┐
│   Platform Layer Status: Healthy   │
├─────────────────────────────────────┤
│   API:        ✅ Healthy            │
│   Auth:       ✅ Healthy            │
│   Tenants:    ✅ Healthy            │
│   Billing:    ✅ Healthy            │
│   Gateway:    ✅ Healthy            │
│   Registry:   ✅ Healthy            │
└─────────────────────────────────────┘
```

### 7.2 关键指标

```
┌─────────────────────────────────────────────────────────────┐
│  Platform 关键指标                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │API 请求      │  │ 认证成功     │  │ 租户健康      │      │
│  │  1,250 req/m │  │   99.5%     │  │    8/10      │      │
│  │  ▲ 15%      │  │   ▼ 0.2%     │  │    ▲ 2       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 响应时间     │  │ 错误率      │  │ 活跃用户      │      │
│  │   45ms      │  │   0.5%      │  │    256       │      │
│  │   ▼ 5ms     │  │   ▲ 0.1%     │  │    ▲ 12      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 API调用示例

```python
# Dashboard 聚合状态
from management.dashboard import DashboardAggregator, PlatformAdapter

aggregator = DashboardAggregator()
aggregator.register_adapter("platform", PlatformAdapter(endpoint="http://localhost:8003"))

# 获取状态
status = await aggregator.aggregate()

# 返回示例
{
    "timestamp": "2026-04-12T00:00:00Z",
    "overall_status": "healthy",
    "layers": {
        "platform": {
            "status": "healthy",
            "uptime": 86400,
            "components": {
                "api": {"status": "healthy", "requests": 1250},
                "auth": {"status": "healthy", "success_rate": 0.995},
                "tenants": {"status": "healthy", "active": 8, "total": 10},
                "billing": {"status": "healthy", "cycle": "active"},
                "gateway": {"status": "healthy", "routes": 15},
                "registry": {"status": "healthy", "services": 10}
            }
        }
    }
}
```

---

## 八、故障诊断

### 8.1 常见诊断场景

当 platform 层出现问题时，Management 提供诊断支持：

**API 响应问题诊断**：
- 检查 API 服务状态
- 分析响应时间分布
- 检查错误日志
- 排查后端依赖

**认证失败排查**：
- 检查认证服务状态
- 验证 Token 签发
- 检查 API Key 配置
- 排查权限问题

**租户配额检查**：
- 查看配额使用情况
- 分析配额消耗趋势
- 识别异常消耗源
- 提供扩容建议

**服务依赖检查**：
- 检查服务注册状态
- 验证服务发现
- 检查服务依赖链
- 排查网络连通性

### 8.2 诊断示例

```python
from management.diagnostics import PlatformHealthChecker

checker = PlatformHealthChecker(endpoint="http://localhost:8003")

# 诊断 API 响应问题
diagnosis = await checker.diagnose_api_response_issue()

# 返回示例
{
    "issue": "api_response_slow",
    "severity": "warning",
    "analysis": {
        "response_time": {
            "current": 1500,  # ms
            "threshold": 1000,# ms
            "trend": "increasing"
        },
        "possible_causes": [
            {
                "cause": "Backend service overload",
                "probability": 0.8,
                "suggestions": ["Scale backend services", "Check resource usage"]
            },
            {
                "cause": "Network latency",
                "probability": 0.15,
                "suggestions": ["Check network connectivity", "Reduce request payload"]
            },
            {
                "cause": "Database slow query",
                "probability": 0.05,
                "suggestions": ["Analyze slow queries", "Add database indexes"]
            }
        ]
    },
    "recommended_actions": [
        "Check backend service CPU usage",
        "Review recent deployment changes",
        "Analyze API call patterns"
    ]
}
```

### 8.3 诊断流程

```
用户报告 API 响应慢
        │
        ▼
┌───────────────────┐
│  收集诊断数据     │
│  - 响应时间指标   │
│  - 错误日志       │
│  - 服务状态       │
└────────┬──────────┘
        │
         ▼
┌───────────────────┐
│  分析可能原因      │
│  - 后端过载？      │
│  - 网络延迟？      │
│  - 数据库慢？      │
└────────┬──────────┘
        │
         ▼
┌───────────────────┐
│  给出修复建议      │
│  - 扩容后端       │
│  - 优化数据库     │
│  - 减少请求量     │
└───────────────────┘
```

---

## 九、最佳实践

### 9.1 监控最佳实践

**采集策略**：
- 采集间隔：60秒
- 重点指标：API 响应时间、错误率、认证成功率
- 告警分级：warning、critical

**指标阈值建议**：

| 指标 | Warning | Critical | 说明 |
|------|---------|----------|------|
| API 错误率 | > 5% | > 20% | 超过阈值需关注 |
| API 响应时间 | > 500ms | > 2000ms | 影响用户体验 |
| 认证失败率 | > 1% | > 5% | 可能攻击或配置问题 |
| 租户配额使用 | > 80% | > 95% | 需要及时扩容 |

**告警最佳实践**：
- 分级告警：warning 用于提醒，critical 用于紧急
- 避免告警风暴：设置告警静默期
- 提供可操作建议：告警内容包含处理建议

### 9.2 配置管理最佳实践

**API 配置**：
- 合理设置限流：防止过载，但不要过低影响业务
- 设置合适的超时：平衡用户体验和资源占用
- 定期审查 CORS 配置：确保安全

**认证配置**：
- Token 过期时间：根据业务需求设置
- 定期轮换密钥：建议90天轮换
- API Key 管理：限制数量，定期清理

**租户配置**：
- 监控配额使用：提前预警
- 灵活配置套餐：满足不同需求
- 自动扩容机制：防止服务中断

### 9.3 故障恢复最佳实践

**API 服务故障**：
- 快速回滚：有版本回滚机制
- 流量切换：多实例部署
- 限流降级：保护后端服务

**认证服务故障**：
- Token 缓存：减少认证服务压力
- 备用认证：本地 Token 验证
- 快速重启：自动化运维

**租户隔离故障**：
- 租户隔离检查：定期验证
- 配额自动管理：避免手动错误
- 多租户监控：独立监控每个租户

---

## 十、相关文档

### Management 层文档

- [主文档](../index.md) - Management 系统总览
- [Layer 0 - 基础设施层管理](../infra/index.md) - Management 如何管理 infra 层
- [Layer 1 - 核心层管理](../core/index.md) - Management 如何管理 core 层
- [Layer 3 - 应用层管理](../app/index.md) - Management 如何管理 app 层

### platform 层文档

- [aiPlat-platform 文档](../../../aiPlat-platform/docs/index.md) - platform 层功能文档

---

*最后更新:2026-04-12  
**版本**：v1.0  
**维护团队**：AI Platform Team
