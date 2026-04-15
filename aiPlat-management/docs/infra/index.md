# 基础设施层管理（Layer 0）

> GPU 节点、推理服务、算力调度、存储、网络、监控的完整运维能力

---

## 一、模块概览

基础设施层管理系统提供从节点到服务的完整运维能力：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        基础设施层运维边界                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  节点层（物理资源管理）                                                      │
│  ├── GPU节点添加/删除/扩缩容                                                 │
│  ├── GPU驱动安装/升级                                                        │
│  ├── 节点健康检查（温度/功耗/网络）                                          │
│  └── 节点标签/污点管理                                                       │
│                                                                              │
│  服务层（AI服务生命周期）                                                   │
│  ├── 服务部署（容器拉起、镜像选择）                                          │
│  ├── 镜像版本管理                                                            │
│  ├── 服务扩缩容                                                              │
│  └── 服务配置（max_tokens, temperature等）                                   │
│                                                                              │
│  模型层（模型管理）                                                          │
│  ├── 内置模型（配置文件定义）                                                │
│  ├── 本地模型（Ollama 自动扫描）                                             │
│  ├── 自定义模型（用户添加）                                                  │
│  ├── 模型健康检查                                                            │
│  └── 模型连通性测试                                                          │
│                                                                              │
│  算力层（调度与配额）                                                        │
│  ├── GPU资源池管理                                                           │
│  ├── 服务/租户配额                                                           │
│  ├── 任务队列/优先级调度                                                     │
│  └── 弹性伸缩                                                                │
│                                                                              │
│  存储层                                                                      │
│  ├── 向量存储管理                                                            │
│  ├── 模型存储管理                                                            │
│  └── PVC/存储卷管理                                                          │
│                                                                              │
│  网络层                                                                      │
│  ├── 服务发现/内部DNS                                                        │
│  ├── 负载均衡配置                                                            │
│  └── 网络策略/防火墙                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、功能模块

### 2.1 节点管理

**文档**：[nodes.md](./nodes.md)

**核心功能**：
- GPU 节点生命周期管理（添加/删除/扩缩容）
- GPU 驱动管理（版本检查/升级/回滚）
- 节点监控（利用率/温度/功耗）
- 节点维护（标签/污点/驱逐）

**界面预览**：
- GPU 节点列表
- 节点详情（GPU 状态、温度、功耗）
- 添加节点向导
- 驱动管理面板

---

### 2.2 模型管理

**文档**：[models.md](./models.md)

**核心功能**：
- 模型列表查看（内置/本地/自定义）
- 模型添加与配置
- 模型连通性测试
- Ollama 本地模型扫描
- 模型健康状态监控

**界面预览**：
- 模型列表（分组显示：内置/本地/自定义）
- 添加模型弹窗（支持多种 Provider）
- 模型详情（配置参数、健康状态、使用统计）
- 连通性测试结果

---

### 2.3 服务管理

**文档**：[services.md](./services.md)

**核心功能**：
- AI 推理服务部署
- 镜像仓库管理
- 服务扩缩容（手动/自动）
- 服务配置管理
- 服务日志与事件

**界面预览**：
- 服务列表（状态、Pod实例、资源使用）
- 部署新服务向导
- 镜像仓库管理
- 服务详情与操作

---

### 2.4 算力调度

**文档**：[scheduler.md](./scheduler.md)

**核心功能**：
- 资源配额管理（按团队/服务分配）
- 调度策略配置（优先级/亲和性）
- 任务队列管理
- 弹性伸缩配置

**界面预览**：
- 资源配额面板
- 调度策略配置
- 任务队列监控
- 弹性伸缩策略

---

### 2.5 存储管理

**文档**：[storage.md](./storage.md)

**核心功能**：
- 向量存储管理（Qdrant/Milvus/Weaviate）
- 模型存储管理（版本/缓存）
- PVC 存储卷管理（创建/扩容/快照）

**界面预览**：
- 向量数据库状态
- 模型仓库管理
- PVC 列表与详情

---

### 2.6 网络管理

**文档**：[network.md](./network.md)

**核心功能**：
- 服务发现（Kubernetes Service）
- 负载均衡（Ingress/LoadBalancer）
- 网络策略（NetworkPolicy）
- 网络排查工具

**界面预览**：
- 服务列表（ClusterIP/LoadBalancer）
- Ingress 配置管理
- 网络策略列表
- 连通性测试工具

---

### 2.7 监控告警

**文档**：[monitoring.md](./monitoring.md)

**核心功能**：
- 指标监控（GPU/服务/网络/存储）
- 告警规则配置
- 告警通知管理
- 审计日志查询

**界面预览**：
- 监控大屏（集群概览、GPU 监控）
- 告警规则配置
- 告警历史查询
- 审计日志检索

---

## 三、运维能力矩阵

| 模块 | 查看能力 | 操作能力 | 监控能力 | 告警能力 |
|------|---------|---------|---------|---------|
| 节点管理 | ✅ | ✅ | ✅ | ✅ |
| 模型管理 | ✅ | ✅ | ✅ | ✅ |
| 服务管理 | ✅ | ✅ | ✅ | ✅ |
| 算力调度 | ✅ | ✅ | ✅ | ✅ |
| 存储管理 | ✅ | ✅ | ✅ | ✅ |
| 网络管理 | ✅ | ✅ | ✅ | ✅ |
| 监控告警 | ✅ | ✅ | ✅ | ✅ |

---

## 四、用户角色

| 角色 | 权限 |
|------|------|
| **运维工程师** | 全部模块的完整操作权限 |
| **开发工程师** | 服务管理、存储管理的查看和部分操作权限 |
| **访客** | 所有模块的只读权限 |

---

## 五、实施状态

| 层级 | 管理系统覆盖 | 实施状态 |
|------|-------------|---------|
| **Layer 0 - 基础设施层** | 完整运维能力 | ✅ 已实施 |
| **Layer 1 - 核心能力层** | 预留管理接口 | 🔜 待实施 |
| **Layer 2 - 平台服务层** | 预留管理接口 | 🔜 待实施 |
| **Layer 3 - 应用接入层** | 预留管理接口 | 🔜 待实施 |

---

### 5.1 API 实现状态

| 模块 | API 端点 | 实现状态 |
|------|---------|---------|
| **节点管理** | GET/POST/DELETE /nodes | ✅ 已实现 |
| | POST /nodes/{name}/drain | ✅ 已实现 |
| | POST /nodes/{name}/restart | ✅ 已实现 |
| | GET/POST /drivers | 🔜待实现 |
| **模型管理** | GET/POST /models | ✅ 已实现 |
| | PUT/DELETE /models/{id} | ✅ 已实现 |
| | POST /models/{id}/enable/disable | ✅ 已实现 |
| | POST /models/{id}/test/*| ✅ 已实现 |
| **服务管理** | GET/POST/DELETE /services | ✅ 已实现 |
| | POST /services/{name}/scale| ✅ 已实现 |
| | GET /services/{name}/logs | 🔜 待实现 |
| | GET /services/{name}/events | 🔜 待实现 |
| | GET/POST /images | 🔜 待实现 |
| **算力调度** | GET /scheduler/quotas | ✅ 已实现 |
| | POST/PUT/DELETE /scheduler/quotas | 🔜 待实现 |
| | GET /scheduler/tasks | ✅ 已实现 |
| | POST/DELETE /scheduler/tasks | 🔜 待实现 |
| **存储管理** | GET /storage/pvcs | ✅ 已实现 |
| | GET /storage/collections | ✅ 已实现 |
| | POST /storage/pvc | 🔜 待实现 |
| | POST /storage/vector/collections | 🔜 待实现 |
| **网络管理** | GET /network/services | ✅ 已实现 |
| | GET /network/ingresses | ✅ 已实现 |
| | POST /network/*| 🔜 待实现 |
| **监控告警** | GET /monitoring/metrics | ✅ 已实现 |
| | GET/POST /alerts/rules | ✅ 已实现 |
| | GET /audit/logs | 🔜 待实现 |

### 5.2 前端实现状态

| 模块 | 页面 | 实现状态 |
|------|------|---------|
| **节点管理** | 节点列表 | ✅ 已实现 |
| | 添加节点弹窗 | ✅ 已实现 |
| | 节点详情页 | 🔜待实现 |
| | 驱动管理 | 🔜 待实现 |
| **模型管理** | 模型列表 | ✅ 已实现 |
| | 添加模型弹窗 | ✅ 已实现 |
| | 模型详情页 | 🔜 待实现 |
| **服务管理** | 服务列表 | ✅ 已实现 |
| | 部署服务弹窗 | 🔜 待实现 |
| | 服务详情页 | 🔜 待实现 |
| | 镜像管理 | 🔜 待实现 |
| **其他模块** | 算力调度/存储/网络/监控 | ✅ 基础列表已实现 |

---

## 六、相关文档

### 基础设施层运维模块

- [节点管理](nodes.md) - GPU 节点生命周期管理
- [模型管理](models.md) - 模型配置、健康检查、连通性测试
- [服务管理](services.md) - AI 推理服务管理
- [算力调度](scheduler.md) - 资源配额与任务队列
- [存储管理](storage.md) - 向量存储、模型存储、PVC
- [网络管理](network.md) - 服务发现、负载均衡、网络策略
- [监控告警](monitoring.md) - 指标监控、告警规则、审计日志

### 其他层级

- [系统总览](../index.md) - Management 系统架构
- [核心能力层管理](../core/index.md) - Layer 1 管理接口
- [平台服务层管理](../platform/index.md) - Layer 2 管理接口
- [应用接入层管理](../app/index.md) - Layer 3 管理接口

---

## 七、技术实现

### 后端 API

```
/api/infra/
├── /nodes                    # 节点管理
│   ├── GET /                # 获取节点列表
│   ├── POST /               # 添加节点
│   ├── GET /{name}          # 获取节点详情
│   └── POST /{name}/drain   # 驱逐节点
│
├── /models                   # 模型管理
│   ├── GET /                # 获取模型列表
│   ├── POST /               # 添加模型
│   ├── GET /{model_id}      # 获取模型详情
│   ├── PUT /{model_id}      # 更新模型配置
│   ├── DELETE /{model_id}   # 删除模型
│   ├── POST /{model_id}/enable    # 启用模型
│   ├── POST /{model_id}/disable   # 禁用模型
│   ├── POST /{model_id}/test/connectivity  # 连通性测试
│   └── POST /{model_id}/test/response      # 响应测试
│
├── /services                # 服务管理
│   ├── GET /                # 获取服务列表
│   ├── POST /               # 部署新服务
│   ├── GET /{name}          # 获取服务详情
│   └── POST /{name}/scale   # 扩缩容
│
├── /scheduler               # 算力调度
│   ├── /quotas              # 配额管理
│   ├── /policies            # 调度策略
│   ├── /queue               # 任务队列
│   └── /autoscaling         # 弹性伸缩
│
├── /storage                 # 存储管理
│   ├── /vector              # 向量存储
│   ├── /models              # 模型存储
│   └── /pvc                 # PVC 管理
│
├── /network                 # 网络管理
│   ├── /services            # 服务发现
│   ├── /ingress             # Ingress 管理
│   └── /policies            # 网络策略
│
└── /monitoring              # 监控告警
    ├── /metrics             # 指标采集
    ├── /alerts              # 告警规则
    └── /audit               # 审计日志
```

### 前端路由

```
/infra
├── /nodes                   # 节点管理
│   ├── /                    # 节点列表
│   └── /add                 # 添加节点
│
├── /models                  # 模型管理
│   ├── /                    # 模型列表
│   └── /add                 # 添加模型
│
├── /services                # 服务管理
│   ├── /                    # 服务列表
│   ├── /deploy              # 部署新服务
│   └── /:name               # 服务详情
│
├── /scheduler               # 算力调度
│   ├── /quotas              # 配额管理
│   ├── /policies            # 调度策略
│   ├── /queue               # 任务队列
│   └── /autoscaling         # 弹性伸缩
│
├── /storage                 # 存储管理
│   ├── /vector              # 向量存储
│   ├── /models              # 模型存储
│   └── /pvc                 # PVC 管理
│
├── /network                 # 网络管理
│   ├── /services            # 服务发现
│   ├── /ingress             # Ingress 管理
│   └── /policies            # 网络策略
│
└── /monitoring              # 监控告警
    ├── /overview            # 监控概览
    ├── /alerts              # 告警规则
    └── /audit               # 审计日志
```

---

*最后更新:2026-04-13  
**版本**：v4.1  
**维护团队**：AI Platform Team

---

## 八、架构边界

**重要**：本模块（基础设施层管理）的业务逻辑在 `aiPlat-infra` 层实现。

### 8.1 架构关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (5173)                            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP (浏览器)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  aiPlat-management (8000)                            │
│                       管理系统层                                    ││  management/api/infra.py:                                        │
│  - HTTP 转发到 aiPlat-infra API                                    │
│  - 不包含业务逻辑实现                                              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ HTTP 调用 (httpx)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     aiPlat-infra (8001)                             │
│                       基础设施业务层                                ││  infra/management/api/main.py:                                    │
│  - REST API 端点定义                                               │
│  - infra/management/node/manager.py: 实现 NodeManager             │
│  - infra/management/service/manager.py: 实现 ServiceManager        │
│  - infra/management/storage/manager.py: 实现 StorageManager       │
│  - infra/management/network/manager.py: 实现 NetworkManager│
│  - infra/management/scheduler/manager.py: 实现 SchedulerManager   │
│  - infra/management/monitoring/manager.py: 实现 MonitoringManager │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 API 端点对应

| 管理界面 | Management API | Infra API | 实现位置 |
|----------|----------------|-----------|----------|
| 节点管理 | `/api/infra/nodes` | `/api/infra/nodes` | `infra/management/node/manager.py` |
| 模型管理 | `/api/infra/models` | `/api/infra/models` | `infra/management/model/manager.py` |
| 服务管理 | `/api/infra/services` | `/api/infra/services` | `infra/management/service/manager.py` |
| 存储管理 | `/api/infra/storage` | `/api/infra/storage` | `infra/management/storage/manager.py` |
| 网络管理 | `/api/infra/network` | `/api/infra/network` | `infra/management/network/manager.py` |
| 调度管理 | `/api/infra/scheduler` | `/api/infra/scheduler` | `infra/management/scheduler/manager.py` |

### 8.3 启动顺序

```bash
# 1. 先启动基础设施层
cd aiPlat-infra && ./start.sh  # 端口 8001

# 2. 再启动管理系统层
cd aiPlat-management && ./start.sh # 端口 8000
```

### 8.4 开发指南

**添加新的管理功能**：
1. 在 `aiPlat-infra/infra/management/` 添加 Manager 类
2. 在 `aiPlat-infra/infra/management/api/main.py` 添加 REST API 端点
3. 在 `aiPlat-management/management/infra_client.py` 添加 HTTP 客户端方法
4. 在 `aiPlat-management/management/api/infra.py` 添加 API 转发

详细架构说明：[architecture-boundary.md](../architecture-boundary.md)