# 📚 Network 模块文档（设计真值：以代码事实为准）

> 说明：网络相关能力以 `infra/network/*` 代码与测试为准；更高层的网关/ServiceMesh 等通常属于 To-Be 或外部基础设施。

> 网络资源管理 - 基础设施层

---

## 🎯 模块定位

**职责**：管理和抽象网络资源，包括服务发现、负载均衡、网络策略、流量控制等。

**依赖方向**：
```
network 模块 → 被 core/platform/app 调用（通过 infra 工厂接口）
network 模块 → 不依赖任何内部模块
```

---

## 🏗️ 能力概述

### 支持的网络能力

| 能力 | 说明 |
|------|------|
| **服务发现** | 服务注册、健康检查、DNS 解析 |
| **负载均衡** | 轮询、加权轮询、最少连接、一致性哈希 |
| **网络策略** | 访问控制、隔离策略、网络分段 |
| **流量控制** | 限流、熔断、流量切换 |
| **DNS 管理** | 域名解析、动态更新 |

### 核心能力

| 能力 | 说明 |
|------|------|
| 服务注册 | 服务注册、反注册、心跳 |
| 健康检查 | 周期性健康检查、故障检测 |
| 流量分发 | 多后端路由、权重分配 |
| 安全策略 | 网络隔离、访问控制列表 |
| 动态路由 | 服务发现集成、动态更新 |

---

## 📖 接口定义

### NetworkManager 接口

**位置**：`infra/network/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `register_service` | `service: Service` | `str` | 注册服务 |
| `deregister_service` | `service_id: str` | `bool` | 注销服务 |
| `discover_services` | `name: str` | `List[Endpoint]` | 服务发现 |
| `get_load_balancer` | `name: str` | `LoadBalancer` | 获取负载均衡器 |
| `apply_policy` | `policy: NetworkPolicy` | `bool` | 应用网络策略 |
| `get_dns_records` | `domain: str` | `List[DnsRecord]` | 获取 DNS 记录 |

### 数据模型

| 模型 | 字段 | 说明 |
|------|------|------|
| `Service` | `name`, `endpoints`, `metadata`, `health_check` | 服务定义 |
| `Endpoint` | `address`, `port`, `weight`, `health` | 服务端点 |
| `LoadBalancer` | `algorithm`, `backends`, `health_check` | 负载均衡器 |
| `NetworkPolicy` | `type`, `rules`, `priority` | 网络策略 |
| `DnsRecord` | `name`, `type`, `value`, `ttl` | DNS 记录 |

---

## 🏭 工厂函数

### Network 工厂

**位置**：`infra/network/factory.py`

**函数签名**：
```python
create_network_manager(config: NetworkConfig) -> NetworkManager
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.backend` | str | 后端类型：`consul`, `etcd`, `kubernetes`, `static` |
| `config.lb_algorithm` | str | 负载均衡算法：`round_robin`, `weighted`, `least_conn` |
| `config.health_check_interval` | int | 健康检查间隔（秒）|

**使用示例**：
```python
from infra.network import create_network_manager

# Consul 后端
config = NetworkConfig(
    backend="consul",
    lb_algorithm="weighted",
    health_check_interval=10
)
network = create_network_manager(config)

# Kubernetes 后端
config = NetworkConfig(
    backend="kubernetes",
    lb_algorithm="least_conn",
    health_check_interval=15
)
network = create_network_manager(config)
```

---

## ⚙️ 配置结构

### 配置文件示例

**位置**：`config/infra/network.yaml`

```yaml
# 网络管理配置
network:
  # 服务发现后端
  discovery:
    backend: consul  # consul, etcd, kubernetes, static
    address: localhost:8500
    timeout: 5
    
  # 健康检查配置
  health_check:
    enabled: true
    interval: 10  # 秒
    timeout: 3
    healthy_threshold: 2
    unhealthy_threshold: 3
    
  # 负载均衡配置
  load_balancer:
    algorithm: weighted  # round_robin, weighted, least_conn, consistent_hash
    connection_timeout: 5
    idle_timeout: 60
    
  # 网络策略配置
  policy:
    default_action: allow  # allow, deny
    isolation: tenant  # tenant, namespace, pod
    
  # DNS 配置
  dns:
    enabled: true
    domain: ai-platform.local
    ttl: 30
    dynamic_update: true
```

---

## 🚀 使用示例

### 服务注册

```python
# 1. 创建网络管理器
from infra.network import create_network_manager

network = create_network_manager(config)

# 2. 注册服务
service = Service(
    name="ai-platform-core",
    endpoints=[
        Endpoint(address="10.0.0.1", port=8000, weight=10),
        Endpoint(address="10.0.0.2", port=8000, weight=10),
        Endpoint(address="10.0.0.3", port=8000, weight=5)
    ],
    health_check=HealthCheck(
        path="/health",
        interval=10
    )
)
service_id = await network.register_service(service)
print(f"服务 ID: {service_id}")

# 3. 注销服务
await network.deregister_service(service_id)
```

### 服务发现

```python
# 1. 发现服务
endpoints = await network.discover_services("ai-platform-core")
for ep in endpoints:
    print(f"端点: {ep.address}:{ep.port}, 权重: {ep.weight}, 健康: {ep.health}")

# 2. 获取负载均衡器
lb = await network.get_load_balancer("ai-platform-core")
selected = lb.select()  # 根据算法选择后端
print(f"选中的后端: {selected.address}:{selected.port}")
```

### 网络策略

```python
# 1. 应用网络策略
policy = NetworkPolicy(
    type="access_control",
    rules=[
        {"action": "allow", "source": "10.0.0.0/8", "destination": "10.0.1.0/24"},
        {"action": "deny", "source": "0.0.0.0/0", "destination": "10.0.1.0/24"}
    ],
    priority=1
)
await network.apply_policy(policy)
```

### DNS 管理

```python
# 1. 获取 DNS 记录
records = await network.get_dns_records("ai-platform-core.ai-platform.local")
for record in records:
    print(f"记录: {record.name} -> {record.value} (TTL: {record.ttl})")
```

---

## 📁 文件结构

```
infra/network/
├── __init__.py               # 模块导出
├── base.py                   # NetworkManager 接口
├── factory.py                # create_network_manager()
├── schemas.py                # 数据模型
└── manager.py               # 网络管理实现
```

---

## 🔧 扩展指南

### 添加新的服务发现后端

1. **创建实现文件**：`infra/network/discovery/my_backend.py`
2. **实现接口**：
```python
from infra.network.discovery.base import ServiceDiscovery

class MyBackendDiscovery(ServiceDiscovery):
    async def register(self, service: Service) -> str:
        # 实现服务注册逻辑
    
    async def deregister(self, service_id: str) -> bool:
        # 实现服务注销逻辑
    
    async def discover(self, name: str) -> List[Endpoint]:
        # 实现服务发现逻辑
```
3. **注册到工厂**：在 `factory.py` 中添加新后端分支

### 添加新的负载均衡算法

1. **实现算法类**：继承基类实现 `select()` 方法
2. **注册算法**：在 `factory.py` 中注册新算法
3. **配置使用**：在配置文件中指定新算法

---

## ⚠️ 注意事项

1. **服务发现一致性**：确保服务状态的一致性，避免路由到不健康的后端
2. **健康检查频率**：合理配置健康检查频率，避免频繁检测影响性能
3. **网络隔离**：确保不同租户的网络隔离，避免跨租户访问
4. **DNS 缓存**：注意 DNS 缓存时间，避免服务变更后解析不到新地址

---

## 🔗 相关链接

- **上级**：[← 返回 infra 索引](../index.md)
- **算力管理**：[→ compute](compute/index.md)
- **内存管理**：[→ memory](memory/index.md)
- **Consul 文档**：https://www.consul.io/docs
- **Kubernetes Service**：https://kubernetes.io/docs/concepts/services-networking/

---

*最后更新: 2026-04-11*

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/network/*`
