# Layer 3 - 应用层管理

> Management 如何管理应用层

---

## 一、管理接口

### 1.1 App 管理接口

Management 通过调用 app 层的管理接口来管理应用层。

**管理接口定义**：

```python
class AppManager:
    """app 层管理接口"""
    
    async def get_status() -> Status:
        """获取 app 层整体状态"""
        
    async def get_metrics() -> List[Metric]:
        """获取 app 层监控指标"""
        
    async def health_check() -> HealthStatus:
        """检查 app 层健康状态"""
        
    async def get_config() -> Dict[str, Any]:
        """获取 app 层配置"""
        
    async def update_config(config: Dict[str, Any]) -> None:
        """更新 app 层配置"""
        
    async def diagnose() -> DiagnosisResult:
        """诊断 app 层问题"""
```

### 1.2 调用示例

```python
from management.dashboard import AppAdapter

# 创建适配器
adapter = AppAdapter(endpoint="http://localhost:8004")

# 获取状态
status = await adapter.get_status()
print(f"app 状态: {status.status}")

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

Management 可以获取 app 层的整体状态：

| 组件 | 状态类型 | 说明 |
|------|---------|------|
| Gateway | healthy/degraded/unhealthy | 网关状态 |
| Channels | healthy/degraded/unhealthy | 通道连接状态 |
| Runtime | healthy/degraded/unhealthy | 运行时状态 |
| Sessions | healthy/degraded/unhealthy | 会话状态 |
| CLI | healthy/degraded/unhealthy | 命令行工具状态 |
| Workbench | healthy/degraded/unhealthy | 工作台状态 |

---

## 三、指标采集

### 3.1 采集的指标

**Gateway 指标**：
- `gateway.connections.active` - 活跃连接数
- `gateway.messages.per_second` - 每秒消息数
- `gateway.processing.time` - 处理时间

**Channels 指标**：
- `channels.active.count` - 活跃通道数
- `channels.messages.sent` - 已发送消息数
- `channels.messages.received` - 已接收消息数

**Sessions 指标**：
- `sessions.active.count` - 活跃会话数
- `sessions.average.duration` - 平均会话时长
- `sessions.messages.total` - 消息总数

---

## 四、配置管理

### 4.1 可管理的配置项

Management 可以管理 app 层的以下配置：

**Gateway 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| gateway.max_connections | int | 1000 | Gateway 最大连接数 |
| gateway.connection_timeout | int | 60 | 连接超时（秒） |
| gateway.idle_timeout | int | 300 | 空闲超时（秒） |
| gateway.message_size_limit | int | 10485760 | 消息大小限制（字节） |
| gateway.enable_compression | bool | true | 是否启用压缩 |

**Channel 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| channel.timeout | int | 300 | 通道超时时间（秒） |
| channel.reconnect_attempts | int | 3 | 重连尝试次数 |
| channel.message_buffer_size | int | 100 | 消息缓冲区大小 |
| channel.enable_retry | bool | true | 是否启用重试 |

**Runtime 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| runtime.max_instances | int | 50 | Runtime 最大实例数 |
| runtime.instance_timeout | int | 600 | 实例超时（秒） |
| runtime.memory_limit | int | 1073741824 | 内存限制（字节） |
| runtime.cpu_limit | float | 1.0 | CPU 限制（核数） |

**Session 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| session.timeout | int | 1800 | 会话超时（秒） |
| session.max_history | int | 100 | 最大历史记录数 |
| session.enable_persistence | bool | true | 是否持久化 |
| session.cleanup_interval | int | 3600 | 清理间隔（秒） |

### 4.2 配置读取示例

```python
from management.config import ConfigManager

# 创建配置管理器
config_manager = ConfigManager(endpoint="http://localhost:8004")

# 获取 app 层配置
config = await config_manager.get_config("app")

# 读取具体配置项
max_connections = config.get("gateway.max_connections")
session_timeout = config.get("session.timeout")
runtime_instances = config.get("runtime.max_instances")

print(f"Max Connections: {max_connections}")
print(f"Session Timeout: {session_timeout} seconds")
print(f"Max Runtime Instances: {runtime_instances}")
```

### 4.3 配置更新示例

```python
from management.config import ConfigManager

config_manager = ConfigManager(endpoint="http://localhost:8004")

# 更新配置
await config_manager.update_config("app", {
    "gateway.max_connections": 2000,
    "session.timeout": 3600,
    "runtime.max_instances": 100
})

# 回滚配置
await config_manager.rollback("app", version="v1")
```

---

## 五、健康检查

### 5.1 检查项列表

Management 对 app 层进行以下健康检查：

**Gateway 检查**：
- Gateway 是否响应正常
- 连接数是否在合理范围内
- 消息处理是否正常

**Channels 检查**：
- 各通道连接是否正常
- 消息发送/接收是否正常
- 通道重连机制是否有效

**Runtime 检查**：
- Runtime 实例是否运行
- 实例资源使用是否正常
- Agent 执行是否正常

**Sessions 检查**：
- 会话系统是否可用
- 会话持久化是否正常
- 会话清理是否正常

**CLI 检查**：
- CLI 工具是否可访问
- CLI 命令是否执行正常

**Workbench 检查**：
- Workbench 是否可访问
- 功能是否正常

### 5.2 健康检查示例

```python
from management.diagnostics import AppHealthChecker

# 创建健康检查器
checker = AppHealthChecker(endpoint="http://localhost:8004")

# 执行健康检查
health = await checker.health_check()

# 检查结果示例
{
    "status": "healthy",
    "checks": {
        "gateway": {
            "status": "healthy",
            "connections": 156,
            "max_connections": 1000,
            "messages_per_second": 45
        },
        "channels": {
            "status": "healthy",
            "active_channels": 5,
            "telegram": {"status": "connected"},
            "slack": {"status": "connected"},
            "web": {"status": "connected"},
            "discord": {"status": "connected"},
            "cli": {"status": "available"}
        },
        "runtime": {
            "status": "healthy",
            "active_instances": 12,
            "max_instances": 50,
            "memory_usage": "2.5GB",
            "cpu_usage": 0.65
        },
        "sessions": {
            "status": "healthy",
            "active_sessions": 256,
            "average_duration": 1200,
            "persistence": "ok"
        },
        "cli": {
            "status": "healthy",
            "available": true,
            "version": "1.0.0"
        },
        "workbench": {
            "status": "healthy",
            "available": true,
            "users_online": 10
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
| `gateway_connection_failed` | connections == 0 | critical | Gateway 无连接 | 检查网络、重启 Gateway |
| `gateway_connections_near_limit` | connections > 80% | warning | Gateway 连接接近上限 | 扩容 Gateway 或优化连接使用 |
| `channel_disconnected` | status == unhealthy | warning | 通道断开 | 检查通道配置、重连 |
| `channel_message_backlog` | backlog > 1000 | warning | 消息积压 | 增加 consumer 或优化处理速度 |
| `runtime_instance_failed` | instance_status == failed | critical | Runtime 实例失败 | 重启实例、检查日志 |
| `runtime_memory_high` | memory_usage > 90% | warning | Runtime 内存使用高 | 扩容内存或优化 Agent |
| `session_timeout_high` | timeout_rate > 10% | warning | 会话超时率高 | 优化会话处理或增加超时 |
| `message_processing_slow` | latency > 5000ms | warning | 消息处理慢 | 检查 Runtime 负载 |
| `workbench_unavailable` | status == unavailable | critical | Workbench 不可用 | 重启 Workbench 服务 |

### 6.2 告警规则配置示例

```python
from management.alerting import AlertRule, AlertEngine

# 创建告警规则
gateway_connection_rule = AlertRule(
    name="gateway_connection_failed",
    layer="app",
    metric="gateway.connections",
    condition="==",
    threshold=0,
    duration=60,  # 1分钟
    severity="critical",
    message="Gateway 无连接，请立即检查"
)

# 添加到告警引擎
engine = AlertEngine()
engine.add_rule(gateway_connection_rule)

# 评估告警
alerts = await engine.evaluate(metrics)
```

### 6.3 告警通知配置

```yaml
# config/alert_rules.yaml
rules:
  - name: gateway_connection_failed
    layer: app
    metric: gateway.connections
    condition: "=="
    threshold: 0
    duration: 60
    severity: critical
    notifiers:
      - type: email
        recipients:
          - ops@example.com
      - type: slack
        channel: "#critical-alerts"
      - type: webhook
        url: https://hooks.example.com/alerts
```

---

## 七、Dashboard 展示

### 7.1 状态总览

状态总览：

```
┌─────────────────────────────────────┐
│   App Layer Status: Healthy        │
├─────────────────────────────────────┤
│   Gateway:    ✅ Healthy            │
│   Channels:   ✅ Healthy            │
│   Runtime:    ✅ Healthy            │
│   Sessions:   ✅ Healthy            │
│   CLI:        ✅ Healthy            │
│   Workbench:  ✅ Healthy            │
└─────────────────────────────────────┘
```

### 7.2 关键指标

```
┌─────────────────────────────────────────────────────────────┐
│  App 关键指标                                              │
├─────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 活跃连接      │  │ 活跃会话      │  │ 消息速率      │      │
│  │    156       │  │    256      │  │   45 msg/s   │      │
│  │   /1000      │  │   /500      │  │   ▲ 12%      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 运行实例      │  │ 平均延迟      │  │ 通道健康      │      │
│  │    12/50     │  │    120ms    │  │    5/5       │      │
│  │   ▲ 3        │  │   ▼ 5ms      │  │    100%      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Dashboard API调用示例

```python
# Dashboard 聚合状态
from management.dashboard import DashboardAggregator, AppAdapter

aggregator = DashboardAggregator()
aggregator.register_adapter("app", AppAdapter(endpoint="http://localhost:8004"))

# 获取状态
status = await aggregator.aggregate()

# 返回示例
{
    "timestamp": "2026-04-12T00:00:00Z",
    "overall_status": "healthy",
    "layers": {
        "app": {
            "status": "healthy",
            "uptime": 86400,
            "components": {
                "gateway": {
                    "status": "healthy",
                    "connections": 156,
                    "max_connections": 1000,
                    "messages_per_second": 45
                },
                "channels": {
                    "status": "healthy",
                    "active": 5,
                    "details": {
                        "telegram": "connected",
                        "slack": "connected",
                        "web": "connected",
                        "discord": "connected",
                        "cli": "available"
                    }
                },
                "runtime": {
                    "status": "healthy",
                    "active_instances": 12,
                    "max_instances": 50
                },
                "sessions": {
                    "status": "healthy",
                    "active": 256,
                    "average_duration": 1200
                }
            }
        }
    }
}
```

---

## 八、故障诊断

### 8.1 常见诊断场景

当 app 层出现问题时，Management 提供诊断支持：

**Gateway 连接问题诊断**：
- 检查 Gateway 服务状态
- 分析连接数和连接趋势
- 检查网络连通性
- 排查连接超时问题

**通道连接异常排查**：
- 检查各通道连接状态
- 分析断开原因
- 检查认证配置
- 验证网络连通性

**Runtime 实例状态检查**：
- 检查实例运行状态
- 分析资源使用情况
- 检查 Agent 执行日志
- 排查内存/CPU 问题

**会话系统问题定位**：
- 检查会话创建/销毁
- 分析会话超时原因
- 检查持久化状态
- 排查并发问题

### 8.2 诊断示例

```python
from management.diagnostics import AppHealthChecker

checker = AppHealthChecker(endpoint="http://localhost:8004")

# 诊断 Gateway 连接问题
diagnosis = await checker.diagnose_gateway_connection_issue()

# 返回示例
{
    "issue": "gateway_connection_high",
    "severity": "warning",
    "analysis": {
        "current_connections": 850,
        "max_connections": 1000,
        "usage_percent": 85,
        "trend": "increasing",
        "possible_causes": [
            {
                "cause": "Traffic spike",
                "probability": 0.6,
                "suggestions": ["Consider scaling gateway", "Enable connection pool"]
            },
            {
                "cause": "Connection leak",
                "probability": 0.3,
                "suggestions": ["Check connection close logic", "Review timeout settings"]
            },
            {
                "cause": "Attack traffic",
                "probability": 0.1,
                "suggestions": ["Enable rate limiting", "Check traffic source"]
            }
        ]
    },
    "recommended_actions": [
        "Increase max_connections to 2000",
        "Monitor connection trend",
        "Check for connection leaks"
    ]
}
```

### 8.3 诊断流程

```
用户报告 Gateway 连接问题
        │
        ▼
┌───────────────────┐
│  收集诊断数据      │
│  - 连接数         │
│  - 连接趋势        │
│  - 错误日志        │
│  - 服务状态        │
└────────┬──────────┘
        │
         ▼
┌───────────────────┐
│  分析可能原因      │
│  - 流量高峰？      │
│  - 连接泄漏？      │
│  - 攻击流量？      │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  给出修复建议      │
│  - 扩容 Gateway   │
│  - 修复连接泄漏   │
│  - 启用限流       │
└───────────────────┘
```

### 8.4 通道诊断检查项

| 通道类型 | 检查项 | 正常值 | 异常处理 |
|---------|--------|--------|----------|
| Telegram | Bot Token 有效性 | 有效 | 更新 Token |
| Telegram | Webhook 状态 | 已设置 | 重新设置 Webhook |
| Slack | Bot Token 有效性 | 有效 | 更新 Token |
| Slack | 权限范围 | 正确 | 重新配置权限 |
| Web | WebSocket 连接 | 正常 | 检查网络配置 |
| Discord | Bot Token 有效性 | 有效 | 更新 Token |
| Discord | Gateway 连接 | 已连接 | 检查网络/重启 |
| CLI | 命令执行 | 正常 | 检查配置 |

---

## 九、最佳实践

### 9.1 监控最佳实践

**采集策略**：
- 采集间隔：60秒
- 重点指标：连接数、消息处理时间、会话数
- 告警分级：warning、critical

**指标阈值建议**：

| 指标 | Warning | Critical | 说明 |
|------|---------|----------|------|
| Gateway 连接使用率 | > 80% | > 95% | 接近上限需关注 |
| 消息处理延迟 | > 1000ms | > 5000ms | 影响用户体验 |
| 会话超时率 | > 5% | > 15% | 可能配置问题 |
| 通道断开数 | > 1 | > 3 | 通道稳定性问题 |

**告警最佳实践**：
- 连接类告警：快速响应，critical 级别
- 性能类告警：逐步优化，warning 级别
- 容量类告警：提前预警，提前扩容

### 9.2 配置管理最佳实践

**Gateway 配置**：
- 连接数设置：根据并发需求设置，预留 20% 缓冲
- 超时设置：平衡用户体验和资源占用
- 消息大小限制：防止过大的消息影响性能

**Channel 配置**：
- 重连机制：设置合理的重连次数和间隔
- 消息缓冲：设置合适的大小，避免内存溢出
- 超时设置：根据通道特性设置

**Runtime 配置**：
- 实例数限制：根据资源情况设置
- 内存限制：防止 Agent 占用过多资源
- 超时设置：防止长时间运行的 Agent

**Session 配置**：
- 超时时间：根据业务场景设置
- 历史记录：平衡存储和追溯需求
- 清理间隔：定期清理过期会话

### 9.3 故障恢复最佳实践

**Gateway 故障**：
- 快速重启：自动化重启脚本
- 流量切换：多实例部署
- 连接恢复：断线重连机制

**通道故障**：
- 自动重连：实现自动重连逻辑
- 降级处理：必要时降级到其他通道
- Token 管理：定期检查和更新 Token

**Runtime 故障**：
- 实例恢复：自动重启失败实例
- 资源监控：实时监控内存和CPU
- 日志收集：收集详细日志用于排查

**会话故障**：
- 会话恢复：实现会话恢复机制
- 持久化：确保会话数据持久化
- 清理机制：定期清理过期会话

### 9.4 性能优化建议

**Gateway 性能**：
- 使用连接池
- 启用消息压缩
- 优化消息序列化

**通道性能**：
- 异步消息处理
- 批量消息发送
- 合理的缓冲区大小

**Runtime 性能**：
- Agent 实例复用
- 资源限制配置
- 定期清理无用实例

**会话性能**：
- 会话缓存优化
- 批量持久化
- 延迟加载历史

---

## 十、相关文档

### Management 层文档

- [主文档](../index.md) - Management 系统总览
- [Layer 0 - 基础设施层管理](../infra/index.md) - Management 如何管理 infra 层
- [Layer 1 - 核心层管理](../core/index.md) - Management 如何管理 core 层
- [Layer 2 - 平台层管理](../platform/index.md) - Management 如何管理 platform 层

### app 层文档

- [aiPlat-app 文档](../../../aiPlat-app/docs/index.md) - app 层功能文档

---

*最后更新:2026-04-12  
**版本**：v1.0  
**维护团队**：AI Platform Team
