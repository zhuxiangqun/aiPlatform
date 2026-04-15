# 日志模块

> 提供轻量级结构化日志能力

---

## 🎯 模块定位

日志模块负责统一管理**业务日志和调试信息**，支持：
- 结构化日志（JSON）
- 日志级别控制
- 日志格式化
- 多输出目标（文件、控制台、syslog）
- 日志轮转

### 模块边界说明

| 模块 | 职责 | 特点 | 适用场景 |
|------|------|------|----------|
| **logging** | 业务日志、调试信息 | 轻量级、灵活 | 应用日志、调试、审计 |
| **observability** | 分布式追踪 + OTel 指标 | OpenTelemetry 标准 | 全链路追踪、跨服务指标 |
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
logging:
  level: ${LOG_LEVEL:INFO}           # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: json                       # json, text, console
  
  # 输出目标
  output:
    - console
    - file
  
  # 文件输出
  file:
    path: /var/log/ai-platform/infra.log
    max_size: 100MB
    backup_count: 10
    encoding: utf-8
  
  # 结构化日志
  structured:
    include_trace_id: true          # 包含追踪ID
    include_request_id: true        # 包含请求ID
    include_user_id: true           # 包含用户ID
    exclude_fields:                 # 排除的字段
      - password
      - token
      - secret
  
  # 日志级别模块配置
  loggers:
    infra.database: INFO
    infra.llm: DEBUG
    infra.http: WARNING
```

---

## 📖 核心接口定义

### Logger 接口

**位置**：`infra/logging/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `debug` | `msg: str`, `**kwargs` | `None` | 调试级别日志 |
| `info` | `msg: str`, `**kwargs` | `None` | 信息级别日志 |
| `warning` | `msg: str`, `**kwargs` | `None` | 警告级别日志 |
| `error` | `msg: str`, `**kwargs` | `None` | 错误级别日志 |
| `critical` | `msg: str`, `**kwargs` | `None` | 严重级别日志 |
| `log` | `level: str`, `msg: str`, `**kwargs` | `None` | 通用日志方法 |
| `child` | `name: str` | `Logger` | 创建子日志器 |

### StructuredLogger 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `log_event` | `event: LogEvent` | `None` | 记录结构化日志事件 |
| `log_request` | `request: RequestLog` | `None` | 记录请求日志 |
| `log_response` | `response: ResponseLog` | `None` | 记录响应日志 |
| `log_exception` | `exc: Exception`, `context: dict` | `None` | 记录异常日志 |

---

### Formatter 接口

**位置**：`infra/logging/formatter.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `format` | `record: LogRecord` | `str` | 格式化日志记录 |
| `format_exception` | `exc: Exception` | `str` | 格式化异常 |

**内置Formatter**：

| Formatter | 说明 |
|-----------|------|
| `JSONFormatter` | JSON 格式输出 |
| `TextFormatter` | 文本格式输出 |
| `ConsoleFormatter` | 控制台彩色输出 |

---

## 🏭 工厂函数

### create_logger

**位置**：`infra/logging/factory.py`

**函数签名**：

```python
def create_logger(
    name: str,
    config: Optional[LoggingConfig] = None
) -> Logger:
    """
    创建日志记录器

    参数：
        name: 日志记录器名称
        config: 日志配置（可选）

    返回：
        Logger 实例
    """
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 日志记录器名称 |
| `config.level` | str | "INFO" | 日志级别 |
| `config.format` | str | "json" | 日志格式 |
| `config.output` | List[str] | ["console"] | 输出目标 |

**使用示例**：

```python
from infra.logging import create_logger

# 创建日志记录器
logger = create_logger("infra.database")

# 记录日志
logger.info("Database connection established", 
            host="localhost", port=5432)

logger.error("Query failed", 
             error="timeout", query="SELECT * FROM users")

# 子日志器
child_logger = logger.child("postgres")
child_logger.info("Connection pool initialized", size=20)
```

---

## 📊 数据模型

### LoggingConfig

```python
@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"
    output: List[str] = field(default_factory=lambda: ["console"])
    file: Optional[FileConfig] = None
    structured: Optional[StructuredConfig] = None
    loggers: Dict[str, str] = field(default_factory=dict)
```

### LogEvent

```python
@dataclass
class LogEvent:
    timestamp: datetime
    level: str
    message: str
    logger: str
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
```

### LogRecord

```python
@dataclass
class LogRecord:
    level: str
    message: str
    timestamp: datetime
    logger_name: str
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
```

---

## 🚀 使用示例

### 基本日志记录

```python
from infra.logging import create_logger

logger = create_logger("my_module")

# 不同级别日志
logger.debug("Debug message", extra={"key": "value"})
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message", error_code=500)
logger.critical("Critical message")
```

### 结构化日志

```python
from infra.logging import create_logger, StructuredLogger

logger = create_logger("api")

# 结构化日志
logger.info(
    "API request",
    trace_id="abc123",
    request_id="req456",
    user_id="user789",
    method="POST",
    path="/api/users",
    status_code=200,
    duration_ms=150
)

# 异常日志
try:
    result = query_database()
except Exception as e:
    logger.error(
        "Database query failed",
        exception=e,
        trace_id="abc123",
        query="SELECT * FROM users"
    )
```

### 日志上下文

```python
from infra.logging import create_logger, LogContext

logger = create_logger("api")

# 使用上下文管理器
with LogContext(trace_id="abc123", user_id="user789"):
    logger.info("Processing request")
    # 自动包含 trace_id 和 user_id
    
    # 子上下文
    with LogContext(request_id="req456"):
        logger.info("Calling external service")
        # 包含 trace_id, user_id, request_id
    
    logger.info("Request completed")
    # 回到上一层上下文
```

### 日志过滤

```python
from infra.logging import create_logger, LogFilter

class SensitiveDataFilter(LogFilter):
    """敏感数据过滤"""
    
    SENSITIVE_FIELDS = {"password", "token", "secret", "api_key"}
    
    def filter(self, record: LogRecord) -> bool:
        for field in self.SENSITIVE_FIELDS:
            if field in record.extra:
                record.extra[field] = "***REDACTED***"
        return True

logger = create_logger("security")
logger.add_filter(SensitiveDataFilter())

logger.info("User login", 
            user_id="user123", 
            password="secret123")  # 会被过滤
```

---

## 🔧 扩展指南

### 添加新的输出目标

**文件**：`infra/logging/outputs/syslog.py`

```python
from infra.logging.outputs.base import LogOutput

class SyslogOutput(LogOutput):
    """Syslog 输出"""
    
    def __init__(self, host: str = "localhost", port: int = 514):
        import logging.handlers
        self.handler = logging.handlers.SysLogHandler(
            address=(host, port)
        )
    
    def emit(self, record: LogRecord):
        self.handler.emit(record)
    
    def close(self):
        self.handler.close()
```

### 添加新的格式化器

**文件**：`infra/logging/formatters/custom.py`

```python
from infra.logging.formatter import Formatter
from infra.logging.schemas import LogRecord

class CustomFormatter(Formatter):
    """自定义格式化器"""
    
    def format(self, record: LogRecord) -> str:
        return f"[{record.level}] {record.timestamp}: {record.message}"
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `logging.level` | DEBUG/INFO/WARNING/ERROR/CRITICAL | invalid log level |
| `logging.format` | json/text/console | invalid format |
| `logging.file.max_size` | > 0 | must be > 0 |
| `logging.file.backup_count` | >= 0 | must be >= 0 |

---

## 📁 文件结构

```
infra/logging/
├── __init__.py                 # 模块导出
├── base.py                    # Logger 接口
├── factory.py                 # create_logger()
├── schemas.py                  # 数据模型
├── formatters/
│   ├── json_formatter.py    # JSON 格式化器
│   ├── text_formatter.py    # 文本格式化器
│   └── console_formatter.py # 控制台格式化器
├── outputs/
│   ├── console.py           # 控制台输出
│   ├── file.py              # 文件输出
│   └── syslog.py           # Syslog 输出
└── filters/
    └── sensitive_data.py    # 敏感数据过滤
```

---

*最后更新: 2026-04-11*