# 可观测性模块（设计真值：以代码事实为准）

> 说明：本文档描述 infra 的 observability（Tracing/Metrics/Logging）能力。As-Is 已提供 `provider` 选择：`otel`（OpenTelemetry SDK）与 `simple`（内存桩实现），并支持 OTLP 导出与 in_memory 导出（测试）。

> 提供分布式追踪、OpenTelemetry 指标收集能力

---

## 🎯 模块定位

可观测性模块负责统一管理所有**分布式追踪和标准化指标**，基于 OpenTelemetry 标准：

- 分布式追踪（Tracing）
- OpenTelemetry 指标收集（Metrics）
- 上下文传播（Propagators）

### 模块边界说明

| 模块 | 职责 | 特点 | 适用场景 |
|------|------|------|----------|
| **observability** | 分布式追踪 + OTel 标准化指标 | 基于 OpenTelemetry 标准 | 需要全链路追踪、跨服务指标聚合 |
| **logging** | 结构化日志 | 轻量级、灵活 | 业务日志、调试信息 |
| **monitoring** | 系统监控 + 告警 | Prometheus 风格 | 基础设施监控、性能告警 |

> **注意**：三个模块各有侧重，不重复：
> - 需要分布式追踪 → 使用 `observability/`
> - 需要业务日志 → 使用 `logging/`
> - 需要系统指标告警 → 使用 `monitoring/`

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
observability:
  enabled: true
  provider: otel                  # otel, simple
  
  # 追踪配置
  tracing:
    enabled: true
    service_name: ai-platform-infra
    exporter: otlp                  # otlp, jaeger, zipkin
    endpoint: ${OTLP_ENDPOINT:http://localhost:4317}
    sample_rate: 1.0               # 采样率 0-1
    include_attributes:
      - http.method
      - http.url
      - http.status_code
  
  # 指标配置
  metrics:
    enabled: true
    exporter: otlp
    endpoint: ${OTLP_ENDPOINT:http://localhost:4317}
    interval: 60                   # 导出间隔（秒）
  
  # 日志配置
  logging:
    enabled: true
    exporter: otlp
    level: ${LOG_LEVEL:INFO}
    include_trace_context: true
  
  # 资源属性
  resource:
    service.name: ai-platform-infra
    service.version: 1.0.0
    deployment.environment: ${ENV:development}
```

---

## 📖 核心接口定义

### Tracer 接口

**位置**：`infra/observability/tracing.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `start_span` | `name: str`, `context: SpanContext` | `Span` | 启动新 span |
| `get_current_span` | 无 | `Optional[Span]` | 获取当前 span |
| `with_span` | `span: Span` | `ContextManager` | 上下文管理器 |

### Metrics 接口

**位置**：`infra/observability/metrics.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `counter` | `name: str`, `**kwargs` | `Counter` | 创建 Counter |
| `up_down_counter` | `name: str`, `**kwargs` | `UpDownCounter` | 创建 UpDownCounter |
| `histogram` | `name: str`, `**kwargs` | `Histogram` | 创建 Histogram |
| `ObservableCounter` | `name: str`, `callback: Callable` | `Observable` | 可观测 Counter |

### Logger 接口

**位置**：`infra/observability/logging.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `log` | `level: str`, `message: str`, `**kwargs` | `None` | 记录日志 |
| `with_context` | `context: dict` | `ContextManager` | 带上下文记录 |

---

## 🏭 工厂函数

### create_observability

**位置**：`infra/observability/factory.py`

**函数签名**：

```python
def create_observability(
    config: Optional[ObservabilityConfig] = None
) -> ObservabilitySystem:
    """
    创建可观测性系统

    参数：
        config: 可观测性配置（可选）

    返回：
        ObservabilitySystem 实例
    """
```

**使用示例**：

```python
from infra.observability import create_observability

# 创建可观测性系统
obs = create_observability()

# 获取追踪器
tracer = obs.tracer

# 创建 span
with tracer.start_span("process_request") as span:
    span.set_attribute("http.method", "GET")
    span.set_attribute("http.url", "/api/users")
    
    # 子 span
    with tracer.start_span("database_query", child_of=span):
        result = await db.query("SELECT * FROM users")
        span.set_attribute("db.statement", "SELECT * FROM users")
    
    span.set_attribute("http.status_code", 200)

# 记录指标
metrics = obs.metrics
counter = metrics.counter("requests_total")
counter.add(1, attributes={"method": "GET", "status": "200"})

# 记录日志
logger = obs.logger
logger.info("Request processed", 
            trace_id=span.context.trace_id,
            duration_ms=150)
```

> 说明（As-Is）：logger 的 OTLP logs 导出在不同运行环境下差异较大，当前实现以 Python logging + trace 上下文增强为主，若需要 OTLP logs 全链路导出可作为 To-Be 扩展。

---

## 证据索引（Evidence Index｜抽样）

- 配置模型（provider）：`infra/observability/schemas.py`
- 工厂选择器：`infra/observability/factory.py`
- OTel SDK 实现：`infra/observability/otel.py`
- Simple* 内存实现：`infra/observability/tracing.py`
- 单测：`infra/tests/unit/test_observability_otel_provider.py`

---

## 📊 数据模型

### Span

```python
@dataclass
class Span:
    name: str
    context: SpanContext
    parent: Optional[SpanContext] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    status: SpanStatus = SpanStatus.OK
```

### SpanContext

```python
@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    trace_state: Optional[str] = None
    remote: bool = False
```

### MetricDefinition

```python
@dataclass
class MetricDefinition:
    name: str
    description: str
    unit: MetricUnit
    type: MetricType
    labels: List[str]

class MetricType(Enum):
    COUNTER = "counter"
    UP_DOWN_COUNTER = "up_down_counter"
    HISTOGRAM = "histogram"
    OBSERVABLE_COUNTER = "observable_counter"

class MetricUnit(Enum):
    NONE = "none"
    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    BYTES = "bytes"
    REQUESTS = "requests"
```

---

## 🚀 使用示例

### 分布式追踪

```python
from infra.observability import create_observability

obs = create_observability()
tracer = obs.tracer

# 追踪 HTTP 请求
async def handle_request(request):
    with tracer.start_span("handle_request") as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        
        # 调用下游服务
        with tracer.start_span("call_downstream") as child:
            child.set_attribute("downstream.url", "https://api.example.com")
            response = await call_api()
            child.set_attribute("http.status_code", response.status_code)
        
        span.set_attribute("http.status_code", 200)
        
    return response

# 手动传播上下文
context = tracer.extract(headers=request.headers)
with tracer.start_span("child_operation", context=context) as span:
    # 使用提取的上下文继续追踪
    pass
```

### 指标收集

```python
from infra.observability import create_observability

obs = create_observability()
metrics = obs.metrics

# 定义指标
request_counter = metrics.counter(
    "http_server_requests_total",
    description="Total HTTP requests",
    unit="requests"
)

request_duration = metrics.histogram(
    "http_server_request_duration",
    description="HTTP request duration",
    unit="milliseconds"
)

# 记录指标值
def record_metrics(request: Request, response: Response, duration_ms: float):
    request_counter.add(
        1,
        attributes={
            "method": request.method,
            "status_code": response.status_code,
            "path": request.url.path
        }
    )
    
    request_duration.record(
        duration_ms,
        attributes={
            "method": request.method,
            "status_code": response.status_code
        }
    )
```

### 日志与追踪集成

```python
from infra.observability import create_observability

obs = create_observability()
tracer = obs.tracer
logger = obs.logger

# 在追踪中记录日志
async def process_with_logging():
    with tracer.start_span("process_data") as span:
        logger.info(
            "Processing started",
            trace_id=span.context.trace_id,
            span_id=span.context.span_id
        )
        
        try:
            result = await do_processing()
            logger.info("Processing completed", result_id=result.id)
        except Exception as e:
            logger.error(
                "Processing failed",
                error=str(e),
                trace_id=span.context.trace_id
            )
            span.set_status(StatusCode.ERROR, str(e))
            raise
```

### 上下文传播

```python
from infra.observability import create_observability

obs = create_observability()

# 注入上下文到 HTTP 头
def inject_trace_context(headers: dict):
    span = obs.tracer.get_current_span()
    if span:
        obs.propagator.inject(span.context, headers)
    return headers

# 提取上下文
def extract_trace_context(headers: dict) -> SpanContext:
    return obs.propagator.extract(headers)

# HTTP 客户端传播
async def http_client_request(url: str, method: str):
    headers = {}
    inject_trace_context(headers)
    return await http.request(url, method=method, headers=headers)
```

---

## 🔧 扩展指南

### 添加新的导出器

```python
from infra.observability.base import SpanExporter, Span

class CustomExporter(SpanExporter):
    """自定义导出器"""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
    
    def export(self, spans: List[Span]) -> None:
        """导出 spans 到自定义后端"""
        requests.post(
            self.endpoint,
            json=[self._serialize_span(s) for s in spans]
        )

    def shutdown(self) -> None:
        """Exporter shutdown hook"""
        return None
    
    def _serialize_span(self, span: Span) -> dict:
        return {
            "name": span.name,
            "trace_id": span.context.trace_id,
            "span_id": span.context.span_id,
            "attributes": span.attributes
        }
```

### 添加自定义属性

```python
from infra.observability import create_observability

obs = create_observability()

# 在所有 span 中添加资源属性
obs.resource.attributes["host.name"] = platform.node()
obs.resource.attributes["deployment.version"] = "1.0.0"

# 在所有指标中添加属性
obs.metrics.resource.attributes["service.name"] = "ai-platform-infra"
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `observability.tracing.sample_rate` | 0-1 浮点数 | must be 0-1 |
| `observability.metrics.interval` | > 0 | must be > 0 |
| `observability.tracing.exporter` | otlp/jaeger/zipkin | invalid exporter |

---

## 📁 文件结构

```
infra/observability/
├── __init__.py               # 模块导出
├── base.py                   # 核心接口
├── factory.py              # create_observability()
├── schemas.py               # 数据模型
├── tracing.py              # 分布式追踪
└── exporters/
    └── otlp.py            # OTLP 导出器
```

---

*最后更新: 2026-04-11*
