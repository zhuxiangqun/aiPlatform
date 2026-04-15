# 工具模块

> 提供通用工具函数、错误处理、验证器、加密等能力

---

## 🎯 模块定位

工具模块负责提供所有通用工具函数，支持：
- 错误处理
- 输入验证
- 安全工具
- 异步工具
- 通用辅助函数

### 模块边界说明

| 子模块 | 职责 | 说明 |
|--------|------|------|
| `errors` | 错误处理 | ErrorHandler、ErrorEvent、ErrorCategory |
| `validation` | 输入验证 | InputValidator、ValidationResult、规则 |
| `security` | 安全工具 | 哈希、加密、令牌生成 |
| `async_utils` | 异步工具 | 重试、超时、并发控制 |

> **注意**：随着系统增长，此模块可能拆分为独立子模块。建议新功能优先考虑专用模块。

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
utils:
  # 错误处理配置
  error:
    include_trace: true
    include_context: true
    default_level: error
    log_errors: true
  
  # 验证配置
  validation:
    strict_mode: false
    trim_strings: true
  
  # 安全配置
  security:
    hash_algorithm: sha256
    encrypt_algorithm: aes256
  
  # 缓存配置
  cache:
    enabled: true
    max_size: 1000
    ttl: 300
```

---

## 📖 核心接口定义

### ErrorHandler 接口

**位置**：`infra/utils/error_handler.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `handle` | `error: Exception`, `context: dict` | `ErrorEvent` | 处理错误 |
| `log` | `event: ErrorEvent` | `None` | 记录错误 |
| `get_errors` | `filters: dict` | `List[ErrorEvent]` | 获取错误列表 |
| `clear` | 无 | `None` | 清除错误记录 |

### InputValidator 接口

**位置**：`infra/utils/validator.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `validate` | `value: Any`, `rules: List[Rule]` | `ValidationResult` | 验证输入 |
| `validate_schema` | `data: dict`, `schema: dict` | `ValidationResult` | 验证数据模式 |
| `add_rule` | `rule: Rule` | `None` | 添加自定义规则 |

### SecurityUtils 接口

**位置**：`infra/utils/security.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `hash` | `data: str` | `str` | 哈希计算 |
| `encrypt` | `data: str`, `key: str` | `str` | 加密 |
| `decrypt` | `data: str`, `key: str` | `str` | 解密 |
| `generate_token` | `length: int` | `str` | 生成令牌 |
| `verify_signature` | `data: str`, `signature: str` | `bool` | 验证签名 |

---

## 🏭 工厂函数

### get_error_handler

**位置**：`infra/utils/factory.py`

**函数签名**：

```python
def get_error_handler(
    config: Optional[ErrorConfig] = None
) -> ErrorHandler:
    """
    获取错误处理器

    参数：
        config: 错误处理配置（可选）

    返回：
        ErrorHandler 实例
    """
```

### get_validator

**函数签名**：

```python
def get_validator(
    config: Optional[ValidationConfig] = None
) -> InputValidator:
    """
    获取输入验证器

    参数：
        config: 验证配置（可选）

    返回：
        InputValidator 实例
    """
```

**使用示例**：

```python
from infra.utils import get_error_handler, get_validator

# 错误处理
handler = get_error_handler()
try:
    result = process_data()
except Exception as e:
    event = handler.handle(e, {"operation": "process_data", "user": "alice"})
    print(f"Error ID: {event.error_id}")

# 输入验证
validator = get_validator()
result = validator.validate("user@example.com", [EmailRule()])
if result.is_valid:
    print("Valid email")
else:
    print(result.errors)
```

---

## 📊 数据模型

### ErrorEvent

```python
@dataclass
class ErrorEvent:
    error_id: str
    category: ErrorCategory
    level: ErrorLevel
    message: str
    exception: Optional[Exception]
    context: Dict[str, Any]
    timestamp: datetime
    trace_id: Optional[str] = None

class ErrorCategory(Enum):
    VALIDATION = "validation"
    NETWORK = "network"
    DATABASE = "database"
    LLM_API = "llm_api"
    PARSING = "parsing"
    SYSTEM = "system"
    BUSINESS = "business"

class ErrorLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str] = field(default_factory=list)

@dataclass
class ValidationError:
    field: str
    message: str
    code: str
```

### SecurityConfig

```python
@dataclass
class SecurityConfig:
    hash_algorithm: str = "sha256"
    encrypt_algorithm: str = "aes256"
    secret_key: Optional[str] = None
    salt: Optional[str] = None
```

---

## 🚀 使用示例

### 错误处理

```python
from infra.utils import get_error_handler, ErrorCategory, ErrorLevel

handler = get_error_handler()

# 处理错误
try:
    result = await db.query("SELECT * FROM users")
except Exception as e:
    event = handler.handle(
        e,
        context={
            "operation": "db_query",
            "query": "SELECT * FROM users",
            "user": "alice"
        }
    )
    print(f"Error handled: {event.error_id}")
    print(f"Category: {event.category}")
    print(f"Level: {event.level}")

# 获取错误列表
errors = handler.get_errors(
    filters={"level": ErrorLevel.HIGH}
)
for error in errors:
    print(f"{error.timestamp}: {error.message}")
```

### 输入验证

```python
from infra.utils import get_validator, Rule, ValidationError

validator = get_validator()

# 邮箱验证
result = validator.validate("user@example.com", [EmailRule()])
print(result.is_valid)  # True

# 复合验证
result = validator.validate(data, [
    RequiredRule("email"),
    EmailRule("email"),
    LengthRule("password", min=8, max=32),
    RegexRule("phone", r"^\d{10,11}$")
])

if not result.is_valid:
    for error in result.errors:
        print(f"{error.field}: {error.message}")

# 自定义验证规则
@Rule
def PasswordStrengthRule:
    def validate(self, value: str) -> bool:
        return (
            any(c.isupper() for c in value) and
            any(c.islower() for c in value) and
            any(c.isdigit() for c in value)
        )
    
    def message(self, field: str) -> str:
        return f"{field} must contain uppercase, lowercase and digits"
```

### 安全工具

```python
from infra.utils import get_security_utils

security = get_security_utils()

# 哈希
hashed = security.hash("password123")
print(hashed)  # sha256 hash

# 加密
encrypted = security.encrypt("sensitive data", key="my-secret-key")
print(encrypted)

# 解密
decrypted = security.decrypt(encrypted, key="my-secret-key")
print(decrypted)  # "sensitive data"

# 生成令牌
token = security.generate_token(length=32)
print(token)

# 验证签名
signature = security.sign("data", key="my-secret-key")
is_valid = security.verify("data", signature, key="my-secret-key")
```

### 异步工具

```python
from infra.utils import async_retry, async_timeout, run_in_executor

# 重试装饰器
@async_retry(max_attempts=3, backoff=2.0)
async def call_api():
    return await http.get("https://api.example.com")

# 超时装饰器
@async_timeout(timeout=5.0)
async def long_operation():
    await asyncio.sleep(10)

# 并发控制
async def limited_concurrent(tasks, max_concurrent=5):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def bounded_task(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*[bounded_task(t) for t in tasks])
```

---

## 🔧 扩展指南

### 添加新的验证规则

```python
from infra.utils.validator import Rule, ValidationResult

class CustomRule(Rule):
    """自定义验证规则"""
    
    def __init__(self, param=None):
        self.param = param
    
    def validate(self, value: Any) -> bool:
        # 验证逻辑
        return value is not None and value != ""
    
    def message(self, field: str) -> str:
        return f"{field} is required"

# 注册规则
validator = get_validator()
validator.add_rule(CustomRule())
```

### 添加新的错误分类

```python
from infra.utils.error_handler import ErrorCategory

# 扩展错误分类
class CustomErrorCategory(ErrorCategory):
    AI_API = "ai_api"
    RATE_LIMIT = "rate_limit"

# 使用
handler = get_error_handler()
handler.handle(error, category=CustomErrorCategory.RATE_LIMIT)
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `utils.error.default_level` | low/medium/high/critical | invalid level |
| `utils.security.hash_algorithm` | sha256/sha512/md5 | invalid algorithm |
| `utils.cache.max_size` | > 0 | must be > 0 |

---

## 📁 文件结构

```
infra/utils/
├── __init__.py                 # 模块导出
├── base.py                     # 核心接口
├── factory.py                  # 工厂函数
├── schemas.py                  # 数据模型
├── error_handler.py           # 错误处理
├── validator.py                # 输入验证
├── security.py                 # 安全工具
├── async_utils.py             # 异步工具
└── helpers.py                 # 通用辅助
```

---

*最后更新: 2026-04-11*