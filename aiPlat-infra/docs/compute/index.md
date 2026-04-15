# 📚 Compute 模块文档

> 算力资源管理 - 基础设施层

---

## 🎯 模块定位

**职责**：管理和抽象计算资源，包括 CPU、GPU、NPU、TPU 等异构算力的分配、调度和弹性扩缩。

**依赖方向**：
```
compute 模块 → 被 core/platform 调用（通过 infra 工厂接口）
compute 模块 → 不依赖任何内部模块
```

**部署模式**：底层实现可以是 Kubernetes API（推荐）、Docker API 或裸机管理。

---

## 🏗️ 能力概述

### 支持的资源类型

| 资源类型 | 说明 | 典型场景 |
|----------|------|----------|
| **CPU** | 通用计算单元 | 通用推理、预处理 |
| **GPU** | 图形处理器 | LLM 推理、向量计算 |
| **NPU** | 神经网络处理器 | 特定模型加速 |
| **TPU** | 张量处理单元 | TensorFlow 模型加速 |

### 核心能力

| 能力 | 说明 |
|------|------|
| 资源分配 | 根据任务需求分配算力资源 |
| 任务调度 | 将任务调度到合适的计算节点 |
| 弹性扩缩 | 根据负载自动扩缩容 |
| 负载均衡 | 多节点间负载均衡 |
| 算力配额 | 按租户/项目分配算力限额 |

---

## 📖 接口定义

### ComputeManager 接口

**位置**：`infra/compute/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `allocate` | `resource_request: ResourceRequest` | `Allocation` | 分配算力资源 |
| `release` | `allocation_id: str` | `bool` | 释放资源 |
| `list_nodes` | `filters: dict` | `List[Node]` | 列出计算节点 |
| `get_node` | `node_id: str` | `Node` | 获取节点详情 |
| `submit_task` | `task: Task` | `TaskId` | 提交计算任务 |
| `get_task_status` | `task_id: str` | `TaskStatus` | 获取任务状态 |
| `cancel_task` | `task_id: str` | `bool` | 取消任务 |

### 数据模型

| 模型 | 字段 | 说明 |
|------|------|------|
| `ResourceRequest` | `resource_type`, `quantity`, `priority` | 资源请求 |
| `Allocation` | `id`, `node_id`, `resources`, `expires_at` | 资源分配 |
| `Node` | `id`, `type`, `status`, `capacity`, `available` | 计算节点 |
| `Task` | `id`, `command`, `resources`, `timeout` | 计算任务 |
| `TaskStatus` | `id`, `state`, `progress`, `result` | 任务状态 |

---

## 🏭 工厂函数

### Compute 工厂

**位置**：`infra/compute/factory.py`

**函数签名**：
```python
create_compute_manager(config: ComputeConfig) -> ComputeManager
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.backend` | str | 后端类型：`kubernetes`, `docker`, `baremetal` |
| `config.default_quota` | dict | 默认算力配额 |
| `config.scheduling_policy` | str | 调度策略：`fifo`, `priority`, `fair_share` |

**使用示例**：
```python
from infra.compute import create_compute_manager

# Kubernetes 后端
config = ComputeConfig(
    backend="kubernetes",
    default_quota={"gpu": 4, "cpu": 8},
    scheduling_policy="fair_share"
)
compute = create_compute_manager(config)

# Docker 后端（开发测试）
config = ComputeConfig(
    backend="docker",
    default_quota={"gpu": 2, "cpu": 4}
)
compute = create_compute_manager(config)
```

---

## ⚙️ 配置结构

### 配置文件示例

**位置**：`config/infra/compute.yaml`

```yaml
# 计算资源管理配置
compute:
  # 后端类型
  backend: kubernetes  # kubernetes, docker, baremetal
  
  # 调度配置
  scheduling:
    policy: fair_share  # fifo, priority, fair_share
    preemption: true   # 是否允许抢占
    max_wait_time: 300 # 最大等待时间（秒）
  
  # 默认配额
  default_quota:
    cpu: 8
    gpu: 2
    memory: 32Gi
  
  # 租户配额
  tenant_quotas:
    tenant-001:
      cpu: 16
      gpu: 4
      memory: 64Gi
    tenant-002:
      cpu: 8
      gpu: 1
      memory: 16Gi
  
  # 资源标签
  labels:
    - key: workload_type
      values: [interactive, batch, training]
    - key: priority
      values: [low, normal, high, critical]
```

---

## 🚀 使用示例

### 资源分配

```python
# 1. 创建计算管理器
from infra.compute import create_compute_manager

compute = create_compute_manager(config)

# 2. 请求 GPU 资源
request = ResourceRequest(
    resource_type="gpu",
    quantity=2,
    priority="high",
    duration=3600  # 1小时
)
allocation = await compute.allocate(request)
print(f"分配 ID: {allocation.id}")
print(f"节点: {allocation.node_id}")

# 3. 使用完毕释放资源
await compute.release(allocation.id)
```

### 任务调度

```python
# 1. 提交计算任务
task = Task(
    command="python inference.py --model gpt-4",
    resources={"gpu": 1, "cpu": 4},
    timeout=3600,
    priority="normal"
)
task_id = await compute.submit_task(task)
print(f"任务 ID: {task_id}")

# 2. 查询任务状态
status = await compute.get_task_status(task_id)
print(f"状态: {status.state}, 进度: {status.progress}%")

# 3. 取消任务
await compute.cancel_task(task_id)
```

### 节点管理

```python
# 1. 列出所有 GPU 节点
nodes = await compute.list_nodes({"type": "gpu", "status": "ready"})
for node in nodes:
    print(f"节点: {node.id}, 可用 GPU: {node.available['gpu']}")

# 2. 获取特定节点详情
node = await compute.get_node("gpu-node-001")
print(f"状态: {node.status}")
print(f"已用: {node.used}")
print(f"可用: {node.available}")
```

---

## 📁 文件结构

```
infra/compute/
├── __init__.py               # 模块导出
├── base.py                   # ComputeManager 接口
├── factory.py                # create_compute_manager()
├── schemas.py                # 数据模型
└── manager.py               # 算力管理实现
```

---

## 🔧 扩展指南

### 添加新的后端实现

1. **创建实现文件**：`infra/compute/my_backend.py`
2. **实现接口**：
```python
from infra.compute.base import ComputeManager

class MyBackendClient(ComputeManager):
    async def allocate(self, request: ResourceRequest) -> Allocation:
        # 实现资源分配逻辑
    
    async def release(self, allocation_id: str) -> bool:
        # 实现资源释放逻辑
    
    # ... 实现其他接口方法
```
3. **注册到工厂**：在 `factory.py` 中添加新后端分支

### 添加新的资源类型

1. **定义资源类型**：在 `types.py` 中添加新类型
2. **更新接口**：在 `base.py` 接口中添加新类型支持
3. **实现支持**：在各后端实现中添加支持

---

## ⚠️ 注意事项

1. **资源隔离**：确保不同租户的资源隔离，避免资源争抢
2. **超时处理**：长时间运行的任务需要设置合理的超时时间
3. **错误恢复**：实现任务失败后的自动重试和恢复机制
4. **成本控制**：监控算力资源使用，避免不必要的资源浪费

---

## 🔗 相关链接

- **上级**：[← 返回 infra 索引](../index.md)
- **内存管理**：[→ memory](memory/index.md)
- **Kubernetes 文档**：https://kubernetes.io/docs/
- **GPU 调度**：[→ NVIDIA Device Plugins](https://github.com/NVIDIA/k8s-device-plugin)

---

*最后更新: 2026-04-11*