# 智能体管理

> Agent 实例的完整生命周期管理

---

## 一、模块定位

智能体管理负责 Agent 实例的创建、配置、监控和生命周期管理。

### 核心职责

```
智能体管理
├── Agent 生命周期
│   ├── 创建 Agent 实例
│   ├── 配置 Agent 参数
│   ├── 启动/停止 Agent
│   └── 删除 Agent 实例
│
├── Agent 执行监控
│   ├── 执行状态跟踪
│   ├── 性能指标采集
│   └── 错误日志记录
│
├── Agent 配置管理
│   ├── 参数调优
│   ├── 记忆配置
│   ├── 技能绑定← 新增
│   └── 工具绑定
│
└── Agent 性能分析
    ├── 成功率统计
    ├── 执行时间分析
    └── 资源消耗监控
```

### Agent 类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| **ReAct** | 推理-行动型 | 复杂任务、工具调用 |
| **RAG** | 检索增强型 | 知识问答、文档检索 |
| **Plan** | 规划执行型 | 多步骤任务、工作流 |
| **Conversational** | 对话型 | 聊天场景、客服 |
| **Tool-Using** | 工具型 | 外部调用、API集成 |
| **Multi-Agent** | 多Agent协作 | 复杂协作任务 |

---

## 二、界面设计

### 2.1 Agent 列表

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  智能体管理                                                  [创建Agent] [刷新] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Agent 总览                                                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 总数     │ │ 运行中   │ │ 已停止   │ │ 异常     │               │   │
│  │  │   15     │ │   8      │ │   6      │ │   1 ⚠️   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Agent 列表                                          [搜索] [过滤]   │   │
│  │  ┌──────────┬────────┬────────┬──────────┬──────────┬──────────┐│   │
│  │  │ Agent ID │ 类型   │ 状态   │ 执行次数 │ 成功率   │ 操作     ││   │
│  │  ├──────────┼────────┼────────┼──────────┼──────────┼──────────┤│   │
│  │  │ agent-001│ ReAct  │ 🟢 运行 │ 1,234    │ 98.5%    │ [详情]   ││   │
│  │  │ agent-002│ RAG    │ 🟢 运行 │ 567      │ 99.2%    │ [详情]   ││   │
│  │  │ agent-003│ Plan   │ 🔴 停止 │ 890      │ 95.3%    │ [详情]   ││   │
│  │  │ agent-004│ ReAct  │ 🟡 异常 │ 234      │ 78.9%    │ [详情]   ││   │
│  │  │ agent-005│ Conv   │ 🟢 运行 │ 1,567    │ 99.8%    │ [详情]   ││   │
│  │  │ agent-006│ Tool   │ 🟢 运行 │ 456      │ 97.2%    │ [详情]   ││   │
│  │  └──────────┴────────┴────────┴──────────┴──────────┴──────────┘│   │
│  │  [上一页] [1] [2] [3] ... [10] [下一页]                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent 详情

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Agent 详情: agent-001 (ReAct)                        [编辑] [停止] [执行] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  基本信息                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ ID: agent-001          │ 类型: ReAct            │ 状态: 🟢 运行 │   │   │
│  │  │ 创建时间: 2026-04-01   │ 最后执行: 10:30:00     │ 版本: v1.2  │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  执行统计                                                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 总执行   │ │ 成功     │ │ 失败     │ │ 平均耗时 │               │   │
│  │  │ 1,234    │ │ 1,215    │ │ 19       │ │ 2.3s     │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  配置参数                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 模型: gpt-4           │ 温度: 0.7            │ 最大 Token: 4096  │   │   │
│  │  │ 最大循环: 25          │ 记忆召回: 5          │ 工具数量: 8       │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │  [查看完整配置]                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  绑定技能                                                  [添加]   │   │
│  │  ┌──────────────┬────────────┬──────────┬──────────┬──────────┐   │   │
│  │  │ 技能名称     │ 类型       │ 调用次数 │ 成功率   │ 操作     │   │   │
│  │  ├──────────────┼────────────┼──────────┼──────────┼──────────┤   │   │
│  │  │ TextGen      │ 生成类     │ 1,234    │ 99.2%    │ [解绑]   │   │   │
│  │  │ CodeAnalysis │ 分析类     │ 567      │ 98.5%    │ [解绑]   │   │   │
│  │  │ DataSummary  │ 分析类     │ 345      │ 100%     │ [解绑]   │   │   │
│  │  └──────────────┴────────────┴──────────┴──────────┴──────────┘   │   │
│  │  已绑定 3 个 Agent                                                    │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  绑定工具                                                  [添加]   │   │
│  │  ┌──────────────┬────────────┬──────────┬──────────┬──────────┐   │   │
│  │  │ 工具名称     │ 类型       │ 调用次数 │ 成功率   │ 操作     │   │   │
│  │  ├──────────────┼────────────┼──────────┼──────────┼──────────┤   │   │
│  │  │ WebSearch    │ 搜索工具   │ 567      │ 99.1%    │ [解绑]   │   │   │
│  │  │ Calculator   │ 计算工具   │ 234      │ 100%     │ [解绑]   │   │   │
│  │  │ CodeExecutor │ 代码执行   │ 123      │ 98.4%    │ [解绑]   │   │   │
│  │  │ Database     │ 数据库查询 │ 89       │ 97.8%    │ [解绑]   │   │   │
│  │  └──────────────┴────────────┴──────────┴──────────┴──────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  近期执行                                                            │   │
│  │  ┌──────────┬────────┬──────────┬──────────┬──────────┐         │   │
│  │  │ 执行ID   │ 状态   │ 开始时间 │ 耗时     │ 操作     │        │   │
│  │  ├──────────┼────────┼──────────┼──────────┼──────────┤│         │   │
│  │  │ e-001    │ ✅ 成功│ 10:30:00 │ 2.1s     │ [查看]   │        │   │
│  │  │ e-002    │ ✅ 成功│ 10:28:00 │ 1.8s     │ [查看]   │        │   │
│  │  │ e-003    │ ❌ 失败│ 10:25:00 │ 0.5s     │ [查看]   │        │   │
│  │  └──────────┴────────┴──────────┴──────────┴──────────┘│         │   │
│  │  [查看全部执行]                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 创建 Agent 向导

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  创建 Agent                                                   [取消] [创建] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  步骤指示器: ①选择类型 ━━━━ ②配置参数 ━━━━ ③绑定技能/工具 ━━━━ ④确认       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  步骤1: 选择 Agent 类型                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ ○ ReAct Agent - 推理行动型，适合复杂任务                    │   │   │
│  │  │ ● RAG Agent - 检索增强型，适合知识问答                      │   │   │
│  │  │ ○ Plan Agent - 规划执行型，适合多步骤任务                   │   │   │
│  │  │ ○ Conversational Agent - 对话型，适合聊天场景               │   │   │
│  │  │ ○ Tool-Using Agent - 工具型，适合外部调用                   │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  步骤2: 配置参数                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 模型: [gpt-4                                ▼]            │   │   │
│  │  │ 温度: [0.7                                           ]    │   │   │
│  │  │ 最大 Token: [4096                                    ]    │   │   │
│  │  │ 最大循环: [25                                        ]    │   │   │
│  │  │ 记忆类型: [短期记忆                         ▼]            │   │   │
│  │  │ 记忆召回数: [5                                        ]    │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  步骤3: 绑定技能与工具                                               │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 可用技能:                                                    │   │   │
│  │  │ ☑️ TextGenerationSkill - 文本生成                           │   │   │
│  │  │ ☑️ CodeAnalysisSkill - 代码分析                             │   │   │
│  │  │ ☐ DataAnalysisSkill - 数据分析                              │   │   │
│  │  │ ☐ ImageGenerationSkill - 图像生成                           │   │   │
│  │  │                                                               │   │   │
│  │  │ 可用工具:                                                    │   │   │
│  │  │ ☑️ WebSearchTool - 网络搜索                                  │   │   │
│  │  │ ☑️ CalculatorTool - 数学计算                                 │   │   │
│  │  │ ☐ DatabaseQueryTool - 数据库查询                            │   │   │
│  │  │ ☐ FileOperationTool - 文件操作                              │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [上一步] [下一步] [取消] [创建]                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、API 端点

> 本章 API 以“scope 分离”为准：  
> - **核心能力层（engine）**：`/api/core/agents/*`（management 侧转发；前端菜单为“核心能力层”→ Agent管理）  
> - **对外应用库（workspace）**：`/api/core/workspace/agents/*`（management 侧转发；前端菜单为“应用库”→ Agent库）

### 3.1 Agent 管理

```python
# 获取 Agent 列表
GET /api/core/agents
Query: ?type=ReAct&status=running&limit=100&offset=0
Response: {
  "agents": [...],
  "total": 15,
  "running": 8,
  "stopped": 6,
  "error": 1
}

# 获取 Workspace Agent 列表（对外应用库）
GET /api/core/workspace/agents
Query: ?type=react&status=running&limit=100&offset=0

# 创建 Agent
POST /api/core/agents
Body: {
  "type": "ReAct",
  "name": "my-agent",
  "config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 4096,
    "max_iterations": 25
  },
  "tools": ["WebSearchTool", "CalculatorTool"],
  "memory": {
    "type": "short_term",
    "recall_count": 5
  }
}
Response: {
  "id": "agent-001",
  "status": "created"
}

# 创建 Workspace Agent（对外应用库）
POST /api/core/workspace/agents
Body: {
  "agent_type": "react",
  "name": "my-app-agent",
  "config": { "model": "gpt-4", "temperature": 0.7 },
  "skills": ["text_generation"],
  "tools": ["web_search"]
}

# 获取 Agent 详情
GET /api/core/agents/{agent_id}
Response: {
  "id": "agent-001",
  "type": "ReAct",
  "status": "running",
  "config": {...},
  "tools": [...],
  "memory": {...},
  "stats": {
    "total_executions": 1234,
    "success_rate": 0.985,
    "avg_duration_ms": 2300
  }
}

# 更新 Agent 配置
PUT /api/core/agents/{agent_id}
Body: {
  "config": {
    "temperature": 0.8
  }
}

# 删除 Agent
DELETE /api/core/agents/{agent_id}

# 启动 Agent
POST /api/core/agents/{agent_id}/start

# 停止 Agent
POST /api/core/agents/{agent_id}/stop
```

### 3.2 Agent 执行（engine / workspace）

```python
# 执行 Agent
POST /api/core/agents/{agent_id}/execute
Body: {
  "input": "查询今日天气",
  "context": {
    "user_id": "user-001",
    "session_id": "session-001"
  }
}
Response: {
  "execution_id": "exec-001",
  "status": "running"
}

# 执行 Workspace Agent
POST /api/core/workspace/agents/{agent_id}/execute
Body: {
  "input": {"message": "查询今日天气"},
  "context": {"user_id": "user-001", "session_id": "session-001"}
}

# 获取执行历史
GET /api/core/agents/{agent_id}/history?limit=100&offset=0
GET /api/core/workspace/agents/{agent_id}/history?limit=100&offset=0
Response: {
  "history": [
    {
      "id": "exec-001",
      "status": "completed",
      "start_time": "2026-04-13T10:30:00Z",
      "duration_ms": 2300
    }
  ],
  "total": 1234
}

# 获取执行详情
GET /api/core/agents/executions/{execution_id}
Response: {
  "id": "exec-001",
  "agent_id": "agent-001",
  "status": "completed",
  "input": "查询今日天气",
  "output": "今日天气晴...",
  "steps": [...],
  "duration_ms": 2300
}
```

### 3.3 Agent 技能管理

```python
# Workspace 端点（对外应用库）
GET /api/core/workspace/agents/{agent_id}/skills
POST /api/core/workspace/agents/{agent_id}/skills
DELETE /api/core/workspace/agents/{agent_id}/skills/{skill_id}

# 获取 Agent 绑定的技能
GET /api/core/agents/{agent_id}/skills
Response: {
  "skills": [
    {
      "skill_id": "skill-001",
      "skill_name": "TextGenerationSkill",
      "skill_type": "generation",
      "call_count": 1234,
      "success_rate": 0.992,
      "last_called": "2026-04-13T10:30:00Z"
    }
  ]
}

# 绑定技能到 Agent
POST /api/core/agents/{agent_id}/skills
Body: {
  "skill_ids": ["skill-001", "skill-002"]
}
Response: {
  "bound_skills": 2,
  "status": "success"
}

# 解绑技能
DELETE /api/core/agents/{agent_id}/skills/{skill_id}
```

### 3.4 Agent 工具管理

```python
# Workspace 端点（对外应用库）
GET /api/core/workspace/agents/{agent_id}/tools
POST /api/core/workspace/agents/{agent_id}/tools
DELETE /api/core/workspace/agents/{agent_id}/tools/{tool_id}

# 获取 Agent 绑定的工具
GET /api/core/agents/{agent_id}/tools

# 绑定工具到 Agent
POST /api/core/agents/{agent_id}/tools
Body: {
  "tool_ids": ["tool-001", "tool-002"]
}

# 解绑工具
DELETE /api/core/agents/{agent_id}/tools/{tool_id}
```

### 3.5 Agent 版本管理（workspace）

```python
GET  /api/core/workspace/agents/{agent_id}/versions
POST /api/core/workspace/agents/{agent_id}/versions                 # Body: {"changes": "变更说明"}
POST /api/core/workspace/agents/{agent_id}/versions/{version}/rollback
```

---

## 四、数据模型

```typescript
// Agent 定义
interface Agent {
  id: string;
  name: string;
  type: AgentType;
  status: 'running' | 'stopped' | 'error' | 'pending';
  config: AgentConfig;
  skills: string[];      // 绑定的技能ID列表
  tools: string[];       // 绑定的工具ID列表
  memory: MemoryConfig;
  created_at: string;
  updated_at: string;
  version: string;
}

// Agent 类型
type AgentType = 
  | 'ReAct' 
  | 'RAG' 
  | 'Plan' 
  | 'Conversational' 
  | 'Tool-Using'
  | 'Multi-Agent';

// Agent 配置
interface AgentConfig {
  model: string;
  temperature: number;
  max_tokens: number;
  max_iterations: number;
  timeout_seconds: number;
  system_prompt?: string;
}

// 记忆配置
interface MemoryConfig {
  type: 'short_term' | 'long_term' | 'none';
  recall_count: number;
  max_history?: number;
}

// 执行统计
interface ExecutionStats {
  total: number;
  success: number;
  failed: number;
  avg_duration_ms: number;
  success_rate: number;
}

// 执行记录
interface ExecutionRecord {
  id: string;
  agent_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  start_time: string;
  end_time?: string;
  duration_ms?: number;
  input: any;
  output?: any;
  error?: string;
  steps: ExecutionStep[];
}

// 执行步骤
interface ExecutionStep {
  step: number;
  type: 'thought' | 'action' | 'observation';
  content: string;
  tool?: string;
  tool_input?: any;
  tool_output?: any;
  duration_ms: number;
}

// 技能绑定
interface SkillBinding {
  agent_id: string;
  skill_id: string;
  skill_name: string;
  skill_type: 'generation' | 'analysis' | 'transformation' | 'retrieval' | 'execution';
  call_count: number;
  success_rate: number;
  last_called: string;
}

// 工具绑定
interface ToolBinding {
  agent_id: string;
  tool_id: string;
  tool_name: string;
  call_count: number;
  success_rate: number;
  last_called: string;
}
```

---

## 五、实施步骤

| 步骤 | 功能 | 工时 |
|------|------|------|
| 1 | Agent 列表页面 | 1天 |
| 2 | Agent 详情页面 | 0.5天 |
| 3 | 创建 Agent 向导 | 1天 |
| 4 | Agent 执行与监控 | 1天 |
| 5 | Agent 工具管理 | 0.5天 |
| 6 | API 开发 | 1天 |
| **总计** | | **5天** |

---

## 六、监控指标

### 6.1 Agent 状态指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `agents.total` | Agent 总数 | 个 |
| `agents.running` | 运行中 Agent 数 | 个 |
| `agents.stopped` | 已停止 Agent 数 | 个 |
| `agents.error` | 异常 Agent 数 | 个 |

### 6.2 Agent 执行指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `agents.executions.total` | 执行总次数 | 次 |
| `agents.executions.success` | 成功次数 | 次 |
| `agents.executions.failed` | 失败次数 | 次 |
| `agents.executions.duration_ms` | 执行耗时 | 毫秒 |
| `agents.executions.iterations` | 循环迭代次数 | 次 |

### 6.3 Agent 性能指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `agents.success_rate` | 成功率 | 百分比 |
| `agents.avg_duration_ms` | 平均执行时间 | 毫秒 |
| `agents.skill_calls` | 技能调用次数 | 次 |
| `agents.tool_calls` | 工具调用次数 | 次 |
| `agents.memory_usage_mb` | 内存使用 | MB |

### 6.4 Agent 技能指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `agents.skills.bound` | 绑定的技能数 | 个 |
| `agents.skills.calls` | 技能调用总次数 | 次 |
| `agents.skills.success` | 技能调用成功次数 | 次 |
| `agents.skills.failed` | 技能调用失败次数 | 次 |
| `agents.skills.avg_duration_ms` | 技能平均执行时间 | 毫秒 |

### 6.5 Agent 工具指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `agents.tools.bound` | 绑定的工具数 | 个 |
| `agents.tools.calls` | 工具调用总次数 | 次 |
| `agents.tools.success` | 工具调用成功次数 | 次 |
| `agents.tools.failed` | 工具调用失败次数 | 次 |
| `agents.tools.avg_duration_ms` | 工具平均执行时间 | 毫秒 |

---

## 七、告警规则

| 规则名称 | 条件 | 严重性 | 说明 |
|---------|------|--------|------|
| `agent_error_rate_high` | 错误率 > 5% | warning | Agent 错误率过高 |
| `agent_execution_timeout` | 超时次数 > 10 | warning | Agent 执行超时过多 |
| `agent_stuck` | 执行时间 > 5分钟 | critical | Agent 可能卡住 |
| `agent_memory_exhausted` | 内存使用 > 90% | critical | Agent 内存耗尽 |
| `agent_unhealthy` | 健康检查失败 | warning | Agent 健康状态异常 |

---

## 八、相关文档

- [核心能力层总览](index.md) - Layer 1 管理接口总览
- [执行引擎管理](harness.md) - Harness 执行引擎运维
- [技能管理](skills.md) - Skill 注册与执行
- [记忆系统管理](memory.md) - 会话与记忆管理
- [aiPlat-core 文档](../../../aiPlat-core/docs/index.md) - core 层功能文档

---

*最后更新:2026-04-13  
**版本**：v1.0  
**维护团队**：AI Platform Team
