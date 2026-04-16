# 架构边界说明

> 重要：aiPlat-management 和 aiPlat-infra 的层级边界

---

## 0. 文档说明（设计为准）

本文件描述的是 **aiPlat-management 的目标设计（To‑Be）**，其约束对实现具有“规范性”。  
当前仓库中的实现可能仍处于原型阶段；实现现状请参见：

- `docs/IMPLEMENTATION_STATUS.md`

## 一、架构层级

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Web UI)                            │
│                         前端展示层                                  │
└────────────────────────────────┬────────────────────────────────────┘│
                                 │ HTTP (浏览器)│                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   aiPlat-management (8000)                            │
│                       管理系统层                                    │
│                                     ││  职责：                                                          │
│  - Dashboard 聚合展示│  - Alerting 告警管理│  - Diagnostics 健康诊断│  - 统一 API 入口                         │
│                                     ││  API:                                                           │
│  - /api/dashboard/*                                                 │
│  - /api/alerting/*                                                  │
│  - /api/diagnostics/*                                               │
│  - /api/infra/* (转发到 infra 层)││└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ HTTP 调用
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     aiPlat-infra (8001)                              │
│                       基础设施业务层                                 │
│                                                                     │
│  职责：                                                             │
│  - 实现基础设施管理业务逻辑│  - 提供 REST API│  - 管理 Manager 实例                                    │
│                                                                     │
│  API:                                                               │
│  - /api/infra/nodes          (节点管理)                            │
│  - /api/infra/services       (服务管理)                            │
│  - /api/infra/storage        (存储管理)                            │
│  - /api/infra/network        (网络管理)                            │
│  - /api/infra/scheduler      (调度管理)                            │
│  - /api/infra/monitoring     (监控管理)                            │
│                                                                     │
│  Manager:                                                           │
│  - NodeManager                                                      │
│  - ServiceManager                                                   │
│  - StorageManager                                                   │
│  - NetworkManager                                                   │
│  - SchedulerManager                                                 │
│  - MonitoringManager│└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、层级职责

### 2.1 aiPlat-management 层（管理系统层）

| 职责 | 说明 |
|------|------|
| Dashboard | 聚合各层状态，提供总览视图 |
| Alerting | 告警规则管理、通知发送 |
| Diagnostics | 健康检查、故障诊断 |
| API 入口 | 统一的 API 网关，转发请求到 infra 层 |

**不应包含：**
- 业务逻辑实现
- 直接操作 Manager 类
- 与业务强耦合的数据存储操作（management 自身可拥有“管理面元数据”存储，例如告警规则、配置版本、审计日志；但不得替代业务层状态存储）

### 2.2 aiPlat-infra 层（基础设施业务层）

| 职责 | 说明 |
|------|------|
| 业务实现 | 节点、服务、存储、网络等管理逻辑 |
| REST API | 提供标准化的 REST API |
| Manager | 具体的业务管理器 |
| 数据存储 | 管理状态和配置数据 |

---

## 三、数据流向

> 关键要求：management 作为统一入口，应通过 **HTTP 调用**各层管理 API 获取 status/metrics/health/diagnostics，并做聚合与标准化输出。  
> management 不应在自身进程内进行“本机探测”作为权威数据源（避免与 infra 业务逻辑边界混淆）。

```
┌─────────────┐│
│   Frontend  ││
│   (Browser)││
└──────┬──────┘│
       │ HTTP
       ▼
┌─────────────────────────────────────────────┐
│            aiPlat-management                 │
│                 (8000├─────────────────────────────┤
│  management/api/dashboard.py                 │
│  management/api/alerting.py│  management/api/diagnostics.py│  management/api/infra.py│└──────────────────┬──────────────────────────┘│
                   │ HTTP 调用
                   │ httpx.AsyncClient
                   ▼
┌─────────────────────────────────────────────┐
│              aiPlat-infra                    │
│                 (8001)                       │
├─────────────────────────────────────────────┤
│  infra/management/api/main.py                │
│                                             │
│  infra/management/node/manager.py            │
│  infra/management/service/manager.py│  infra/management/storage/manager.py       │
│  infra/management/network/manager.py         │
│  infra/management/scheduler/manager.py       │
│  infra/management/monitoring/manager.py      │
└─────────────────────────────────────────────┘
```

---

## 四、代码组织

### 4.1 aiPlat-management

```
aiPlat-management/
├── management/
│   ├── api/
│   │   ├── dashboard.py      # Dashboard API（目标：通过适配器聚合各层 API 数据）
│   │   ├── alerting.py       # 告警 API（目标：规则/历史/通知的统一入口）
│   │   ├── diagnostics.py    # 诊断 API（目标：聚合各层诊断结果）
│   │   ├── infra.py          # Infra API（HTTP 转发到 infra 层）
│   │   └── core.py           # Core API（HTTP 转发到 core 层）
│   ├── dashboard/
│   │   └── infra_adapter.py  # Dashboard 适配器
│   ├── monitoring/           # 监控采集
│   └── alerting/           # 告警引擎│├── pyproject.toml
│   └── start.sh                # 启动脚本
```

### 4.2 aiPlat-infra

```
aiPlat-infra/
├── infra/
│   └── management/
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py          # REST API 入口 (✓ 正确)
│       │   └── run_server.py    # 服务器启动│       ├── node/
│       │   └── manager.py       # 节点管理
│       ├── service/
│       │   └── manager.py       # 服务管理
│       ├── storage/
│       │   └── manager.py       # 存储管理
│       ├── network/
│       │   └── manager.py       # 网络管理
│       ├── scheduler/
│       │   └── manager.py       # 调度管理
│       ├── monitoring/
│       │   └── manager.py       # 监控管理
│       ├── manager.py           # InfraManager 基类
│       └── base.py             # ManagementBase│├── pyproject.toml
│   └── start.sh                # 启动脚本
```

---

## 五、启动顺序

**必须按顺序启动：**

```bash
# 1. 先启动 aiPlat-infra (基础设施层)
cd aiPlat-infra
./start.sh# aiPlat-infra 运行在端口 8001

# 2. 再启动 aiPlat-management (管理系统层)
cd aiPlat-management
./start.sh# aiPlat-management 运行在端口 8000

# 3. 前端 (可选)
cd aiPlat-management/frontend
npm run dev# 前端运行在端口 5173
```

**或者使用统一启动脚本：**

```bash
cd aiPlat-management
./start.sh  # 会自动按顺序启动infra 和 management
```

---

## 六、API 端点对照

| 功能 | Management API | Infra API |
|------|----------------|-----------|
| 节点管理 | `/api/infra/nodes` → HTTP 转发 | `/api/infra/nodes` |
| 服务管理 | `/api/infra/services` → HTTP 转发 | `/api/infra/services` |
| 存储管理 | `/api/infra/storage` → HTTP 转发 | `/api/infra/storage` |
| 网络管理 | `/api/infra/network` → HTTP 转发 | `/api/infra/network` |
| 调度管理 | `/api/infra/scheduler` → HTTP 转发 | `/api/infra/scheduler` |
| 监控管理 | `/api/infra/monitoring` → HTTP 转发 | `/api/infra/monitoring` |

---

## 七、依赖关系

### 7.1 Python 包依赖

**aiPlat-management/pyproject.toml:**
```toml
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "httpx>=0.24.0",# HTTP 客户端，用于调用 infra API
    ...
]
```

**aiPlat-infra/pyproject.toml:**
```toml
# 独立的依赖，不需要依赖 management
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "pydantic>=2.0.0",
    ...
]
```

### 7.2 运行时依赖

```
aiPlat-management (8000)
    │
    ├── HTTP 调用 ──> aiPlat-infra (8001)
    │
    └── 必须等待 infra 启动完成
```

---

## 八、开发指南

### 8.1 添加新的基础设施管理功能

**在 aiPlat-infra 层：**

1. 创建 Manager 类：
```python
# infra/management/new_feature/manager.py
class NewFeatureManager(ManagementBase):
    async def get_status(self) -> Status: ...
    async def list_items(self) -> List[Item]: ...
```

2. 添加 API 端点：
```python
# infra/management/api/main.py
@router.get("/api/infra/new_feature/items")
async def list_new_feature_items():
    manager = get_infra_manager().get("new_feature")
    return await manager.list_items()
```

### 8.2 在 aiPlat-management 层增加聚合展示（推荐方式）

1) **先在目标业务层增加管理 API**（infra/core/platform/app）。  
2) management 通过 `httpx` client 调用目标层 API，并在 adapter/aggregator 中做聚合与标准化。  
3) **避免**：在 management 内部新增“真实业务探测/治理逻辑”，以免破坏管理平面与业务平面的边界。

**在 aiPlat-management 层：**

3. 添加 HTTP 客户端方法：
```python
# management/infra_client.py
async def list_new_feature_items(self) -> List[Dict]:
    return await self._request("GET", "/api/infra/new_feature/items")
```

4. 添加 API转发：
```python
# management/api/infra.py
@router.get("/new_feature/items")
async def list_new_feature_items():
    client = get_infra_client()
    return await client.list_new_feature_items()
```

---

## 九、常见问题

### Q1: 为什么需要两层？

**Answer:**
- **aiPlat-infra**: 业务层，实现具体的基础设施管理逻辑，可以独立部署
- **aiPlat-management**: 管理层，聚合多个业务层（infra、core、platform、app），提供统一入口

### Q2: 能否让 management 直接调用 Manager 类？

**Answer:**
can，但不推荐。分层架构的好处：
- 独立部署：infra 可以独立运行
- 故障隔离：infra 故障不会直接影响 management
- 水平扩展：可以部署多个 infra 实例

### Q3: 如何调试？

**Answer:**
```bash
# 单独调试 infra
cd aiPlat-infra
python -m infra.management.api.run_server

# 访问 API 文档
open http://localhost:8001/docs
```

---

*最后更新:2026-04-12  
**版本**：v4.0
