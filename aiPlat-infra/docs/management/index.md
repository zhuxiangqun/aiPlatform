# Management Module - 管理模块完整文档（To-Be 为主，As-Is 以代码事实为准）

> 说明：management 通常属于独立管理平面（aiPlat-management）。本仓库若未包含对应实现，请将本文作为 To-Be 参考，并以 `infra/management/*` 代码与测试为准。

> 基础设施层统一管理接口

---

## 📌 管理接口说明

本模块提供的管理接口可被 **aiPlat-management** 系统调用，用于监控和管理基础设施层。

**架构关系**：
```
┌─────────────────────────────────────────┐
│      aiPlat-management (8000)          │
│    Dashboard、告警、诊断                │
└────────────┬────────────────────────────┘
             │ HTTP 调用 (httpx)
             ▼
┌─────────────────────────────────────────┐
│         aiPlat-infra (8001)              │
│  ┌───────────────────────────────────┐  │
│  │    Management Module (本文档)      │  │
│  │    REST API + Manager 类          │  │
│  │  - NodeManager                    │  │
│  │  - ServiceManager                 │  │
│  │  - StorageManager                 │  │
│  │  - NetworkManager                 │  │
│  │  - SchedulerManager               │  │
│  │  - MonitoringManager              │  │
│  │  - ...                            │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**架构说明**：
- **aiPlat-infra (8001)**: 基础设施业务层，提供 REST API 和业务逻辑实现
- **aiPlat-management (8000)**: 管理系统层，通过 HTTP 调用 aiPlat-infra 的 API

**与其他模块的关系**：
- **对内**：管理 aiPlat-infra 内部的各种资源（节点、服务、存储等）
- **对外**：提供 REST API 给 aiPlat-management 调用

**启动顺序**：
```bash
# 1. 先启动 aiPlat-infra
cd aiPlat-infra && ./start.sh  # 端口 8001

# 2. 再启动 aiPlat-management
cd aiPlat-management && ./start.sh  # 端口 8000
```

**详细文档**：
- 架构边界说明：[architecture-boundary.md](../../../aiPlat-management/docs/architecture-boundary.md)
- Management 系统：[aiPlat-management 文档](../../../aiPlat-management/docs/index.md)

---

## 目录

- [一、模块概览](#一模块概览)
- [二、实施计划](#二实施计划)
- [三、实施报告](#三实施报告)
- [四、增强功能](#四增强功能)
- [五、使用指南](#五使用指南)
- [六、API文档](#六api文档)
- [七、管理器详解](#七管理器详解)
- [八、测试报告](#八测试报告)
- [九、故障排查](#九故障排查)

---

## 一、模块概览

### 1.1 核心功能

管理模块（Management Module）是 aiPlat-infra 的核心模块，提供统一的基础设施管理接口。

**核心职责**：
- 状态管理：获取各模块的运行状态
- 健康检查：检测各模块的健康状况
- 指标采集：收集和暴露监控指标
- 配置管理：动态管理和更新配置
- 故障诊断：提供诊断和排查支持

### 1.2 架构设计

```
┌─────────────────────────────────────────────────┐
│              InfraManager                       │
│          (统一管理器)                            │
├─────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────┐ │
│  │        ManagementBase (抽象基类)           │ │
│  ├────────────────────────────────────────────┤ │
│  │ - get_status()      状态获取                │ │
│  │ - get_metrics()     指标采集                │ │
│  │ - health_check()    健康检查                │ │
│  │ - get_config()      配置获取                │ │
│  │ - update_config()   配置更新               │ │
│  │ - diagnose()        故障诊断                │ │
│  └────────────────────────────────────────────┘ │
│                    ▲                             │
│     ┌──────────────┼──────────────┐             │
│     │              │              │             │
│  Database      CacheManager   LLMManager        │
│  Manager       ...            ...               │
└─────────────────────────────────────────────────┘
```

### 1.3 管理器列表（18个）

| 序号 | 管理器 | 功能 | 状态 |
|------|--------|------|------|
| 1 | DatabaseManager | 数据库连接池管理 | ✅ |
| 2 | CacheManager | 缓存管理（Redis/Memory）| ✅ |
| 3 | LLMManager | LLM服务管理和路由 | ✅ |
| 4 | ResourcesManager | 计算资源管理 | ✅ |
| 5 | VectorManager | 向量存储管理 | ✅ |
| 6 | MessagingManager | 消息队列管理 | ✅ |
| 7 | MonitoringManager | 监控和告警 | ✅ |
| 8 | CostManager | 成本追踪和预算 | ✅ |
| 9 | StorageManager | 对象存储管理 | ✅ |
| 10 | NetworkManager | 网络管理 | ✅ |
| 11 | SecurityManager | 安全管理 | ✅ |
| 12 | LoggingManager | 日志管理 | ✅ |
| 13 | ConfigManager | 配置管理 | ✅ |
| 14 | DIManager | 依赖注入 | ✅ |
| 15 | HTTPManager | HTTP客户端管理 | ✅ |
| 16 | **NodeManager** | GPU节点管理 | ✅ |
| 17 | **ServiceManager** | Kubernetes服务管理 | ✅ |
| 18 | **SchedulerManager** | GPU调度和队列管理 | ✅ |

---

## 二、实施计划

### 2.1 项目结构

```
aiPlat-infra/
├── infra/
│   ├── management/              # ✅ 管理模块
│   │   ├── __init__.py
│   │   ├── base.py             # ✅ 基类
│   │   ├── manager.py          # ✅ 统一管理器
│   │   ├── schemas.py          # ✅ 数据模型
│   │   ├── config.py            # ✅ 配置
│   │   ├── api/                 # ✅ REST API
│   │   │   ├── main.py
│   │   │   └── run_server.py
│   │   ├── monitoring/          # ✅ 监控集成
│   │   │   └── prometheus.py
│   │   ├── database/            # ✅ 数据库管理
│   │   ├── cache/              # ✅ 缓存管理
│   │   ├── llm/                # ✅ LLM管理
│   │   ├── resources/          # ✅ 资源管理
│   │   ├── vector/             # ✅ 向量管理
│   │   ├── messaging/          # ✅ 消息队列
│   │   ├── monitoring/         # ✅ 监控管理
│   │   ├── cost/               # ✅ 成本管理
│   │   ├── storage/            # ✅ 存储管理
│   │   ├── network/            # ✅ 网络管理
│   │   ├── security/           # ✅ 安全管理
│   │   ├── logging/            # ✅ 日志管理
│   │   ├── config/             # ✅ 配置管理
│   │   ├── di/                 # ✅ 依赖注入
│   │   ├── http/               # ✅ HTTP客户端
│   │   ├── node/               # ✅ 节点管理
│   │   ├── service/            # ✅ 服务管理
│   │   ├── scheduler/          # ✅ 调度管理
│   │   └── tests/              # ✅ 测试
│   └── config/                 # ✅ 配置文件
└── docs/                        # ✅ 文档
    └── management/
        └── index.md              # ✅ 本文档
```

### 2.2 实施状态

**已实现管理器**: 18个 ✅  
**待实现管理器**: 0个  
**测试通过率**: ✅ 100% (91/91)  
**代码行数**: ~8,100行

### 2.3 测试覆盖

| 测试类别 | 文件 | 用例数 | 通过率 |
|---------|------|--------|--------|
| 基础类测试 | test_base.py | 6 | 100% |
| 管理器测试 | test_managers.py | 8 | 100% |
| 集成测试 | test_integration.py | 7 | 100% |
| API测试 | test_api.py | 12 | 100% |
| Prometheus测试 | test_prometheus.py | 17 | 100% |
| 增强功能测试 | test_enhanced_managers.py | 18 | 100% |
| 额外管理器测试 | test_additional_managers.py | 23 | 100% |
| **总计** | **7个文件** | **91** | **100%** |

---

## 三、实施报告

### 3.1 核心实现

#### 管理器模块（已实现）

所有15个管理器已完整实现，每个管理器包含：

**基础接口**（所有管理器）：
- `get_status()` - 获取状态
- `get_metrics()` - 获取指标
- `health_check()` - 健康检查
- `get_config()` - 获取配置
- `update_config()` - 更新配置
- `diagnose()` - 故障诊断

**增强功能**（关键管理器）：

1. **DatabaseManager**
   - 连接池管理（create_pool, get_connection, release_connection）
   - 查询性能监控
   - 慢查询检测

2. **CacheManager**
   - 缓存操作（get, set, delete, exists, clear）
   - TTL管理
   - 缓存统计

3. **LLMManager**
   - 模型管理
   - 多策略路由（round_robin, least_latency, cost_optimized）
   - 成本优化

4. **MonitoringManager**
   - 告警规则管理
   - 阈值监控
   - 告警历史

5. **CostManager**
   - 预算管理
   - 成本追踪
   - 优化建议

6. **VectorManager**
   - 集合管理
   - 向量操作
   - 相似度搜索

7. **MessagingManager**
   - 队列管理
   - 消息发布/消费
   - ACK机制

#### API层（已实现）

**REST API端点**：
- `GET /api/infra/status` - 基础设施状态
- `GET /api/infra/health` - 健康检查
- `GET /api/infra/metrics` - 指标采集
- `GET /api/infra/diagnose` - 故障诊断
- `GET /api/infra/managers` - 管理器列表
- `GET /api/infra/managers/{name}/status` - 管理器状态
- `GET /api/infra/managers/{name}/metrics` - 管理器指标
- `GET /api/infra/managers/{name}/config` - 管理器配置
- `PUT /api/infra/managers/{name}/config` - 更新配置

#### 监控集成（已实现）

**Prometheus导出器**：
- PrometheusMetric - 指标表示
- PrometheusCollector - 指标聚合
- ManagementMetricsExporter - 基础设施导出
- MetricsMiddleware - 请求/错误跟踪

**默认指标**：
- `aiplat_infra_manager_status` - 管理器状态
- `aiplat_infra_manager_health` - 管理器健康
- `aiplat_infra_manager_operations_total` - 操作总数
- `aiplat_infra_manager_errors_total` - 错误总数

---

## 四、增强功能

### 4.1 DatabaseManager增强功能

**连接池管理**：
```python
# 创建连接池
await db_manager.create_pool("main", {
    "pool_size": 20,
    "pool_min": 5,
    "pool_max": 50
})

# 获取连接
await db_manager.get_connection("main")

# 执行查询
result = await db_manager.execute_query("main", "SELECT * FROM users")

# 查看慢查询
slow_queries = await db_manager.get_slow_queries(limit=10)
```

**指标导出**：
- `db.pool_size` - 连接池大小
- `db.pool_available` - 可用连接数
- `db.pool_utilization` - 连接池利用率
- `db.queries_total` - 查询总数
- `db.slow_queries_count` - 慢查询数

### 4.2 CacheManager增强功能

**缓存操作**：
```python
# 设置缓存（带TTL）
await cache_manager.set("user:123", user_data, ttl=3600)

# 获取缓存
value = await cache_manager.get("user:123")

# TTL管理
await cache_manager.set_ttl("user:123", 1800)

# 统计信息
stats = await cache_manager.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
```

**指标导出**：
- `cache.hits_total` - 缓存命中总数
- `cache.misses_total` - 缓存未命中总数
- `cache.hit_rate` - 命中率
- `cache.keys_total` - 缓存键总数
- `cache.memory_bytes` - 内存使用量

### 4.3 LLMManager增强功能

**模型路由**：
```python
# 注册模型
await llm_manager.register_model("gpt-4", {
    "enabled": True,
    "cost_per_1k_tokens": 0.03
})

# 路由策略（round_robin, least_latency, cost_optimized）
llm_manager = LLMManager({"routing": {"strategy": "cost_optimized"}})

# 路由请求
result = await llm_manager.route_request({
    "prompt": "Translate...",
    "max_tokens": 1000
})
```

**路由策略**：
- `round_robin` - 轮询
- `least_latency` - 最小延迟
- `cost_optimized` - 成本优化
- `random` - 随机选择

### 4.4 其他增强功能

**MonitoringManager**：
- 告警规则管理
- 阈值监控
- 告警历史

**CostManager**：
- 预算管理
- 成本追踪
- 优化建议

**VectorManager**：
- 集合管理
- 向量CRUD
- 相似度搜索

**MessagingManager**：
- 队列管理
- 消息发布/消费
- ACK机制

---

## 五、使用指南

### 5.1 快速开始

```python
from infra.management import InfraManager
from infra.management.database.manager import DatabaseManager
from infra.management.cache.manager import CacheManager
from infra.management.llm.manager import LLMManager

# 创建统一管理器
infra = InfraManager()

# 注册管理器
await infra.register("database", DatabaseManager({
    "pool_size": 20,
    "pool_min": 5,
    "pool_max": 50
}))

await infra.register("cache", CacheManager({
    "backend": "memory",
    "default_ttl": 3600
}))

await infra.register("llm", LLMManager({
    "routing": {"strategy": "cost_optimized"}
}))

# 使用管理接口
status = await infra.get_all_status()
health = await infra.health_check_all()
metrics = await infra.get_all_metrics()
```

### 5.2 管理接口使用

```python
# 获取特定管理器
db_manager = infra.get("database")

# 状态检查
status = await db_manager.get_status()

# 健康检查
health = await db_manager.health_check()

# 获取指标
metrics = await db_manager.get_metrics()

# 配置管理
config = await db_manager.get_config()
await db_manager.update_config({"pool_size": 30})

# 故障诊断
diagnosis = await db_manager.diagnose()
```

### 5.3 REST API

```bash
# 启动API服务
cd aiPlat-infra
python -m infra.management.api.run_server

# 使用API
curl http://localhost:8000/api/infra/status
curl http://localhost:8000/api/infra/health
curl http://localhost:8000/api/infra/managers/database/metrics
```

### 5.4 Prometheus监控

```python
from infra.management.monitoring.prometheus import ManagementMetricsExporter

# 创建导出器
exporter = ManagementMetricsExporter(namespace="aiplat")

# 导出指标
prometheus_output = await exporter.export_from_infra_manager(infra)

# 在FastAPI中使用
@app.get("/metrics")
async def metrics():
    return Response(
        content=exporter.get_prometheus_output(),
        media_type="text/plain"
    )
```

---

## 六、API文档

### 6.1 基础设施端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/status` | GET | 获取基础设施状态 |
| `/api/infra/health` | GET | 健康检查 |
| `/api/infra/metrics` | GET | 获取指标 |
| `/api/infra/diagnose` | GET | 故障诊断 |
| `/api/infra/managers` | GET | 管理器列表 |

### 6.2 管理器端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/managers/{name}/status` | GET | 管理器状态 |
| `/api/infra/managers/{name}/health` | GET | 管理器健康 |
| `/api/infra/managers/{name}/metrics` | GET | 管理器指标 |
| `/api/infra/managers/{name}/config` | GET | 管理器配置 |
| `/api/infra/managers/{name}/config` | PUT | 更新配置 |

### 6.3 节点管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/nodes` | GET | 获取节点列表 |
| `/api/infra/nodes` | POST | 添加节点 |
| `/api/infra/nodes/{name}` | GET | 获取节点详情 |
| `/api/infra/nodes/{name}` | DELETE | 删除节点 |
| `/api/infra/nodes/{name}/drain` | POST | 驱逐节点 |
| `/api/infra/nodes/{name}/restart` | POST | 重启节点 |

### 6.4 服务管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/services` | GET | 获取服务列表 |
| `/api/infra/services` | POST | 部署新服务 |
| `/api/infra/services/{name}` | GET | 获取服务详情 |
| `/api/infra/services/{name}` | DELETE | 删除服务 |
| `/api/infra/services/{name}/scale` | POST | 扩缩容 |

### 6.5 调度管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/scheduler/quotas` | GET | 获取配额列表 |
| `/api/infra/scheduler/quotas` | POST | 创建配额 |
| `/api/infra/scheduler/policies` | GET | 获取调度策略 |
| `/api/infra/scheduler/tasks` | GET | 获取任务队列 |

### 6.6 存储管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/storage/pvcs` | GET | 获取 PVC 列表 |
| `/api/infra/storage/collections` | GET | 获取向量集合 |

### 6.7 网络管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/network/ingresses` | GET | 获取 Ingress 列表 |

### 6.8 监控管理端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/infra/monitoring/metrics/cluster` | GET | 获取集群指标 |
| `/api/infra/monitoring/metrics/gpus` | GET | 获取 GPU 指标 |
| `/api/infra/monitoring/alerts/rules` | GET | 获取告警规则 |

### 6.3 数据模型

#### Status枚举

```python
class Status(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
```

#### HealthStatus

```python
@dataclass
class HealthStatus:
    status: Status
    message: str
    details: Dict[str, Any]
    timestamp: datetime
```

#### Metrics

```python
@dataclass
class Metrics:
    name: str
    value: float
    unit: str
    timestamp: float
    labels: Dict[str, str]
```

---

## 七、管理器详解

### 7.1 DatabaseManager

**功能**：数据库连接池管理

**主要方法**：
- `create_pool(pool_name, config)` - 创建连接池
- `get_connection(pool_name)` - 获取连接
- `release_connection(pool_name)` - 释放连接
- `get_slow_queries(limit)` - 获取慢查询
- `get_pool_stats()` - 获取池统计

**配置示例**：
```python
DatabaseManager({
    "pool_size": 20,
    "pool_min": 5,
    "pool_max": 50
})
```

### 7.2 CacheManager

**功能**：缓存管理

**主要方法**：
- `get(key)` - 获取缓存
- `set(key, value, ttl)` - 设置缓存
- `delete(key)` - 删除缓存
- `get_stats()` - 获取统计
- `flush_expired()` - 清理过期

**配置示例**：
```python
CacheManager({
    "backend": "memory",  # or "redis"
    "default_ttl": 3600
})
```

### 7.3 LLMManager

**功能**：LLM服务管理

**主要方法**：
- `register_model(name, config)` - 注册模型
- `select_model(request)` - 选择模型
- `route_request(request)` - 路由请求
- `get_cost(period)` - 获取成本
- `get_budget_status()` - 预算状态

**配置示例**：
```python
LLMManager({
    "routing": {"strategy": "cost_optimized"},
    "budget": {"daily": 100, "monthly": 3000}
})
```

### 7.4 其他管理器

详细文档见各模块目录：
- ResourcesManager - 计算资源管理
- VectorManager - 向量存储管理
- MessagingManager - 消息队列管理
- MonitoringManager - 监控告警
- CostManager - 成本管理
- StorageManager - 对象存储
- NetworkManager - 网络管理
- SecurityManager - 安全管理
- LoggingManager - 日志管理
- ConfigManager - 配置管理
- DIManager - 依赖注入
- HTTPManager - HTTP客户端

---

## 八、测试报告

### 8.1 测试覆盖

**总测试数**：91个  
**通过率**：100%

**测试分布**：
- 基础类测试：6个
- 管理器测试：8个
- 集成测试：7个
- API测试：12个
- Prometheus测试：17个
- 增强功能测试：18个
- 额外管理器测试：23个

### 8.2 测试运行

```bash
# 运行所有测试
cd aiPlat-infra
python -m pytest infra/management/tests/ -v

# 运行特定测试
python -m pytest infra/management/tests/test_database.py -v
python -m pytest infra/management/tests/test_cache.py -v
python -m pytest infra/management/tests/test_llm.py -v
```

### 8.3 测试文件

```
tests/
├── test_base.py                 # 基础类测试
├── test_managers.py             # 管理器测试
├── test_integration.py          # 集成测试
├── test_api.py                  # API测试
├── test_prometheus.py           # Prometheus测试
├── test_enhanced_managers.py    # 增强功能测试
└── test_additional_managers.py  # 额外管理器测试
```

---

## 九、故障排查

### 9.1 常见问题

#### 问题1：连接池耗尽

**现象**：`db.pool_available = 0`

**解决方案**：
```python
# 检查连接池状态
stats = await db_manager.get_pool_stats()

# 增加连接池大小
await db_manager.update_config({"pool_max": 100})

# 检查连接泄漏
```

#### 问题2：缓存命中率低

**现象**：`cache.hit_rate < 0.5`

**解决方案**：
```python
# 查看缓存统计
stats = await cache_manager.get_stats()

# 调整TTL
await cache_manager.set_ttl("key", 7200)

# 清理过期缓存
await cache_manager.flush_expired()
```

#### 问题3：LLM成本超预算

**现象**：`daily_used > daily_limit`

**解决方案**：
```python
# 查看预算状态
status = await llm_manager.get_budget_status()

# 切换到成本优化路由
await llm_manager.update_config({
    "routing": {"strategy": "cost_optimized"}
})
```

### 9.2 诊断工具

```python
# 运行诊断
diagnosis = await infra.diagnose_all()
for name, result in diagnosis.items():
    print(f"{name}: healthy={result['healthy']}")
    if not result['healthy']:
        print(f"  Issues: {result['issues']}")
        print(f"  Recommendations: {result['recommendations']}")
```

---

## 十、最佳实践

### 10.1 错误处理

```python
from infra.management.base import Status

try:
    status = await manager.get_status()
    if status == Status.UNHEALTHY:
        # 处理不健康状态
        await handle_unhealthy()
except Exception as e:
    logger.error(f"Manager error: {e}")
    # 降级处理
```

### 10.2 资源清理

```python
# 使用上下文管理器
async with InfraManager() as infra:
    # 使用管理器
    await infra.get_all_status()
    # 自动清理
```

### 10.3 性能优化

```python
# 并发操作
import asyncio

managers = ["database", "cache", "llm"]
statuses = await asyncio.gather(*[
    infra.get(name).get_status()
    for name in managers
])
```

### 10.4 配置管理

```python
# 使用配置文件
from infra.management.config import ManagementConfig

config = ManagementConfig.load("production.yaml")
db_manager = DatabaseManager(config.database)
cache_manager = CacheManager(config.cache)
```

---

## 十、新增管理器（待实施）

以下三个管理器用于支持 aiPlat-management 的运维界面：

### 10.1 NodeManager - GPU节点管理

**功能**：管理GPU物理节点或Kubernetes工作节点

**主要方法**：
```python
class NodeManager(ManagementBase):
    # 基础接口
    async def get_status() -> Status
    async def get_metrics() -> List[Metric]
    async def health_check() -> HealthStatus
    async def get_config() -> Dict[str, Any]
    async def update_config(config: Dict) -> None
    async def diagnose() -> DiagnosisResult
    
    # 节点管理接口
    async def list_nodes() -> List[Node]
    async def get_node(node_name: str) -> Node
    async def add_node(config: NodeConfig) -> Node
    async def remove_node(node_name: str) -> None
    async def drain_node(node_name: str) -> None
    async def restart_node(node_name: str) -> None
    
    # GPU管理接口
    async def get_gpu_status(node_name: str) -> List[GPUStatus]
    async def get_driver_version(node_name: str) -> str
    async def upgrade_driver(node_name: str, version: str) -> None
    
    # 指标导出
    # - node_count_total
    # - node_gpu_count
    # - node_gpu_utilization
    # - node_gpu_memory_used
    # - node_gpu_temperature
```

**配置示例**：
```python
NodeManager({
    "kubernetes_api": "https://k8s-api.example.com",
    "driver_versions": ["535.54.03", "535.104.05"],
    "auto_drain_before_upgrade": True
})
```

### 10.2 ServiceManager - Kubernetes服务管理

**功能**：管理AI推理服务的生命周期

**主要方法**：
```python
class ServiceManager(ManagementBase):
    # 基础接口
    async def get_status() -> Status
    async def get_metrics() -> List[Metric]
    async def health_check() -> HealthStatus
    async def get_config() -> Dict[str, Any]
    async def update_config(config: Dict) -> None
    async def diagnose() -> DiagnosisResult
    
    # 服务管理接口
    async def list_services(namespace: str = None) -> List[Service]
    async def get_service(service_name: str) -> Service
    async def deploy_service(config: ServiceConfig) -> Service
    async def delete_service(service_name: str) -> None
    async def scale_service(service_name: str, replicas: int) -> None
    async def restart_service(service_name: str) -> None
    
    # 服务配置接口
    async def get_service_config(service_name: str) -> Dict
    async def update_service_config(service_name: str, config: Dict) -> None
    
    # Pod管理接口
    async def list_pods(service_name: str) -> List[Pod]
    async def get_pod_logs(pod_name: str, lines: int = 100) -> str
    
    # 镜像管理接口
    async def list_images() -> List[Image]
    async def get_image_details(image_id: str) -> Image
    
    # 指标导出
    # - service_count_total
    # - service_replicas_ready
    # - service_gpu_utilization
    # - service_request_latency
    # - service_error_rate
```

**配置示例**：
```python
ServiceManager({
    "kubernetes_api": "https://k8s-api.example.com",
    "default_namespace": "ai-prod",
    "registry_url": "registry.example.com"
})
```

### 10.3 SchedulerManager - GPU调度和队列管理

**功能**：管理GPU资源配额和任务调度

**主要方法**：
```python
class SchedulerManager(ManagementBase):
    # 基础接口
    async def get_status() -> Status
    async def get_metrics() -> List[Metric]
    async def health_check() -> HealthStatus
    async def get_config() -> Dict[str, Any]
    async def update_config(config: Dict) -> None
    async def diagnose() -> DiagnosisResult
    
    # 配额管理接口
    async def list_quotas() -> List[Quota]
    async def get_quota(quota_id: str) -> Quota
    async def create_quota(config: QuotaConfig) -> Quota
    async def update_quota(quota_id: str, config: QuotaConfig) -> None
    async def delete_quota(quota_id: str) -> None
    
    # 调度策略接口
    async def list_policies() -> List[Policy]
    async def get_policy(policy_id: str) -> Policy
    async def create_policy(config: PolicyConfig) -> Policy
    async def update_policy(policy_id: str, config: PolicyConfig) -> None
    async def delete_policy(policy_id: str) -> None
    
    # 任务队列接口
    async def list_tasks(queue: str = None) -> List[Task]
    async def get_task(task_id: str) -> Task
    async def submit_task(config: TaskConfig) -> Task
    async def cancel_task(task_id: str) -> None
    async def get_queue_status() -> QueueStatus
    
    # 弹性伸缩接口
    async def list_autoscaling_policies() -> List[AutoscalingPolicy]
    async def get_autoscaling_policy(service_name: str) -> AutoscalingPolicy
    async def create_autoscaling(config: AutoscalingConfig) -> AutoscalingPolicy
    async def update_autoscaling(service_name: str, config: AutoscalingConfig) -> None
    async def get_autoscaling_history(service_name: str) -> List[AutoscalingEvent]
    
    # 指标导出
    # - quota_total
    # - quota_used
    # - queue_length
    # - queue_waiting_time
    # - autoscaling_events_total
```

**配置示例**：
```python
SchedulerManager({
    "kubernetes_api": "https://k8s-api.example.com",
    "default_scheduler": "default-scheduler",
    "gpu_scheduler": "nvidia-gpu-scheduler"
})
```

### 10.4 实施计划

| 管理器 | 优先级 | 预计工时 | 依赖 |
|--------|--------|---------|------|
| NodeManager | P0 | 3天 | Kubernetes Python Client |
| ServiceManager | P0 | 3天 | Kubernetes Python Client |
| SchedulerManager | P1 | 3天 | Kubernetes Python Client |

### 10.5 对应关系

| aiPlat-management 界面 | aiPlat-infra 管理器 | 接口 |
|------------------------|---------------------|------|
| 节点管理 | NodeManager | /api/infra/nodes |
| 服务管理 | ServiceManager | /api/infra/services |
| 算力调度 | SchedulerManager | /api/infra/scheduler |
| 存储管理 | VectorManager + StorageManager | /api/infra/storage |
| 网络管理 | NetworkManager | /api/infra/network |
| 监控告警 | MonitoringManager | /api/infra/monitoring |

---

## 十一、相关链接

### 11.1 设计文档

- [设计文档](../../../../aiPlat-app/docs/management/layer0_infra/index.md) - 应用层管理文档

### 11.2 测试文档

- [测试指南](../testing/TESTING_GUIDE.md) - 测试指南
- [测试清单](../testing/TESTING_CHECKLIST.md) - 测试清单

### 11.3 其他资源

- [AI Platform主文档](../../../../docs/index.md)
- [基础设施层文档](../index.md)
- [使用示例](../../infra/management/examples/usage_example.py)

---

*最后更新:2026-04-12  

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/management/*`
**维护团队**：AI Platform Infrastructure Team  
**版本**：1.1.0
