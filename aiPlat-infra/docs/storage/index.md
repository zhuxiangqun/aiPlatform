# 存储模块（设计真值：以代码事实为准）

> 说明：存储模块的 As-Is 能力以 `infra/storage/*` 代码与测试为准；对象存储/MinIO/S3 等若未实现需标注为 To-Be。

> 提供持久化存储能力，包括本地存储、网络存储、对象存储

---

## 🎯 模块定位

存储模块负责统一管理所有**持久化**数据存储，支持：
- 文件存储（本地磁盘）
- 对象存储（S3、GCS、Azure Blob）
- 临时文件存储
- 存储策略配置

> **注意**：本模块专注于**持久化存储**，不包含临时缓存能力。
> 临时缓存能力请使用独立的 `cache/` 模块。

### 模块边界说明

| 模块 | 职责 | 数据特征 | 示例 |
|------|------|----------|------|
| **storage** | 持久化存储 | 长期保存、不会自动过期 | 用户上传的文件、业务数据、备份 |
| **cache** | 临时缓存 | 短期保存、TTL过期 | 会话数据、查询缓存、热点数据 |

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
storage:
  # 文件存储配置
  file:
    base_path: /var/data/ai-platform
    max_file_size: 100MB
    allowed_extensions:
      - pdf
      - txt
      - json
      - csv
      - png
      - jpg
  
  # 对象存储配置（S3/GCS/Azure）
  object:
    type: s3                      # s3, gcs, azure
    bucket: ai-platform-bucket
    region: us-east-1
    access_key: ${AWS_ACCESS_KEY}
    secret_key: ${AWS_SECRET_KEY}
    endpoint: ${S3_ENDPOINT}       # 自定义S3兼容存储使用
  
  # 临时存储
  temp:
    path: /tmp/ai-platform
    max_size: 1GB
    cleanup_interval: 3600
```

---

## 📖 核心接口定义

### StorageClient 接口

**位置**：`infra/storage/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `save` | `key: str`, `data: Any` | `str` | 保存数据 |
| `load` | `key: str` | `Optional[Any]` | 加载数据 |
| `delete` | `key: str` | `bool` | 删除数据 |
| `exists` | `key: str` | `bool` | 检查是否存在 |
| `list` | `prefix: str` | `List[str]` | 列出键 |
| `clear` | 无 | `None` | 清空存储 |

### FileStorage 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `save_file` | `path: str`, `content: bytes` | `str` | 保存文件 |
| `read_file` | `path: str` | `bytes` | 读取文件 |
| `delete_file` | `path: str` | `bool` | 删除文件 |
| `list_files` | `dir: str` | `List[str]` | 列出文件 |
| `get_size` | `path: str` | `int` | 获取文件大小 |
| `get_url` | `path: str` | `str` | 获取访问 URL |

### ObjectStorage 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `upload` | `key: str`, `data: bytes`, `content_type: str` | `str` | 上传对象 |
| `download` | `key: str` | `bytes` | 下载对象 |
| `delete` | `key: str` | `bool` | 删除对象 |
| `list_objects` | `prefix: str` | `List[str]` | 列出对象 |
| `get_presigned_url` | `key: str`, `expires: int` | `str` | 获取预签名URL |

---

## 🏭 工厂函数

### create_storage_client

**位置**：`infra/storage/factory.py`

**函数签名**：

```python
def create_storage_client(
    config: StorageConfig
) -> StorageClient:
    """
    创建存储客户端

    参数：
        config: 存储配置

    返回：
        StorageClient 实例
    """
```

**使用示例**：

```python
from infra.storage import create_storage_client

# 文件存储
storage = create_storage_client(StorageConfig(
    type="file",
    base_path="/var/data/ai-platform"
))

await storage.save_file("documents/user1/report.pdf", file_content)
content = await storage.read_file("documents/user1/report.pdf")

# 对象存储（S3）
object_storage = create_storage_client(StorageConfig(
    type="s3",
    bucket="ai-platform-bucket",
    region="us-east-1"
))

await object_storage.upload("uploads/doc.pdf", file_content, "application/pdf")
url = object_storage.get_presigned_url("uploads/doc.pdf", expires=3600)
```

> **注意**：如需使用 Redis/内存缓存，请使用独立的 `cache/` 模块。

---

## 📊 数据模型

### StorageConfig

```python
@dataclass
class StorageConfig:
    type: str = "file"              # file, s3, gcs, azure
    base_path: str = "/var/data"
    max_file_size: str = "100MB"
    allowed_extensions: List[str] = field(default_factory=list)
    key_prefix: str = ""
```

### ObjectConfig

```python
@dataclass
class ObjectConfig:
    type: str = "s3"                # s3, gcs, azure
    bucket: str = ""
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = ""
    endpoint: Optional[str] = None
```

### FileConfig

```python
@dataclass
class FileConfig:
    path: str
    size: int
    content_type: str
    created_at: datetime
    modified_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 🚀 使用示例

### 文件存储

```python
from infra.storage import create_storage_client

storage = create_storage_client(StorageConfig(
    type="file",
    base_path="/var/data/ai-platform"
))

# 保存文件
await storage.save_file(
    "reports/2024/q1/report.pdf",
    b"PDF content here"
)

# 读取文件
content = await storage.read_file("reports/2024/q1/report.pdf")

# 删除文件
await storage.delete_file("reports/2024/q1/report.pdf")

# 列出文件
files = await storage.list_files("reports/2024/")

# 获取文件信息
info = await storage.get_file_info("reports/2024/q1/report.pdf")
print(f"Size: {info.size}, Type: {info.content_type}")
```

### 对象存储（S3）

```python
from infra.storage import create_storage_client

object_storage = create_storage_client(StorageConfig(
    type="s3",
    bucket="ai-platform-bucket",
    region="us-east-1",
    access_key="AKIAIOSFODNN7EXAMPLE",
    secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
))

# 上传对象
await object_storage.upload(
    "documents/2024/report.pdf",
    file_content,
    content_type="application/pdf"
)

# 下载对象
content = await object_storage.download("documents/2024/report.pdf")

# 删除对象
await object_storage.delete("documents/2024/report.pdf")

# 列出对象
objects = await object_storage.list_objects("documents/")

# 获取预签名URL（临时访问）
url = object_storage.get_presigned_url(
    "documents/2024/report.pdf",
    expires=3600  # 1小时
)
print(f"Download URL: {url}")
```

### 临时文件存储

```python
# 临时文件处理
temp_storage = create_storage_client(StorageConfig(
    type="temp",
    path="/tmp/ai-platform"
))

# 保存临时文件
temp_path = await temp_storage.save_file(
    "tmp/upload_abc123.tmp",
    large_file_content
)

# 处理完成后自动清理
await temp_storage.delete_file(temp_path)
```

### 缓存操作

```python
from infra.storage import create_cache_client

cache = create_cache_client(CacheConfig(
    type="redis",
    host="localhost",
    port=6379,
    default_ttl=3600
))

# 基本操作
await cache.set("user:1", {"name": "Alice"}, ttl=1800)
user = await cache.get("user:1")

# 检查存在
if await cache.exists("user:1"):
    print("User exists")

# 批量操作
await cache.set_many({
    "user:2": {"name": "Bob"},
    "user:3": {"name": "Charlie"}
}, ttl=3600)

# 删除
await cache.delete("user:1")

# 模式匹配
keys = await cache.keys("user:*")
print(f"Found {len(keys)} user keys")

# 清空
await cache.clear()
```

### 缓存策略

```python
from infra.storage import CacheStrategy

# LRU 策略
cache = create_cache_client(CacheConfig(
    type="redis",
    strategy="lru"
))

# TTL 策略
cache = create_cache_client(CacheConfig(
    type="redis",
    default_ttl=3600,
    ttl_strategy="fixed"  # fixed, sliding, lazy
))

# 过期回调
def on_expire(key: str, value: Any):
    logger.info(f"Cache expired: {key}")

cache = create_cache_client(CacheConfig(
    type="redis",
    on_expire=on_expire
))
```

---

## 🔧 扩展指南

### 添加新的存储后端

**文件**：`infra/storage/s3.py`

```python
from infra.storage.base import StorageClient
import boto3

class S3StorageClient(StorageClient):
    """S3 存储客户端"""
    
    def __init__(self, config: StorageConfig):
        self.client = boto3.client('s3',
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region
        )
        self.bucket = config.bucket
    
    async def save(self, key: str, data: Any) -> str:
        await self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data
        )
        return key
    
    async def load(self, key: str) -> Optional[Any]:
        response = await self.client.get_object(
            Bucket=self.bucket,
            Key=key
        )
        return response['Body'].read()
    
    async def delete(self, key: str) -> bool:
        await self.client.delete_object(Bucket=self.bucket, Key=key)
        return True
```

### 注册到工厂

```python
def create_storage_client(config: StorageConfig) -> StorageClient:
    if config.type == "file":
        return FileStorageClient(config)
    elif config.type == "s3":
        return S3StorageClient(config)
    elif config.type == "gcs":
        return GCSStorageClient(config)
    else:
        raise ValueError(f"Unknown storage type: {config.type}")
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `storage.cache.type` | memory/redis | invalid type |
| `storage.cache.port` | 1-65535 | must be 1-65535 |
| `storage.cache.db` | 0-15 | must be 0-15 |
| `storage.file.max_file_size` | 正整数+单位 | invalid size format |

---

## 📁 文件结构

```
infra/storage/
├── __init__.py               # 模块导出
├── base.py                   # 存储接口
├── factory.py                # 工厂函数
├── schemas.py                # 数据模型
└── clients.py               # 存储客户端实现（Local/S3/GCS/Azure）
```

---

*最后更新: 2026-04-11*

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/storage/*`
