# 监控模块

> 提供系统监控、指标采集、健康检查、告警规则等能力

---

## 🎯 模块定位

监控模块负责统一监控**系统运行状态**，支持：
- 指标采集（Counter、Gauge、Histogram）
- 健康检查
- 告警规则
- 心跳监控
- 性能指标

### 模块边界说明

| 模块 | 职责 | 特点 | 适用场景 |
|------|------|------|----------|
| **monitoring** | 系统监控 + 告警 | Prometheus 风格 | 基础设施监控、性能告警 |
| **observability** | 分布式追踪 + OTel 指标 | OpenTelemetry 标准 | 全链路追踪、跨服务指标 |
| **logging** | 业务日志、调试信息 | 轻量级、灵活 | 应用日志、调试、审计 |

> **注意**：三个模块各有侧重，不重复：
> - 需要系统指标告警 → 使用 `monitoring/`
> - 需要分布式追踪 → 使用 `observability/`
> - 需要业务日志 → 使用 `logging/`

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
monitoring:
  enabled: true
  port: 9090
  
  # 指标配置
  metrics:
    enabled: true
    prefix: ai_platform_infra
    labels:
      env: ${ENV:development}
      service: infra
    export_interval: 60
  
  # 健康检查
  health_check:
    enabled: true
    path: /health
    interval: 30
  
  # 心跳监控
  heartbeat:
    enabled: true
    interval: 10
    timeout: 30
  
  # 告警规则
  alerts:
    - name: high_cpu
      metric: system.cpu.usage
      condition: "> 80"
      level: warning
      cooldown: 300
    - name: high_memory
      metric: system.memory.usage
      condition: "> 90"
      level: critical
      cooldown: 60
```

---

## 📖 核心接口定义

### MetricsCollector 接口

**位置**：`infra/monitoring/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `counter` | `name: str`, `**kwargs` | `Counter` | 创建 Counter 指标 |
| `gauge` | `name: str`, `**kwargs` | `Gauge` | 创建 Gauge 指标 |
| `histogram` | `name: str`, `**kwargs` | `Histogram` | 创建 Histogram 指标 |
| `record` | `name: str`, `value: float`, `labels: dict` | `None` | 记录指标值 |
| `get_metrics` | 无 | `List[Metric]` | 获取所有指标 |
| `export` | 无 | `str` | 导出为 Prometheus 格式 |

### HealthChecker 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `register_check` | `name: str`, `check_fn: Callable` | `None` | 注册健康检查 |
| `check` | 无 | `HealthStatus` | 执行所有健康检查 |
| `check_one` | `name: str` | `HealthStatus` | 执行单个检查 |

### AlertManager 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add_rule` | `rule: AlertRule` | `None` | 添加告警规则 |
| `remove_rule` | `name: str` | `None` | 移除告警规则 |
| `trigger` | `alert: Alert` | `None` | 触发告警 |
| `list_rules` | 无 | `List[AlertRule]` | 列出所有规则 |
| `list_alerts` | 无 | `List[Alert]` | 列出活动告警 |

---

## 🏭 工厂函数

### create_monitoring_system

**位置**：`infra/monitoring/factory.py`

**函数签名**：

```python
def create_monitoring_system(
    config: Optional[MonitoringConfig] = None
) -> MonitoringSystem:
    """
    创建监控系统

    参数：
        config: 监控配置（可选）

    返回：
        MonitoringSystem 实例
    """
```

**使用示例**：

```python
from infra.monitoring import create_monitoring_system

# 创建监控系统
monitor = create_monitoring_system()

# 获取指标收集器
metrics = monitor.metrics

# 创建指标
counter = metrics.counter("requests_total", labels={"method": "GET"})
counter.inc()

gauge = metrics.gauge("memory_usage", labels={"host": "localhost"})
gauge.set(1024)

histogram = metrics.histogram("request_duration", labels={"endpoint": "/api"})
histogram.observe(0.125)

# 健康检查
monitor.health.register_check("database", check_db_health)
status = monitor.health.check()

# 告警规则
monitor.alerts.add_rule(AlertRule(
    name="high_error_rate",
    metric="requests.errors",
    condition="> 0.1",
    level=AlertLevel.ERROR,
    cooldown=300
))
```

---

## 📊 数据模型

### Metric

```python
@dataclass
class Metric:
    name: str
    value: Union[int, float]
    timestamp: float
    labels: Dict[str, str]
    metric_type: MetricType

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
```

### HealthStatus

```python
@dataclass
class HealthStatus:
    healthy: bool
    checks: Dict[str, bool]
    details: Dict[str, Any]
    timestamp: datetime
```

### AlertRule

```python
@dataclass
class AlertRule:
    name: str
    description: str
    metric: str
    condition: str  # e.g., "> 80", "< 10"
    level: AlertLevel
    cooldown: int = 300

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

### Alert

```python
@dataclass
class Alert:
    rule: AlertRule
    value: float
    timestamp: datetime
    fired: bool = False
    resolved: bool = False
```

---

## 🚀 使用示例

### 指标采集

```python
from infra.monitoring import create_monitoring_system

monitor = create_monitoring_system()
metrics = monitor.metrics

# Counter 指标
requests_total = metrics.counter(
    "http_requests_total",
    labels={"method": "POST", "endpoint": "/api/users"}
)
requests_total.inc()

# Gauge 指标
cpu_usage = metrics.gauge(
    "system_cpu_usage_percent",
    labels={"host": "server-1"}
)
cpu_usage.set(75.5)

# Histogram 指标
request_duration = metrics.histogram(
    "http_request_duration_seconds",
    labels={"method": "GET", "endpoint": "/api/data"}
)
request_duration.observe(0.125)  # 125ms

# 导出 Prometheus 格式
print(metrics.export())
```

### 健康检查

```python
from infra.monitoring import create_monitoring_system, HealthStatus

monitor = create_monitoring_system()

# 注册健康检查
@monitor.health.register("database")
async def check_database() -> HealthStatus:
    try:
        await db.ping()
        return HealthStatus(healthy=True, details={"connected": True})
    except Exception as e:
        return HealthStatus(healthy=False, details={"error": str(e)})

@monitor.health.register("redis")
async def check_redis() -> HealthStatus:
    try:
        await redis.ping()
        return HealthStatus(healthy=True)
    except Exception as e:
        return HealthStatus(healthy=False, details={"error": str(e)})

# 执行健康检查
status = await monitor.health.check()
print(f"Overall: {'healthy' if status.healthy else 'unhealthy'}")
print(status.checks)
```

### 告警管理

```python
from infra.monitoring import create_monitoring_system, AlertRule, AlertLevel

monitor = create_monitoring_system()
alerts = monitor.alerts

# 添加告警规则
alerts.add_rule(AlertRule(
    name="high_error_rate",
    description="Error rate exceeds threshold",
    metric="http_requests_errors_total",
    condition="> 0.05",  # 5%
    level=AlertLevel.WARNING,
    cooldown=300
))

alerts.add_rule(AlertRule(
    name="high_latency",
    description="Request latency too high",
    metric="http_request_duration_p99",
    condition="> 1.0",  # 1 second
    level=AlertLevel.CRITICAL,
    cooldown=60
))

# 触发告警
alerts.trigger(Alert(
    rule=alerts.get_rule("high_error_rate"),
    value=0.08,
    timestamp=datetime.now()
))

# 查看告警
active_alerts = alerts.list_alerts()
for alert in active_alerts:
    print(f"{alert.rule.name}: {alert.value}")
```

### 监控装饰器

```python
from infra.monitoring import monitor

@monitor.track_duration("function_duration_seconds")
@monitor.track_errors("function_errors_total")
async def process_data(data):
    # 函数执行时间和错误会被自动记录
    result = await transform(data)
    return result
```

---

## 🔧 扩展指南

### 添加新的指标类型

```python
from infra.monitoring.base import MetricsCollector

class CustomMetricsCollector(MetricsCollector):
    """自定义指标收集器"""
    
    def summary(self, name: str, **kwargs) -> Summary:
        """Summary 指标"""
        return Summary(name, **kwargs)
```

### 添加新的健康检查

```python
from infra.monitoring.health import HealthChecker

class CustomHealthCheck(HealthChecker):
    """自定义健康检查"""
    
    async def check_kafka(self) -> HealthStatus:
        """检查 Kafka 连接"""
        try:
            producer = self._kafka_producer
            metadata = producer.topics()
            return HealthStatus(healthy=True, details={"topics": len(metadata)})
        except Exception as e:
            return HealthStatus(healthy=False, details={"error": str(e)})
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `monitoring.port` | 1-65535 | must be 1-65535 |
| `monitoring.health_check.interval` | > 0 | must be > 0 |
| `monitoring.heartbeat.interval` | > 0 | must be > 0 |
| `monitoring.alerts.cooldown` | >= 0 | must be >= 0 |

---

## 📁 文件结构

```
infra/monitoring/
├── __init__.py               # 模块导出
├── base.py                   # 核心接口
├── factory.py               # create_monitoring_system()
├── schemas.py               # 数据模型
└── collector.py             # 指标收集器
```

---

*最后更新: 2026-04-11*