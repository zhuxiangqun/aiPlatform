# AI 平台管理系统 — 系统分析报告

> 基于 `docs/` 目录下 28 份文档（约 587KB / 11150 行）的完整阅读与分析。
> 分析对象：`aiPlat-management`（独立运维管理平面）及其管理的四层业务架构。

---

## 一、系统定位

`aiPlat-management` 是一个**独立的运维管理平面**，它本身不承载业务逻辑，而是"横切"四层业务架构，提供统一的 Dashboard、监控、告警、诊断与配置入口。

核心设计哲学：

- **管理平面 ≠ 业务平面**：管理平面仅做聚合与转发，业务逻辑下沉到各层。
- **单一数据源**：管理平面不直接持有业务数据，所有数据经 HTTP 从各层获取。
- **HTTP 解耦**：层间通信统一走 HTTP（`httpx.AsyncClient`），管理平面转发至 `infra:8001` / `core:8002` / `platform:8003` / `app:8004`。
- **配置驱动**：不按 artifact key 做特殊分支，所有行为由配置决定。
- **To-Be 与 As-Is 分离**：文档明确区分设计目标（To-Be）与当前实现（As-Is），避免文档美化现实。

---

## 二、四层架构总览

| 层级 | 名称 | 端口 | 状态 | 职责 |
|------|------|------|------|------|
| Layer 0 | 基础设施层 | 8001 | 已实现 | 节点/模型/服务/算力/存储/网络/监控 |
| Layer 1 | 核心能力层 | 8002 | 已实现 | Harness/Agents/Skills/Memory/Knowledge/Adapters |
| Layer 2 | 平台服务层 | 8003 | 预留 | API/Auth/Tenants/Billing/Gateway/Registry |
| Layer 3 | 应用接入层 | 8004 | 预留 | Gateway/Channels/Runtime/Sessions/CLI/Workbench |

**启动顺序**：`infra(8001) → core(8002) → management(8000) → frontend(5173)`

**通信链路**：前端(5173) → 管理平面(8000) → 各业务层，JWT 透传 `X-AIPLAT-*` 头。

---

## 三、管理平面（Management, port 8000）

### 3.1 五大模块

| 模块 | 职责 | 关键 API |
|------|------|----------|
| Dashboard | 聚合四层状态 | `/api/dashboard/status`, `/api/dashboard/metrics` |
| Monitoring | 监控指标 | 经由各 Adapter 转发 |
| Alerting | 告警规则与历史 | `/api/alerts` |
| Diagnostics | 诊断与自检 | `/api/diagnostics/doctor` |
| Config | 配置管理 | YAML 驱动，已迁移 |

### 3.2 Adapter 模式

管理平面通过四个 Adapter 转发请求：

- `InfraAdapter` — 真实探测 PostgreSQL / Redis / Milvus / RabbitMQ / Ollama / Network / Storage / Memory
- `CoreAdapter` — 转发至核心能力层
- `PlatformAdapter` — 转发至平台服务层（预留）
- `AppAdapter` — 转发至应用接入层（预留）

### 3.3 边界红线（来自 `architecture-boundary.md`）

- 管理平面**禁止**包含业务逻辑。
- 必须**通过 HTTP 调用**各层，不得跨层直接访问数据库。
- 数据源必须**单一**（经 HTTP）。

---

## 四、Layer 0 基础设施层（infra:8001）

### 4.1 七大子模块

| 子模块 | API 前缀 | 实现状态 |
|--------|----------|----------|
| 节点管理 | `/api/infra/nodes` | GET 已实现；drain/restart/labels 待实现 |
| 模型管理 | `/api/infra/models` | CRUD + 测试 + 本地扫描 已实现 |
| 服务管理 | `/api/infra/services` | CRUD + scale/restart/logs 已实现 |
| 算力调度 | `/api/infra/quotas`, `/scheduling`, `/queue`, `/autoscaling` | API 已定义 |
| 存储 | `/api/infra/storage/{vector,models,pvc}` | GET 已实现；写操作待实现 |
| 网络 | `/api/infra/network/{services,ingress,policies}` | API 已定义 |
| 监控审计 | `/api/infra/monitoring`, `/alerting`, `/audit` | 已实现 |

### 4.2 关键设计

- **模型三来源**：config（内置只读）/ Ollama 本地（动态扫描）/ 用户添加（`data/models.json`）。
- **状态流转**：未配置 → 已配置 → 已启用（测试失败 → 不可用）。
- **存储三类**：向量存储（HNSW/IVF/FLAT，cosine/euclidean/dot_product）/ 模型存储（上传/下载/缓存）/ PVC（创建/扩容/快照/恢复）。
- **告警分级**：critical / warning / info；通知渠道：email / dingtalk / webhook / slack。
- **GPU 调度**：配额（按团队/用户）+ 策略（优先级/亲和性）+ 队列任务 + HPA 自动扩缩。

### 4.3 已知缺口（As-Is）

- 驱动管理写操作、PVC 写操作待实现。
- 前端详情页、驱动管理、部署服务向导待实现。
- **本机探测仍存在**（设计上应改为经 infra 层，当前管理平面仍直接探测本机）。

---

## 五、Layer 1 核心能力层（core:8002）

### 5.1 Engine vs Workspace 边界（核心设计）

| 维度 | Engine 引擎 | Workspace 工作区 |
|------|------------|-----------------|
| 路径 | `aiplat-core/core/engine/` | `~/.aiplat/` |
| 可变性 | 不可变，随发行版分发 | 可编辑，用户级 |
| 内容 | Harness + 内置 Agents/Skills/Adapters | 用户 Agents/Skills/Memory/Knowledge |
| 版本管理 | 不支持 | 支持（workspace 专属） |

这一边界是系统"开箱即用 + 可扩展"平衡的关键：引擎保证稳定性，工作区保证灵活性。

### 5.2 六大子模块

#### Harness 执行引擎

- 参数：`max_iterations=25`, `timeout=300s`, `retry=3`
- Hook 管理：pre/post 钩子，按优先级执行
- **6 种协调模式**：Pipeline / FanOutFanIn / Supervisor / ExpertPool / ProducerReviewer / Hierarchical
- Feedback Loops：LOCAL / PUSH / PROD 三类反馈回路
- API：`/api/core/harness/{status,config,logs,hooks,coordinators,feedback/config}`

#### Agents 智能体

- **6 种类型**：ReAct / RAG / Plan / Conversational / Tool-Using / Multi-Agent
- 生命周期：CRUD + start/stop/execute/history
- Workspace 变体：`/api/core/workspace/agents/*`（支持版本管理）
- 技能/工具绑定 API

#### Skills 技能

- 5 种类型：generation / analysis / transformation / retrieval / execution
- 2026 新特性：
  - **触发条件**（trigger_conditions）
  - **演化机制**：CAPTURED → FIX → DERIVED → stable
  - **血缘追踪**（lineage）
  - Agent Skill 目录结构：`SKILL.md` + `handler.py` + `scripts/` + `references/`
- 版本管理 + 回滚

#### Memory 记忆

- 三类：短期（内存）/ 长期（向量 DB）/ 会话（内存 + 持久化）
- API：sessions CRUD + stats/search/cleanup/export/import
- 自动清理配置

#### Knowledge 知识库

- Collection CRUD + reindex
- 文档：upload/list/delete
- 检索测试：`/search`
- 配置：`embedding_model`, `dimension=1536`, `chunk_size`, `chunk_overlap=50`, `similarity_threshold=0.75`

#### Adapters 适配器

- 6 提供商：OpenAI / Anthropic / AzureOpenAI / Ollama / vLLM / Custom
- CRUD + test + enable/disable
- 限流：rpm / tpm / daily_quota
- 重试：指数退避
- 调用监控统计

### 5.3 前端实现缺口

- 知识库检索测试 UI — 🔜 待实现
- 适配器管理 UI — 🔜 待实现

---

## 六、Layer 2 / Layer 3（预留）

### Layer 2 平台服务层（platform:8003）

- PlatformManager 接口已定义
- 组件：API / Auth / Tenants / Billing / Gateway / Registry
- 配置项：`api.rate_limit.requests=1000`, `auth.token.expiration=3600`, `tenant.quota.storage=10GB`

### Layer 3 应用接入层（app:8004）

- AppManager 接口已定义
- 组件：Gateway / Channels / Runtime / Sessions / CLI / Workbench
- 配置项：`gateway.max_connections=1000`, `session.timeout=1800`
- 9 条预定义告警规则

---

## 七、技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + Tailwind + Framer Motion + Lucide + Vite |
| 后端 | FastAPI + uvicorn + httpx.AsyncClient |
| 语言 | Python 3.10+ / TypeScript |
| 数据库 | PostgreSQL + Redis |
| 向量 | Milvus（HNSW/IVF/FLAT） |
| 消息 | RabbitMQ |
| 监控 | Prometheus + Grafana |
| 追踪 | OpenTelemetry（Phase 0.2） |
| 部署 | K8s（GPU 节点 / Ingress / NetworkPolicy / PVC） |
| 配置 | YAML 驱动 |

---

## 八、运维与诊断特性

### 8.1 Doctor 一键自检

`GET /api/diagnostics/doctor` 聚合：

- 健康状态
- Adapter 连通性
- autosmoke 环境检查
- strong-gate 状态
- 可执行建议（带 `actions` 白名单 + `input_schema` UI 渲染）

### 8.2 Onboarding 向导

配置 LLM 适配器 → 全链路健康检查 → E2E smoke → 默认 LLM 路由（审批制）→ 租户/策略初始化 → `AIPLAT_SECRET_KEY` 加密 → strong-gate 开关 → autosmoke 配置中心 → 明文密钥迁移。

### 8.3 强门禁（strong-gate）

`approval_required_tools=['*']` — 所有工具调用需审批，生产环境安全护栏。

### 8.4 Runs 评估与 Learning Artifacts

- 自动评估：url / project_id / expected_tags
- 三种工作流：QA-only / QA+Gate / Investigate
- Learning Artifacts 浏览：按 target_type / run_id / trace_id / kind / status 过滤
- 全局/项目策略编辑

### 8.5 全链路追踪

`trace_id` / `span_id` 贯穿四层，已实现（Phase 0.2）。

### 8.6 E2E Smoke 与 autosmoke

自动化冒烟测试，配置中心化管理。

---

## 九、As-Is vs To-Be 实现状态矩阵

| 能力 | To-Be 目标 | As-Is 现状 | 差距 |
|------|-----------|-----------|------|
| RBAC | 完整权限体系 | `policy_gate.py` + `permissions.yaml` | ✅ 完成 |
| 核心诊断 | 24 类检查 | 已接线 | ✅ 完成 |
| OpenTelemetry | 全链路 | Phase 0.2 已接线 | ✅ 完成 |
| trace_id/span_id | 全链路追踪 | 已实现 | ✅ 完成 |
| 配置 | YAML 驱动 | 已迁移 | ✅ 完成 |
| AlertEngine | 持久化 + 时序 | 内存原型 | ⚠️ 待升级 |
| 时序存储 | 入库 | 未入 | ❌ 缺失 |
| infra 探测 | 经 infra 层 | 本机探测仍存在 | ⚠️ 待迁移 |
| config 下发 | 全层 | 未完成 | ⚠️ 进行中 |
| UI trace 关联 | 可视化 | 未完成 | ❌ 待实现 |
| 知识库检索 UI | 前端 | 🔜 待实现 | ❌ 待实现 |
| 适配器管理 UI | 前端 | 🔜 待实现 | ❌ 待实现 |

---

## 十、优势分析

1. **架构边界清晰**：管理平面与业务平面严格分离，避免"大泥球"。HTTP 解耦使各层可独立演进。
2. **Engine/Workspace 分离**：内置能力不可变保证稳定，用户工作区可编辑保证灵活，兼顾开箱即用与可扩展。
3. **文档诚实**：明确区分 To-Be 与 As-Is，`IMPLEMENTATION_STATUS.md` 不美化现实，利于工程决策。
4. **运维闭环完整**：Doctor 自检 → Onboarding → autosmoke → strong-gate → Runs 评估 → Learning Artifacts，形成从部署到学习的闭环。
5. **全链路追踪**：trace_id/span_id 贯穿四层，生产可观测性基础已具备。
6. **配置驱动**：YAML 化，避免硬编码分支。
7. **Skill 演化机制**：CAPTURED/FIX/DERIVED/stable 四态演化 + 血缘追踪，体现对"技能生命周期"的深入思考。

---

## 十一、风险与缺口

### 高优先级

1. **AlertEngine 仍为内存原型** — 重启丢失告警状态，生产环境不可接受。需引入持久化 + 时序存储。
2. **infra 本机探测仍存在** — 违反"管理平面不直接探测"边界，单点故障时管理平面会误判。应改为经 infra 层代理。
3. **时序存储未入** — 监控历史数据无落盘，无法做长周期趋势分析。

### 中优先级

4. **config 下发未完成** — 部分层配置仍需手动同步。
5. **UI trace 关联未完成** — 后端有 trace_id，前端未可视化，排查体验打折。
6. **知识库检索/适配器管理 UI 待实现** — 核心能力层两个关键前端缺口。

### 架构性

7. **Layer 2/3 预留** — 平台服务与应用接入层尚未实现，多租户/计费/应用网关能力空缺，规模化时需补齐。
8. **6 协调模式 + 3 反馈回路** — 设计丰富，但文档未明确各模式的适用场景与性能特征，需补充决策指南。

---

## 十二、建议的下一步

| 优先级 | 行动 | 理由 |
|--------|------|------|
| P0 | AlertEngine 持久化 + 时序存储接入 | 生产可用性前提 |
| P0 | infra 探测迁移至 infra 层 | 架构边界一致性 |
| P1 | 知识库检索 UI + 适配器管理 UI | 核心层前端闭环 |
| P1 | UI trace 关联可视化 | 排障体验 |
| P1 | config 下发全层完成 | 配置一致性 |
| P2 | Layer 2 平台服务层原型 | 多租户/计费前置 |
| P2 | 6 协调模式决策指南文档 | 降低使用门槛 |
| P2 | Skill 演化机制效果验证 | 确认设计落地价值 |

---

## 十三、一句话总结

> 这是一个**架构设计成熟、边界纪律严格、文档诚实**的 AI 平台管理系统：四层解耦 + 管理平面横切 + Engine/Workspace 分离的设计思路清晰，运维闭环（Doctor/Onboarding/autosmoke/Runs/Learning）完整；当前主要矛盾在于**部分基础设施层探测未按边界迁移、告警与时序存储尚为原型、核心层两个前端 UI 缺口**，这些都是工程收尾问题，而非架构性问题。

---

*报告生成自 28 份项目文档的完整阅读。文档来源：`/Users/apple/workdata/person/zy/aiPlatform/aiPlat-management/docs/` + 根目录 `README.md` / `CLAUDE.md` / `QUICKSTART.md`。*
