# aiPlat 管理画面 操作手册

> 版本 1.0 | 最后更新 2026-07 | 适用于 aiPlat v12

本文档详细说明 aiPlat 管理画面（Management Dashboard）的所有功能模块、操作方法和典型工作流。

---

## 目录

- [1. 系统概述](#1-系统概述)
- [2. 五大角色与权限体系](#2-五大角色与权限体系)
- [3. 侧边栏导航](#3-侧边栏导航)
- [4. 系统入口页面](#4-系统入口页面)
- [5. 基础设施](#5-基础设施)
- [6. AI 能力 — Engine 管理](#6-ai-能力--engine-管理)
- [7. AI 能力 — 应用市场](#7-ai-能力--应用市场)
- [8. 平台管理](#8-平台管理)
- [9. 平台管理 — 应用接入](#9-平台管理--应用接入)
- [10. 价值中心](#10-价值中心)
- [11. 诊断与修复](#11-诊断与修复)
- [12. 知识中心](#12-知识中心)
- [13. 审批中心](#13-审批中心)
- [14. 典型操作流程](#14-典型操作流程)
- [附录 A：支持模型类型](#附录-a支持模型类型)
- [附录 B：常见问题](#附录-b常见问题)
---

## 1. 系统概述

aiPlat 管理画面是一个四层架构的 AI 中台管理界面，覆盖基础设施、AI 能力、平台服务和应用接入全栈管理。首页为**系统概览**仪表盘，左侧侧边栏按功能层级分组。右下角提供**角色切换器**用于不同身份视角切换。

**访问地址**：`http://localhost:5173`（开发模式）

---

## 2. 五大角色与权限体系

### 2.1 角色定义

| # | 角色 Key | 中文名 | 职责范围 | 侧边栏可见组 |
|---|---------|-------|---------|------------|
| 1 | `admin` | 管理员 | 全局配置、安全审计、系统运维 | 全部菜单组 + 独立菜单项 |
| 2 | `developer` | 开发者 | 模型、Agent、Skill、诊断 | infra, core, workspace, app, value, user, diagnostics |
| 3 | `business` | 业务负责人 | KPI、目标、价值看板 | value, user |
| 4 | `user` | 终端用户 | 提交任务、查看结果 | user, app |
| 5 | `approver` | 审批人 | 审批待办事项 | user |

### 2.2 角色切换

侧边栏底部的角色切换器允许你切换身份以验证不同角色的界面效果：

1. 点击底部当前角色名称
2. 弹出下拉菜单显示 5 个可选角色
3. 选择目标角色 → 页面自动刷新

> 开发环境使用 `localStorage` 模拟。生产环境从 JWT Token 解析角色，不可手动切换。

### 2.3 后端权限矩阵

以下路由级别权限在后端通过 `PolicyGate.check_route_access()` 强制校验：

| 路由前缀 | 允许角色 |
|---------|---------|
| `/system-overview` | admin |
| `/onboarding` | admin |
| `/platform` | admin |
| `/value-center/roles` | admin |
| `/value-center` | admin, business |
| `/value-center/kpis` | admin, business |
| `/value-center/goals` | admin, business |
| `/value-center/strategy` | admin, developer |
| `/value-center/training` | admin, developer |
| `/diagnostics` | admin, developer |
| `/infra` | admin, developer |
| `/core` | admin, developer |
| `/workspace` | admin, developer |
| `/workbench` | admin, developer, business, user |
| `/value-center/spec` | admin, developer, business, approver |
| `/app` | admin, user |
| `/approval-center` | admin, approver |

---

## 3. 侧边栏导航

侧边栏按功能分为 8 个分组，每组包含若干菜单项。左侧图标 + 文字标签，点击进入对应页面。

### 3.1 菜单分组总览

| 分组 | 标签 | 主要角色 | 菜单数 | 说明 |
|------|------|---------|:---:|------|
| overview | **总览** | 全部 | 4 | 系统概览、告警中心、系统图谱、文档系统 |
| knowledge | **知识中心** | admin, developer | 7 | 管线总览、原始资料、本体模型、向量知识库、LLM Wiki、RAG 检索、质量反馈 |
| ai | **AI 能力** | admin, developer | 20 | Agent/Skill/Tool/MCP/Workflow/Memory 管理 + 市场 + 模板 + 分析 |
| diagnostics | **诊断与修复** | admin, developer | 4 | 诊断中心、修复中心、FDE 工作台、LLM 审查 |
| infra | **基础设施** | admin | 9 | 节点、模型、微调、服务、算力、存储、网络、监控、LLM 路由 |
| platform | **平台管理** | admin | 13 | API 网关、认证鉴权、多租户、渠道、会话、构建、部署等 |
| value | **价值中心** | admin, developer, business | 6 | 价值看板、KPI 管理、目标追踪、角色管理、策略控制、训练监控 |
| approval | **审批中心** | admin, approver | 3 | 资产审批、运行时审批、审批记录 |

### 3.2 各分组详细菜单

#### 总览

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Activity | 系统概览 | `/system-overview` | 全局健康仪表盘 |
| Bell | 告警中心 | `/alerts` | 系统告警管理 |
| Share2 | 系统图谱 | `/system-graph` | 架构可视化 |
| BookOpen | 文档系统 | `/docs` | 在线文档浏览 |

#### 知识中心

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Share2 | 管线总览 | `/knowledge/overview` | 知识处理流水线概览 |
| FileText | 原始资料 | `/platform/kb?tab=vault` | 上传原始文档（PDF/Word 等） |
| Box | 本体模型 | `/infra/ontology` | 域本体管理（类/关系/状态机） |
| Database | 向量知识库 | `/platform/kb?tab=documents` | 文档切块与向量索引 |
| BookOpen | LLM Wiki | `/platform/kb?tab=wiki` | LLM 可读的结构化 Wiki |
| Search | RAG 检索 | `/platform/kb?tab=eval` | 检索质量评估 |
| TrendingUp | 质量反馈 | `/platform/kb?tab=quality` | 答案质量与反馈闭环 |

#### AI 能力

**Engine 管理（系统内置）**：

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Bot | Agent 管理 | `/core/agents` | 引擎内置 Agent 的 CRUD |
| Sparkles | Skill 管理 | `/core/skills` | 引擎内置 Skill 的注册 |
| Wrench | Tool 管理 | `/core/tools` | 工具注册与权限管理 |
| Plug | MCP 管理 | `/core/mcp` | MCP 服务连接管理 |
| GitBranch | Workflow 管理 | `/core/workflows` | 工作流模板管理 |
| Brain | Memory 管理 | `/core/memory` | 记忆系统配置 |

**配置与模板**：

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| FileText | 系统 Prompt | `/core/prompts` | 系统级提示词模板 |
| FileText | 提示词模板 | `/prompts/app` | 应用级提示词管理 |
| PenTool | 变量管理 | `/core/variables` | Prompt 变量 |
| Key | 凭证管理 | `/core/credentials` | API Key 等凭证 |

**应用市场（用户工作区）**：

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Bot | Agent 市场 | `/workspace/agents` | 用户自定义 Agent |
| Sparkles | Skill 市场 | `/workspace/skills` | 用户自定义 Skill |
| Wrench | Tool 市场 | `/workspace/tools` | 用户自定义 Tool |
| Plug | MCP 市场 | `/workspace/mcp` | 用户 MCP 连接 |
| Users | 团队组装 | `/workspace/teams` | 多 Agent 团队编排 |
| ShoppingBag | 商城 | `/workspace/marketplace` | 共享资产市场 |
| Package | 包管理 | `/core/skill-packs` | Skill 打包分发 |
| Box | 插件管理 | `/plugins` | 插件扩展 |

**分析**：

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| BarChart3 | Agent 能力 | `/core/agent-insight` | Agent 能力评估 |
| BarChart3 | Agent 评估 | `/diagnostics/eval` | Agent 质量评分 |

#### 诊断与修复

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Activity | 诊断中心 | `/diagnostics` | 综合诊断入口 |
| Wrench | 修复中心 | `/diagnostics/repairs` | 一键修复问题 |
| Wrench | FDE 工作台 | `/diagnostics/fde` | FDE 交付操作 |
| Search | LLM 审查 | `/diagnostics/llm-review` | LLM 输出审查 |

#### 基础设施

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Server | 节点管理 | `/infra/nodes` | 计算节点管理 |
| Cpu | 模型管理 | `/infra/models` | LLM 模型注册 |
| Wrench | 模型微调 | `/infra/finetune` | 模型训练任务 |
| Database | 服务管理 | `/infra/services` | 基础服务管理 |
| HardDrive | 算力调度 | `/infra/scheduler` | GPU 资源调度 |
| Database | 存储管理 | `/infra/storage` | 数据存储管理 |
| Network | 网络管理 | `/infra/network` | 网络配置 |
| Monitor | 监控告警 | `/infra/monitoring` | 资源监控 |
| Monitor | LLM 路由监控 | `/infra/llm-stats` | LLM 路由统计 |

#### 平台管理

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Network | API 网关 | `/platform/gateway` | 网关配置 |
| Shield | 认证鉴权 | `/platform/auth` | 身份认证与权限 |
| Users | 多租户 | `/platform/tenant` | 租户管理 |
| MessageSquare | 渠道管理 | `/app/channels` | 通信渠道 |
| MessageSquare | 会话管理 | `/app/sessions` | 用户会话 |
| FolderOpen | 项目构建 | `/app/builder` | 项目构建 |
| PenTool | 图表工作室 | `/app/diagrams` | 图表工具 |
| Rocket | 已部署应用 | `/app/apps` | 应用列表 |
| Rocket | 版本管理 | `/releases` | 版本发布 |
| Settings | 初始化向导 | `/onboarding` | 系统初始化 |
| Sparkles | App Studio | `/studio` | 应用工作室 |
| Shield | 渗透测试 | `/pentest` | 安全测试 |
| Monitor | 终端工作台 | `/workbench` | 用户工作台 |

#### 价值中心

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| BarChart3 | 价值看板 | `/value-center` | ROI 价值总览 |
| Target | KPI 管理 | `/value-center/kpis` | KPI 指标 |
| Flag | 目标追踪 | `/value-center/goals` | 目标进度 |
| Users | 角色管理 | `/value-center/roles` | Agent 角色配置 |
| Sliders | 策略控制 | `/value-center/strategy` | 路由策略 |
| GitBranch | 训练监控 | `/value-center/training` | SFT/RL 训练 |

#### 审批中心

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Package | 资产审批 | `/approval` | Skill/Agent 发布审批 |
| Shield | 运行时审批 | `/core/approvals` | 高危操作审批 |
| FileText | 审批记录 | `/approval/history` | 审批历史

---

## 4. 系统入口页面

### 4.1 系统概览（`/system-overview`）

**可见角色**：admin

**功能**：四层架构运行状态的全局仪表盘。展示：

- **四层健康卡片**：基础设施层 (Infra)、AI 中台 (Core)、平台服务 (Platform)、应用接入 (App) —— 每层显示存活状态和关键指标
- **模型统计**：可用模型数 (chat/embed/rerank/audio/ocr) 及 provider 列表
- **LLM 调用统计 (24h)**：请求次数、成功率、平均延迟、Token 消耗
- **服务状态**：5 个核心服务 (management/infra/core/platform/app) 的在线状态
- **存储状态**：DB 连接、向量数据库、缓存状态
- **Agent 统计**：总计 Agent 数、引擎内置 vs 工作区、按类型分布
- **Skill/Tool/MCP**：激活数量统计
- **诊断趋势**：最近 30 次诊断结果的变化趋势图
- **Pipeline 活跃度**：当前活跃流水线、已完成总数

**操作**：
- 点击「刷新」按钮手动拉取最新指标
- 点击「诊断 35s ago」链接跳转到诊断中心查看详细报告
- 点击各层健康卡片跳转到对应管理页面

### 4.2 系统图谱（`/system-graph`）

**可见角色**：admin

**功能**：以交互式 Canvas 展示 aiPlat 四层架构的模块依赖关系图。

**操作**：
- 拖拽平移画布、滚轮缩放
- 点击节点查看模块详情（文件数、行数、依赖关系）
- 搜索框输入模块名过滤高亮
- 切换到「图对话」模式，用自然语言查询架构信息

### 4.3 告警中心（`/alerts`）

**可见角色**：admin

**功能**：系统告警的集中管理。

**操作**：
- 查看告警列表（级别、时间、来源、详情）
- 确认 (Acknowledge) 已知告警
- 关闭 (Close) 已解决的告警

### 4.4 版本管理（`/releases`）

**可见角色**：admin

**功能**：系统版本发布记录。

**操作**：
- 浏览版本发布历史（版本号、发布日期、变更日志）
- 查看每个版本的详细 Release Notes

### 4.5 初始化向导（`/onboarding`）

**可见角色**：admin

**功能**：新系统安装后的初始化引导流程。

**操作**：
- 按步骤完成：模型配置 → 租户创建 → 用户创建 → 知识库初始化 → 完成

---

## 5. 基础设施

### 5.1 节点管理（`/infra/nodes`）

**可见角色**：admin, developer

**功能**：管理计算节点（GPU/CPU 服务器）。

**操作**：
- **添加节点**：填写节点名称、IP、驱动类型 (Docker/K8s/SSH)、规格
- **查看详情**：点击节点查看 GPU 型号、内存、磁盘、运行中的任务
- **配置变更**：修改节点标签、资源限制、调度策略
- **移除节点**：将节点从调度池中移除

### 5.2 模型管理（`/infra/models`）

**可见角色**：admin, developer

**功能**：系统所有 AI 模型的统一目录。

**模型来源**：
- **内置模型**：代码中通过环境变量自动注册
- **本地模型**：Ollama / LM Studio / oMLX / vLLM 自动扫描
- **自定义模型**：手动添加的 OpenAI 兼容 API

**操作**：
- **查看模型列表**：名称、类型 (chat/embedding/reranker/audio/ocr)、provider、状态
- **启用/禁用**：切换模型是否参与调度
- **测试连通性**：发送测试请求验证模型可用性
- **添加自定义模型**：填写名称、API 地址、类型、API Key
- **查看详情**：模型参数、健康检查历史、调用统计

### 5.3 模型微调（`/infra/finetune`）

**可见角色**：admin, developer

**功能**：模型训练与微调的完整工作流，6 个 Tab 页面。

| Tab | 功能 | 操作 |
|------|------|------|
| 数据集 | 管理训练/验证/测试数据集 | 上传 CSV/JSONL → 预览 → 标记为训练集 |
| 微调 | 启动 LoRA/QLoRA 微调任务 | 选数据集 + 基座模型 + 参数 → 提交 |
| RL 训练 | 强化学习训练 (PPO/DPO) | 奖励模型 + 策略模型 + 环境配置 |
| 蒸馏 | 大模型 → 小模型蒸馏 | Teacher 模型 + Student 模型 + KL 散度参数 |
| 从零训练 | 从零训练小模型 (gpt2/pythia) | 数据集 + 架构 + 训练步数 |
| 模型注册表 | 查看所有训练产物 | 浏览 → 部署为推理服务 → 下载 |

### 5.4 服务管理（`/infra/services`）

**可见角色**：admin, developer

**功能**：推理服务的管理与部署。

**操作**：
- **部署新服务**：选择模型 → 设置实例数 → 资源配置 → 启动
- **扩缩容**：调整实例数或启用弹性伸缩
- **查看日志**：服务运行日志和错误信息
- **停止/重启**：管理服务生命周期

### 5.5 算力调度（`/infra/scheduler`）

**可见角色**：admin, developer

**功能**：GPU/CPU 资源的配额与调度策略。

**操作**：
- **设置资源配额**：团队/项目维度的 GPU 小时数上限
- **弹性伸缩策略**：最小/最大实例数、触发指标 (GPU 使用率/队列长度)
- **查看任务队列**：等待中/运行中/已完成的任务分布
- **优先级调整**：高优任务可抢占低优任务的资源

### 5.6 存储管理（`/infra/storage`）

**可见角色**：admin, developer

**功能**：持久化存储和向量数据库管理。

**操作**：
- **查看存储卷**：名称、类型 (本地/NFS/云存储)、容量、使用率
- **向量集合管理**：创建/删除向量集合、查看维度与索引信息
- **PVC 管理**：K8s 持久卷申请的查看与扩容

### 5.7 网络管理（`/infra/network`）

**可见角色**：admin, developer

**功能**：服务间网络配置。

**操作**：
- **端点管理**：查看各服务的内部端点地址和端口映射
- **Ingress 配置**：外部访问的路由规则
- **网络策略**：服务间访问控制规则

### 5.8 监控告警（`/infra/monitoring`）

**可见角色**：admin, developer

**功能**：基础设施层面的指标监控。

**操作**：
- **GPU 指标**：GPU 使用率、显存、温度
- **节点指标**：CPU、内存、磁盘、网络 IO
- **集群指标**：总节点数、在线率、任务分布
- **告警规则**：创建/编辑阈值告警规则（如 GPU 使用率 > 90% → 通知）

### 5.9 LLM 路由监控（`/infra/llm-stats`）

**可见角色**：admin, developer

**功能**：LLM 请求的路由决策可视化。

**操作**：
- 查看各 providers 的流量分布
- 查看路由决策历史（哪个请求被路由到哪个模型）
- 分析延迟和成功率按 provider 分组

---

## 6. AI 能力 — Engine 管理

### 6.1 Agent 管理（`/core/agents`）

**可见角色**：admin, developer

**功能**：管理 engine（内置）和 workspace（用户）两个来源的 Agent。

**引擎 Agent**：随 core 版本发布，只读/受控更新。标识 `protected=true`。

**工作区 Agent**：用户创建，可完整 CRUD。

**操作**：
- **新建 Agent**：填写 AGENT.md（名称、类型、system_prompt、绑定 Skill/Tool）
- **编辑**：修改 AGENT.md 属性（工作区 Agent）
- **启用/禁用**：切换 Agent 是否可被调度
- **测试执行**：输入任务描述 → 实时观察 Agent 的执行过程
- **对话**：打开对话窗口与 Agent 直接交互

### 6.2 Skill 管理（`/core/skills`）

**可见角色**：admin, developer

**功能**：管理 engine 和 workspace 的 Skill。

**Skill 状态流转**：`draft → active → deprecated → retired`

**操作**：
- **新建 Skill**：填写 SKILL.md（名称、类型、SOP、输入/输出 schema）
- **编辑**：修改 SKILL.md
- **执行**：输入参数 → 查看执行结果
- **灰度发布**：设置 Canary 比例 → A/B 测试 → 全量发布
- **回滚**：选择历史版本 → 一键回滚

### 6.3 Tool 管理（`/core/tools`）

**可见角色**：admin, developer

**功能**：查看系统注册的所有工具。

> 工具通过代码注册（`BaseTool`），管理界面当前为只读。

**操作**：
- 浏览工具列表（名称、描述、所属模块）
- 查看工具输入 schema
- 手动执行工具并查看返回结果

### 6.4 MCP 管理（`/core/mcp`）

**可见角色**：admin, developer

**功能**：管理 MCP (Model Context Protocol) 服务器。

**操作**：
- **添加 MCP Server**：填写名称、连接方式 (SSE/Stdio)、配置
- **启用/禁用**：管理 MCP Server 生命周期
- **查看工具**：列出该 MCP Server 暴露的所有工具
- **测试连接**：验证 MCP Server 连通性

### 6.5 Memory 管理（`/core/memory`）

**可见角色**：admin, developer

**功能**：Agent 的四层记忆系统管理。

| 记忆层 | 存储 | 管理操作 |
|--------|------|---------|
| Working (热) | deque 滑动窗口 | 查看当前上下文内容 |
| Episodic (温) | 规则摘要 | 浏览会话摘要、交互事件 |
| Semantic (冷) | SQLite 长期记忆表 | 搜索/创建/编辑/删除长期记忆条目 |
| Task Skills (外挂) | JSON 文件 | 查看自动晶体化的 Task Skill |

**操作**：
- **按会话浏览**：选择 session_id → 查看该会话的全部记忆
- **搜索**：全文搜索 (FTS5) 长期记忆
- **创建记忆**：手动添加长期记忆条目（标签、内容、过期时间）
- **导入/导出**：批量迁移记忆数据

### 6.6 系统 Prompt（`/core/prompts`）

**可见角色**：admin, developer

**功能**：管理全局 Prompt 模板。

**操作**：
- **创建模板**：设置模板 ID、分类 (skills/routing/coding/general)、正文、变量占位符
- **编辑模板**：修改模板内容
- **评估**：运行 Prompt 评估（对相同输入对比模板效果）
- **优化**：AI 自动优化 Prompt 措辞和结构

### 6.7 变量管理（`/core/variables`）

**可见角色**：admin, developer

**功能**：运行时变量的集中管理。

**操作**：
- **添加变量**：名称、默认值、是否为密钥
- **编辑变量**：修改变量值或默认值
- **按 scope 筛选**：engine / workspace 维度

### 6.8 凭证管理（`/core/credentials`）

**可见角色**：admin, developer

**功能**：API Key、Token 等敏感凭证的安全存储。

**操作**：
- **添加凭证**：名称、类型 (API Key / Token / Password)、值 → 加密存储
- **查看**：脱敏显示（前 4 位 + `***`）
- **删除**：吊销凭证

### 6.9 Agent 能力分析（`/core/agent-insight`）

**可见角色**：admin, developer

**功能**：Agent 能力的可视化分析和度量。

**操作**：
- 查看每个 Agent 的能力评分（任务完成率、工具调用质量、步骤效率）
- 点击 Agent 进入详情页查看指标趋势图
- 对比多个 Agent 的能力雷达图

---

## 7. AI 能力 — 应用市场

### 7.1 Agent 市场（`/workspace/agents`）

**可见角色**：admin, developer

**功能**：用户工作区的 Agent 管理。与 Core Agent 管理的区别在于：这里是用户创建的应用级 Agent，允许完整 CRUD。

### 7.2 Skill 市场（`/workspace/skills`）

**可见角色**：admin, developer

**功能**：用户工作区 Skill 管理。支持自定义 Skill 的创建、lint 检查、执行。

### 7.3 Tool 市场（`/workspace/tools`）

**可见角色**：admin, developer

**功能**：用户工作区 Tool 注册和管理。

### 7.4 Workflow 管理（`/core/workflows`）

**可见角色**：admin, developer

**功能**：可视化 Pipeline 编排。

**操作**：
- **新建 Workflow**：拖拽节点 → 连线 → 配置阶段参数 → 保存
- **编辑**：打开画布编辑器修改
- **运行**：启动 Workflow → 实时查看每个阶段的执行状态、日志

### 7.5 商城（`/workspace/marketplace`）

**可见角色**：admin, developer

**功能**：6 个 Tab 的一站式安装市场。

| Tab | 内容 |
|------|------|
| Skills | 从 agentskills.io 或其他仓库安装 Skill |
| Agents | 安装预配置的 Agent |
| Tools | 安装工具包 |
| MCP | 安装 MCP Server 配置 |
| Workflows | 安装预建 Pipeline 模板 |
| Published | 查看已发布的自有资产 |

**操作**：
- 输入 Skill URL → 一键安装到 workspace
- 查看已安装列表 → 卸载/更新

### 7.6 包管理（`/core/skill-packs`）

**可见角色**：admin, developer

**功能**：Skill 包的分发管理。将多个 Skill 打包为一个 Skill Pack，方便分发。

### 7.7 团队组装（`/workspace/teams`）

**可见角色**：admin, developer

**功能**：可视化组装 Agent 团队。

**操作**：
- 拖拽 Agent 到团队面板
- 配置角色、任务分工
- 设定通信规则和依赖关系
- 保存为团队模板

### 7.8 插件管理（`/plugins`）

**可见角色**：admin, developer

**功能**：管理第三方插件。

**操作**：
- 查看已安装插件列表
- 启用/禁用插件
- 配置插件参数

---

## 8. 平台管理

### 8.1 知识库管理（`/platform/kb`）

**可见角色**：admin

**功能**：企业知识库的全生命周期管理。这是一个复合页面，包含：

- **DocumentGrid**：文档列表浏览（树形目录 + 表格视图）
- **文档上传**：拖拽上传 PDF/DOCX/PPTX/HTML/MD/TXT
- **ChatPanel**：知识库问答对话（MaterialsChat）
- **WikiGraph**：知识图谱交互式可视化
- **本体图**：域本体的类-关系-实例图
- **VaultBrowser**：知识库文件系统浏览器
- **Wiki 健康仪表盘**：死链/孤立页面/过期文档的监控

### 8.2 Materials Chat（`/platform/kb/chat/:sessionId`）

**可见角色**：admin

**功能**：知识库深度问答。支持视频时间轴引用、多检索路径标记（蓝色=直接检索、紫色=HyDE）、CRAG 三级回退。

### 8.3 知识中心 — 本体模型（`/infra/ontology`）

**可见角色**：admin, developer

**功能**：域本体 (Domain Ontology) 的完整管理。

**操作**：
- **创建域**：定义 T-Box（类、关系、属性）→ YAML 配置
- **类图编辑**：添加/修改类定义、字段约束、状态机
- **关系定义**：添加对象属性和数据属性
- **引擎运行**：触发本体引擎管线（分类→提取→验证→建图→合成）
- **状态机模拟**：输入场景 → 观察状态转换
- **场景推演**：多方案对比（基线 vs 方案 A vs 方案 B）
- **图快照**：创建/查看/回滚图版本
- **图谱可视化**：交互式查看实体关系图

### 8.4 API 网关（`/platform/gateway`）

**可见角色**：admin

**功能**：管理 API 路由、限流策略和设备配对。

**操作**：
- **路由管理**：查看/添加/修改 API 路由（路径 → 后端服务映射）
- **限流配置**：设置每分钟/每 IP 请求上限
- **令牌管理**：生成/吊销设备配对令牌

### 8.5 认证鉴权（`/platform/auth`）

**可见角色**：admin

**功能**：用户和权限管理。

**操作**：
- **用户 CRUD**：创建/编辑/删除用户
- **角色分配**：为用户分配一个或多个角色
- **锁定/解锁**：停用或恢复用户账号
- **查看权限**：每个用户的已授权路由列表

### 8.6 多租户（`/platform/tenant`）

**可见角色**：admin

**功能**：多租户隔离管理。

**操作**：
- **创建租户**：名称、命名空间、资源配额
- **暂停/恢复**：临时冻结或恢复租户的所有操作
- **查看详情**：租户下的用户数、知识库集合数、API 消费量

---

## 9. 平台管理 — 应用接入

### 9.1 渠道管理（`/app/channels`）

**可见角色**：admin, user

**功能**：企业消息渠道配置。

**支持的渠道**：
- 飞书（Webhook）
- 企业微信（Webhook）
- Slack（Bot Token）

**操作**：
- **添加渠道**：选择渠道类型 → 填写 Webhook URL / Token → 启用
- **测试连通性**：发送测试消息
- **禁用/启用**：管理渠道状态

### 9.2 会话管理（`/app/sessions`）

**可见角色**：admin, user

**功能**：应用会话的监控与管理。

**操作**：
- 查看活跃会话列表（用户、创建时间、消息数）
- 查看会话详情（消息历史、使用的 Agent、工具调用记录）
- 强制结束异常会话

### 9.3 项目构建（`/app/builder`）

**可见角色**：admin, user

**功能**：Pipeline 项目从创建到部署的完整生命周期。

**操作流程**：
1. **创建项目**：填写项目名称、描述
2. **团队配置**：选择参与项目的 Agent（PM/Architect/Programmer/QA）
3. **定义 Pipeline 阶段**：设置各阶段的执行顺序、HITL 审批点
4. **启动 Pipeline**：触发执行 → 监控每个阶段的状态
5. **查看产出物**：checkpoint 快照、代码产物、测试报告

### 9.4 图表工作室（`/app/diagrams`）

**可见角色**：admin, user

**功能**：图表创建与管理。

**操作**：
- 创建流程图、架构图、时序图
- 编辑现有图表
- 导出为 PNG/SVG

### 9.5 App Studio（`/studio`）

**可见角色**：admin, user

**功能**：对话式应用构建器。通过与 PM Agent 多轮对话，自动完成需求分析到部署的全流程。

**操作流程**：
1. 输入应用目标 → PM Agent 提问澄清需求
2. PM 生成 PRD 草案 → 用户确认或修改
3. 自动组建开发团队 → 启动 Pipeline
4. 开发者 (Programmer) 生成代码 → QA 执行测试
5. 部署到 App Gallery

### 9.6 已部署应用（`/app/apps`）

**可见角色**：admin, user

**功能**：管理已部署的应用。

**操作**：
- 查看已部署应用列表（名称、模式、状态、创建时间）
- 打开应用对话界面进行交互
- 查看应用详情（API 端点、使用统计）
- 停用/重新部署

---

## 10. 价值中心

### 10.1 价值看板（`/value-center`）

**可见角色**：admin, business

**功能**：五维业务价值总览。支持三视角切换：

| 视角 | 关注点 |
|------|--------|
| CEO 视角 | 战略对齐度、资源使用效率、整体进展 |
| CFO 视角 | 成本节省、ROI、Token 消费优化 |
| PM 视角 | 项目进度、质量指标、团队产出 |

### 10.2 KPI 管理（`/value-center/kpis`）

**可见角色**：admin, business

**功能**：企业关键绩效指标的定义与追踪。

**操作**：
- **定义 KPI**：名称、目标值、当前值、权重、关联项目
- **更新进度**：定期更新当前值
- **查看趋势**：KPI 随时间变化的折线图

### 10.3 目标追踪（`/value-center/goals`）

**可见角色**：admin, business

**功能**：将业务目标映射到 Agent 执行。

**操作**：
- **创建业务目标**：目标描述、期限、关键结果
- **关联 Agent**：指定负责执行的 Agent 团队
- **进度时间线**：查看目标完成度的甘特图
- **GoalAwareRouter 预测**：AI 预测目标达成概率和建议调整

### 10.4 角色管理（`/value-center/roles`）

**可见角色**：admin

**功能**：定义和配置系统的 Agent 角色（业务层面的角色，区别于权限角色）。

**操作**：
- 创建/编辑 Agent 角色（PM、Architect、Programmer、QA 等）
- 为每个角色绑定对应的 Agent、Skill 集合
- 管理角色状态（active/inactive）

### 10.5 策略控制（`/value-center/strategy`）

**可见角色**：admin, developer

**功能**：手动覆盖 GoalAwareRouter 的决策参数。

**操作**：
- 调整 Agent 模式（效率优先 / 质量优先 / 平衡）
- 修改路由权重
- 设置最大并发数

### 10.6 训练监控（`/value-center/training`）

**可见角色**：admin, developer

**功能**：自学习和 SFT 训练任务的进度与质量监控。

**操作**：
- 查看训练任务列表（状态、进度、损失曲线）
- 查看 AutoLearner SkillDraft 的生成和审批历史
- 监控 SFT 数据集的质量指标

---

### 终端工作台 (User Workbench)

**路由**：`/workbench`

**可见角色**：全部

**功能**：终端用户的核心操作界面，提供 FDE (Feedback-Driven Execution) 操作系统。

### 11.1 五大仪表板卡片

| 卡片 | 功能 |
|------|------|
| 决策 (Decisions) | 查看自动决策记录：Agent 在什么条件下做了什么选择 |
| 信号 (Signals) | FeedbackRadar 检测到的 5 类信号（风险/机会/异常/趋势/瓶颈） |
| 异常 (Anomalies) | 系统自动检测的异常事件 |
| 审批 (Approvals) | 待处理的人工审批请求（HITL） |
| 种子 Demo | 预置的演示数据，快速体验系统功能 |

### 11.2 Spec 管理

Spec 是 FDE 操作系统的核心产物——从碎石路（临时决策）升级为高速公路（可复用 Pipeline）。

**操作**：
- **查看 Spec 列表**：按状态分类（DRAFT / STABLE / DEPRECATED）
- **创建 Spec**：新建 Spec 草案
- **提升 (Promote)**：DRAFT → 提交审批 → approve → 注册到 SkillRegistry
- **Spec 详情**：三 Tab 视图（正文编辑 / 修订历史 / 版本对比）
- **复制**：基于现有 Spec 创建变体
- **Diff**：并排对比两个版本

### 11.3 操作区域

- **筛选**：按状态、标签、创建时间过滤
- **批量批准**：选中多个待审批项 → 一键批准
- **提交任务**：输入任务描述 → 提交到 Agent 团队执行

---

## 11. 诊断与修复

**路由**：`/diagnostics`

**可见角色**：admin, developer

诊断中心是系统的"体检中心"。点击某行可打开详细模态框查看具体违规和代码位置。

---

### 12.1 诊断总览（`/diagnostics`）

综合诊断报告，覆盖 25+ 检查类别。点击「一键诊断」运行完整诊断。

**主要检查类别**：

| 分类 | 说明 | 满分 |
|------|------|:---:|
| Core 运行时 | Agent 执行循环健康检查 | 100 |
| 代码架构 | 四层依赖方向、循环导入 | 100 |
| 跨语言 | 前端 fetch body 字段 vs 后端 data.get 字段名 | 100 |
| 领域耦合 | core 中是否硬编码业务概念 | 100 |
| 脆弱基类 | 深度继承链检测 | 100 |
| 能力图谱 | 能力健康度汇总 | 100 |
| Skill Lint | Skill 元数据规范检查 | 100 |
| Wiki 健康 | 死链/孤立页面/过期文档 | 100 |
| 链路追踪 | trace_id/span_id 完整度 | 100 |
| 上下文 | 压缩/注入/budget | 100 |
| 架构守卫 | 跨文件 grep 级架构检查 | — |
| 合规审计 | 策略执行合规性 | 100 |
| 冒烟测试 | E2E 全链路冒烟 | 100 |

**操作**：
- **快速诊断**：常见检查快速扫描
- **完整模式**：全部 25 类检查深度扫描
- **运行守卫**：仅运行架构守卫
- 点击每个分类旁边的「详情」展开具体违规项

### 12.2 修复中心（`/diagnostics/repairs`）

**功能**：展示所有可修复问题，支持一键自动修复。

**操作**：
- 浏览问题列表（分类、文件名、违规描述）
- 点击「自动修复」→ 系统自动生成修复补丁
- 点击「批量修复」→ 一键修复全部可自动修复项
- 修复后重新运行诊断验证

### 12.3 诊断工具箱（27 个工具）

| 工具 | 功能 |
|------|------|
| Doctor | 一键聚合诊断报告 |
| Workflows | 把评估/证据/门控串成流水线 |
| Context | Prompt/上下文组装诊断 |
| Capability→Policy | 从 skill capabilities 生成工具门禁策略 |
| Exec Backends | 执行后端健康检查 |
| Traces | 链路追踪与 spans 定位 |
| Graph Runs | 图执行 runs/checkpoints/恢复 |
| Links | 输入 ID 联动查询 |
| Repo | 仓库索引/全文搜索 |
| Code Intel | 代码架构/影响面/风险扫描 |
| Runs | run_id 维度的摘要与事件流 |
| Audit Logs | 关键操作审计日志 |
| Tenant Policies | 策略快照 |
| Policy Debug | 策略评估调试 (RBAC + Policy) |
| Syscalls | syscall_events 检索 |
| Change Control | 变更控制台 |
| E2E Smoke | 生产级全链路冒烟（自动清理） |
| Ops | 导出 (CSV) / DLQ / 配额用量 |
| Observability | LLM 调用/延迟/Token/错误率 |
| Run 对比 | 并排对比两次执行差异 |
| Model Playground | 同 Prompt 并发多模型对比 |
| Model Audit | LLM 指纹溯源与身份验证 |
| Safety | 对话危机检测与情感安全监控 |
| Eval Dashboard | 统一评估面板 |
| 全链路冒烟 | 生产级 E2E：创建→执行→审计→清理 |

---

### 12.4 Agent 评估（`/diagnostics/eval`）

**功能**：六维 Agent 质量评分。

**评分维度**：任务完成率、工具调用质量、步骤效率、错误恢复、安全边界、成本效率

**操作**：
- 查看 Agent 评分排行榜
- 点击 Agent 查看六维详情雷达图
- 创建评估集：定义评估任务和标准答案
- 运行评估：选择 Agent → 选择评估集 → 开始

---

## 12. 知识中心

知识中心是 aiPlat 的"大脑"——管理从原始文档到可检索知识的全流程。

### 10.1 管线总览（`/knowledge/overview`）

**可见角色**：admin, developer

**功能**：知识处理流水线的可视化概览。展示各阶段的处理状态和数据流入流出。

### 10.2 原始资料（`/platform/kb?tab=vault`）

**可见角色**：admin, developer

**功能**：上传和管理原始文档（PDF、Word、PPT、HTML 等）。支持批量上传、解析状态查看。

### 10.3 本体模型（`/infra/ontology`）

**可见角色**：admin, developer

**功能**：域本体（Domain Ontology）的完整管理。

常用操作：
- **创建域**：点击「创建领域本体」→ 填写标识和名称 → 或使用「🤖 智能生成」（输入行业关键词，AI 自动生成 YAML）
- **编辑域**：展开域卡片 → 修改类、关系、状态机定义
- **引擎运行**：触发本体引擎管线（分类→提取→验证→建图→合成）
- **状态监控**：查看每个域的通过率、实体数、Skill 绑定

### 10.4 向量知识库（`/platform/kb?tab=documents`）

**可见角色**：admin, developer

**功能**：文档切块与向量索引管理。查看文档切块列表、重建向量索引。

### 10.5 LLM Wiki（`/platform/kb?tab=wiki`）

**可见角色**：admin, developer

**功能**：由引擎自动生成的 LLM 可读 Wiki 页面。支持创建、编辑、健康检查、死链检测。

### 10.6 RAG 检索（`/platform/kb?tab=eval`）

**可见角色**：admin, developer

**功能**：RAG 检索质量评估。支持 Golden Query 评测、Recall@10 计算。

### 10.7 质量反馈（`/platform/kb?tab=quality`）

**可见角色**：admin, developer

**功能**：答案质量反馈闭环。用户反馈自动汇总到此处，可追踪每条反馈的处理状态。

---

## 13. 审批中心

### 14.1 资产审批（`/approval`）

**可见角色**：admin, approver

**功能**：Agent、Skill、Tool、MCP 等资产的发布审批。提交审批 → 审核 → 通过/驳回 → 发布。

### 14.2 运行时审批（`/core/approvals`）

**可见角色**：admin

**功能**：高危操作（如批量删除、配置变更）的运行时审批。PolicyGate 拦截后生成审批单。

### 14.3 审批记录（`/approval/history`）

**可见角色**：admin, approver

**功能**：查看所有审批历史记录，支持按状态、类型、时间过滤。

---

## 14. 典型操作流程

### 13.1 新建一个 Agent 并测试

```
1. 侧边栏 → Core 组 → Agent 管理 (/core/agents)
2. 点击「新建 Agent」
3. 填写：
   - name: my_agent
   - agent_type: ReAct
   - system_prompt: "你是帮助用户分析数据的助手..."
   - 绑定 Skills: [data_analysis]
   - 绑定 Tools: [database_query]
4. 保存
5. 在列表中找到刚创建的 Agent → 点击「测试」
6. 输入测试任务："分析上个月的销售数据"
7. 观察执行过程 → 查看结果
```

### 13.2 创建一个知识库并上传文档

```
1. 侧边栏 → Platform → 知识库管理 (/platform/kb)
2. 点击「新建集合」→ 输入集合名称
3. 拖拽 PDF/DOCX 文件到上传区域
4. 等待解析完成（DocumentParser 自动分块）
5. 在 DocumentGrid 中查看已上传文档
6. 打开 ChatPanel → 输入问题测试检索效果
```

### 13.3 运行一次完整 Pipeline

```
1. 侧边栏 → App → 项目构建 (/app/builder)
2. 点击「新建项目」
3. 配置团队（选择 PM + Architect + Programmer + QA Agent）
4. 配置 Pipeline 阶段：
   - Stage 1: pm_agent → PRD 生成
   - Stage 2: architect_agent → 架构设计 (HITL 审批 ✓)
   - Stage 3: programmer_agent → 代码生成
   - Stage 4: qa_agent → 测试执行
5. 点击「启动 Pipeline」
6. 在进度面板查看各阶段状态
7. 当 Stage 2 需要审批时 → 查看架构方案 → 批准/驳回
8. 全部完成后 → 下载代码产物
```

### 13.4 配置一个新模型

```
1. 侧边栏 → Infra → 模型管理 (/infra/models)
2. 点击「添加模型」
3. 填写：
   - 名称: DeepSeek-V3
   - 类型: chat
   - Provider: OpenAI Compatible
   - API 地址: https://api.deepseek.com/v1
   - API Key: ********
   - 模型标识: deepseek-chat
4. 点击「测试连通性」→ 等待结果
5. 如果成功 → 启用模型
6. 模型将自动出现在模型选择器中
```

### 13.5 使用诊断中心排查问题

```
1. 侧边栏 → 诊断中心 (/diagnostics)
2. 点击「完整模式」→ 等待诊断完成（约 1-2 分钟）
3. 查看得分低的分类 → 点击「详情」展开违规列表
4. 记下违规的文件路径和行号
5. 侧边栏 → 修复中心 → 查看可自动修复的问题
6. 可自动修复的 → 点击「批量修复」
7. 需手动修复的 → 在代码编辑器中修改
8. 修复后重新运行诊断验证
```

### 13.6 分配用户权限

```
1. 侧边栏 → Platform → 认证鉴权 (/platform/auth)
2. 在用户列表中找到目标用户
3. 点击「编辑」→ 选择角色（可多选，如 developer + approver）
4. 保存
5. 用户下次登录时将获得对应侧边栏菜单和 API 权限
```

### 13.7 将 Spec 提升为可复用 Skill

```
1. 侧边栏 → 工作台 (/workbench)
2. 在 Spec 列表中找到状态为 DRAFT 的目标 Spec
3. 点击「提升 (Promote)」
4. 状态变为 pending → 提交到审批队列
5. 切换到 approver 角色 → 查看待审批列表
6. 点击「批准」
7. Spec 自动注册到 SkillRegistry
8. 现在其他 Agent 可以绑定这个新 Skill
```

---

## 附录 A：支持模型类型

| 类型 | 能力 | 常见模型 |
|------|------|---------|
| chat | 文本对话/推理 | gpt-4o, claude-3.5-sonnet, deepseek-v3, qwen2.5, llama3.3 |
| embedding | 文本向量化 | text-embedding-3-small, bge-large-zh, all-MiniLM-L6 |
| reranker | 检索结果重排 | bge-reranker-v2-m3, cohere-rerank |
| audio | 语音转文字 | whisper-large-v3, faster-whisper |
| ocr | 图像文字识别 | tesseract-ocr, PaddleOCR |

## 附录 B：常见问题

**Q: 为什么侧边栏切换角色后菜单没变？**
A: 角色切换会触发 `window.location.reload()`。如果没变，检查浏览器控制台的 localStorage 中 `aiplat_role` 是否正确。

**Q: 为什么有些页面打不开？**
A: 检查当前角色是否有该路由的访问权限。参见 [§2.3 后端权限矩阵](#23-后端权限矩阵)。

**Q: 诊断中心为什么显示"架构守卫超时"？**
A: 架构守卫对 ~3,000+ 文件做 grep 扫描，某些检查（如 §40 模型解析双路径）在大型仓库中可能超时。这是已知问题，针对性重跑或使用 Code Intel 工具代替。

**Q: 如何确认新创建的 Agent 生效？**
A: 在 Agent 管理页点击「测试」输入任务后，切换到诊断中心 → Runs 工具，搜索该 Agent 的 run_id，查看执行事件流。

**Q: 知识库文档解析失败怎么办？**
A: 检查文件格式是否支持（PDF/DOCX/PPTX/HTML/MD/TXT）。大文件（>50MB）可能超时。在诊断中心 → 诊断总览 → Wiki 健康中查看详细错误。
