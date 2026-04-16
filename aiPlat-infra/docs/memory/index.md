# 📚 Memory 模块文档（设计真值：以代码事实为准）

> 说明：memory（infra）侧是“资源/缓存/显存”等基础设施抽象，与 core/harness 的“对话记忆/语义记忆”概念不同。As-Is 以 `infra/memory/*` 代码与测试为准。

> 内存资源管理 - 基础设施层

---

## 🎯 模块定位

**职责**：管理和抽象内存资源，包括系统内存、显存（VRAM）、HBM 等多级内存的分配、缓存和 OOM 防护。

**依赖方向**：
```
memory 模块 → 被 core/platform 调用（通过 infra 工厂接口）
memory 模块 → 不依赖任何内部模块
```

---

## 🏗️ 能力概述

### 支持的内存类型

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| **RAM** | 系统内存 | 应用缓存、数据处理 |
| **VRAM** | 显存 | GPU 推理、模型加载 |
| **HBM** | 高带宽内存 | 大模型推理、高性能计算 |

### 核心能力

| 能力 | 说明 |
|------|------|
| 多级缓存 | L1/L2/L3 多级缓存管理 |
| 内存池 | 预分配内存池，减少分配开销 |
| 显存管理 | GPU 显存分配、回收、碎片整理 |
| OOM 防护 | 内存不足时自动保护关键进程 |
| 内存回收 | 主动回收冷数据内存 |
| 内存监控 | 实时监控内存使用情况 |

---

## 📖 接口定义

### MemoryManager 接口

**位置**：`infra/memory/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `allocate` | `request: MemoryRequest` | `Allocation` | 分配内存 |
| `release` | `allocation_id: str` | `bool` | 释放内存 |
| `get_stats` | `node_id: str` | `MemoryStats` | 获取内存统计 |
| `set_limit` | `tenant_id: str`, `limit: MemoryLimit` | `bool` | 设置租户内存限制 |
| `enable_oom_protection` | `threshold: float` | `bool` | 启用 OOM 保护 |
| `compact` | `node_id: str` | `bool` | 内存碎片整理 |

### 数据模型

| 模型 | 字段 | 说明 |
|------|------|------|
| `MemoryRequest` | `type`, `size`, `tenant_id`, `priority` | 内存请求 |
| `Allocation` | `id`, `address`, `size`, `expires_at` | 内存分配 |
| `MemoryStats` | `total`, `used`, `available`, `cached` | 内存统计 |
| `MemoryLimit` | `soft_limit`, `hard_limit`, `swap_limit` | 内存限制 |

---

## 🏭 工厂函数

### Memory 工厂

**位置**：`infra/memory/factory.py`

**函数签名**：
```python
create_memory_manager(config: MemoryConfig) -> MemoryManager
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.type` | str | 内存类型：`ram`, `vram`, `hbm` |
| `config.backend` | str | 后端实现：`system`, `cuda`, `custom` |
| `config.pool_enabled` | bool | 是否启用内存池 |
| `config.oom_threshold` | float | OOM 保护阈值（0-1）|

**使用示例**：
```python
from infra.memory import create_memory_manager

# RAM 内存管理
config = MemoryConfig(
    type="ram",
    pool_enabled=True,
    oom_threshold=0.9
)
memory = create_memory_manager(config)

# VRAM 显存管理（CUDA）
config = MemoryConfig(
    type="vram",
    backend="cuda",
    pool_enabled=True,
    oom_threshold=0.85
)
memory = create_memory_manager(config)
```

---

## ⚙️ 配置结构

### 配置文件示例

**位置**：`config/infra/memory.yaml`

```yaml
# 内存管理配置
memory:
  # RAM 配置
  ram:
    enabled: true
    pool_enabled: true
    pool_size: 8Gi
    oom_threshold: 0.9
    
    # 多级缓存配置
    cache_levels:
      - name: L1
        size: 256Mi
        policy: lru
      - name: L2
        size: 2Gi
        policy: lru
      - name: L3
        size: 8Gi
        policy: lru
    
    # 租户内存限制
    tenant_limits:
      tenant-001:
        soft_limit: 16Gi
        hard_limit: 32Gi
      tenant-002:
        soft_limit: 8Gi
        hard_limit: 16Gi

  # VRAM 配置
  vram:
    enabled: true
    backend: cuda  # cuda, opencl, custom
    pool_enabled: true
    pool_size: 16Gi
    oom_threshold: 0.85
    
    # 模型缓存配置
    model_cache:
      max_models: 3
      eviction_policy: lru
      preloaded_models:
        - gpt-4
        - gpt-3.5-turbo
```

---

## 🚀 使用示例

### 内存分配

```python
# 1. 创建内存管理器
from infra.memory import create_memory_manager

memory = create_memory_manager(config)

# 2. 分配内存
request = MemoryRequest(
    type="ram",
    size="2Gi",
    tenant_id="tenant-001",
    priority="high"
)
allocation = await memory.allocate(request)
print(f"分配 ID: {allocation.id}")
print(f"地址: {allocation.address}")

# 3. 使用完毕释放
await memory.release(allocation.id)
```

### 内存监控

```python
# 1. 获取内存统计
stats = await memory.get_stats("node-001")
print(f"总内存: {stats.total}")
print(f"已使用: {stats.used}")
print(f"可用: {stats.available}")
print(f"缓存: {stats.cached}")

# 2. 检查内存压力
if stats.used / stats.total > 0.9:
    print("警告：内存使用率超过 90%")
```

### OOM 保护

```python
# 1. 启用 OOM 保护
await memory.enable_oom_protection(threshold=0.85)
print("OOM 保护已启用")

# 2. 设置租户内存限制
limit = MemoryLimit(
    soft_limit="16Gi",
    hard_limit="32Gi",
    swap_limit="8Gi"
)
await memory.set_limit("tenant-001", limit)
```

### 显存管理（GPU）

```python
# 1. 分配 VRAM
vram_request = MemoryRequest(
    type="vram",
    size="8Gi",
    priority="critical"
)
allocation = await memory.allocate(vram_request)

# 2. 加载模型到显存
model = load_model_to_gpu("gpt-4", allocation.address)

# 3. 显存碎片整理
await memory.compact("gpu-node-001")

# 4. 释放 VRAM
await memory.release(allocation.id)
```

---

## 📁 文件结构

```
infra/memory/
├── __init__.py               # 模块导出
├── base.py                   # MemoryManager 接口
├── factory.py                # create_memory_manager()
├── schemas.py                # 数据模型
└── manager.py               # 内存管理实现
```

---

## 🔧 扩展指南

### 添加新的内存后端

1. **创建实现文件**：`infra/memory/my_backend.py`
2. **实现接口**：
```python
from infra.memory.base import MemoryManager

class MyBackendMemoryManager(MemoryManager):
    async def allocate(self, request: MemoryRequest) -> Allocation:
        # 实现内存分配逻辑
    
    async def release(self, allocation_id: str) -> bool:
        # 实现内存释放逻辑
    
    # ... 实现其他接口方法
```
3. **注册到工厂**：在 `factory.py` 中添加新后端分支

### 添加新的缓存策略

1. **实现缓存策略类**：继承基类实现 `put()`, `get()`, `evict()`
2. **注册策略**：在 `cache.py` 中注册新策略
3. **配置使用**：在配置文件中指定新策略

---

## ⚠️ 注意事项

1. **内存泄漏**：确保正确释放内存，避免泄漏
2. **显存碎片**：大模型场景下需要定期整理显存碎片
3. **OOM 保护阈值**：建议设置在 85-90%，避免频繁触发
4. **多级缓存**：合理配置各级缓存大小，避免内存浪费

---

## 🔗 相关链接

- **上级**：[← 返回 infra 索引](../index.md)
- **算力管理**：[→ compute](../compute/index.md)
- **CUDA 文档**：https://docs.nvidia.com/cuda/
- **Kubernetes 内存管理**：https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/

---

*最后更新: 2026-04-11*

---

## 证据索引（Evidence Index｜抽样）

- 代码入口：`infra/memory/*`
