# 执行引擎管理

> Harness 执行系统的完整运维能力

---

## 一、模块定位

执行引擎管理负责 Agent 执行循环、重试机制、Hook 拦截器、协调系统和反馈循环的运维管理。

### 核心职责

```
执行引擎管理
├── 执行系统（Execution）
│   ├── Agent执行循环配置
│   ├── 重试策略管理
│   ├── 超时控制
│   └── 执行日志追踪
│
├── 协调系统（Coordination）
│   ├── 多Agent协作模式
│   ├── 协调策略配置
│   └── 协作状态监控
│
├── 观察系统（Observability）
│   ├── 指标采集
│   ├── 事件总线
│   └── 追踪管理
│
└── 反馈循环（Feedback Loops）
    ├── LOCAL层反馈
    ├── PUSH层推送
    └── PROD层生效
```

### 子系统说明

| 子系统 | 说明 | 主要能力 |
|--------|------|----------|
| **Execution** | 执行系统 | Agent循环、重试、超时控制 |
| **Coordination** | 协调系统 | 多Agent协作、6种模式 |
| **Observability** | 观察系统 | 指标、事件、追踪 |
| **Feedback Loops** | 反馈循环 | LOCAL/PUSH/PROD三层反馈 |

---

## 二、界面设计

### 2.1 执行引擎状态总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  执行引擎管理                                                  [刷新] [配置] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  引擎状态总览                                                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 执行引擎  │ │ 协调引擎 │ │ 观察引擎 │ │ 反馈引擎 │               │   │
│  │  │  🟢 运行  │ │  🟢 运行  │ │  🟢 运行  │ │  🟢 运行 │               │   │
│  │  │  活跃循环: │ │  协调数:  │ │  事件数:  │ │  反馈数: │               │   │
│  │  │    12     │ │    3      │ │   1024   │ │    45   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  近期执行活动                                           [查看全部]   │   │
│  │  ┌──────────┬────────┬────────┬──────────┬──────────┬──────────┐  │   │
│  │  │ 执行ID   │ Agent  │ 状态   │ 开始时间  │ 耗时     │ 操作     │  │   │
│  │  ├──────────┼────────┼────────┼──────────┼──────────┼──────────┤  │   │
│  │  │ exec-001 │ ReAct  │ ✅ 完成 │ 10:30:00 │ 2.3s     │ [详情]   │  │   │
│  │  │ exec-002 │ RAG    │ ⏳ 运行 │ 10:31:00 │ -        │ [终止]   │  │   │
│  │  │ exec-003 │ Plan   │ ❌ 失败 │ 10:32:00 │ 1.5s     │ [重试]   │  │   │
│  │  │ exec-004 │ ReAct  │ ✅ 完成 │ 10:33:00 │ 3.1s     │ [详情]   │  │   │
│  │  └──────────┴────────┴────────┴──────────┴──────────┴──────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 执行配置面板

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  执行配置                                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  执行循环配置                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 最大循环次数: [25                                    ▼]   │   │   │
│  │  │ 超时时间(秒): [300                                   ▼]   │   │   │
│  │  │ 重试次数:     [3                                     ▼]   │   │   │
│  │  │ 重试间隔(秒): [1                                     ▼]   │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Hook 拦截器                                                         │   │
│  │  ┌──────────────┬────────┬──────────┬────────────┬────────┐    │   │
│  │  │ Hook 名称    │ 类型   │ 优先级   │ 状态       │ 操作   │    │   │
│  │  ├──────────────┼────────┼──────────┼────────────┼────────┤    │   │
│  │  │ LoggingHook  │ 前置   │ 100      │ ✅ 启用    │ [编辑] │    │   │
│  │  │ MetricsHook  │ 后置   │ 200      │ ✅ 启用    │ [编辑] │    │   │
│  │  │ RateLimitHook│ 前置   │ 50       │ ⚠️ 禁用   │ [编辑] │    │   │
│  │  │ RetryHook    │ 后置   │ 150      │ ✅ 启用    │ [编辑] │    │   │
│  │  └──────────────┴────────┴──────────┴────────────┴────────┘    │   │
│  │  [添加Hook]                                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [保存配置] [重置默认]                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 协调模式配置

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  协调模式配置                                              [添加协调器]     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  协调器列表                                                          │   │
│  │  ┌──────────┬────────────┬──────────┬──────────┬──────────┐      │   │
│  │  │ 协调器ID  │ 模式       │ Agent数  │ 状态     │ 操作     │      │   │
│  │  ├──────────┼────────────┼──────────┼──────────┼──────────┤      │   │
│  │  │ coord-001│ Pipeline   │ 3        │ 🟢 活跃 │ [详情]   │      │   │
│  │  │ coord-002│ FanOutFanIn│ 5        │ 🟡 空闲 │ [详情]   │      │   │
│  │  │ coord-003│ Supervisor │ 1+4      │ 🟢 活跃 │ [详情]   │      │   │
│  │  │ coord-004│ ExpertPool │ 4        │ 🔴 停止 │ [启动]   │      │   │
│  │  └──────────┴────────────┴──────────┴──────────┴──────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  协调模式说明                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ • Pipeline: 流水线模式，Agent按顺序执行                    │   │   │
│  │  │ • FanOutFanIn: 扇出扇入模式，Agent并行执行后合并结果       │   │   │
│  │  │ • Supervisor: 监督者模式，一个主Agent协调多个工作Agent    │   │   │
│  │  │ • ExpertPool: 专家池模式，根据输入选择合适的专家Agent     │   │   │
│  │  │ • ProducerReviewer: 生产者-审查者模式，一个生成一个审核   │   │   │
│  │  │ • Hierarchical: 层级模式，Agent按层级组织执行             │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 反馈循环配置

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  反馈循环配置                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LOCAL 层（本地反馈）                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 启用状态: [✓]                                                 │   │   │
│  │  │ 最大历史记录: [1000                                   ]     │   │   │
│  │  │ 自动清理: [✓] 超过30天自动清理                               │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PUSH 层（配置推送）                                                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 启用状态: [✓]                                                 │   │   │
│  │  │ 推送目标: [配置中心URL                              ]       │   │   │
│  │  │ 推送间隔: [60                                        ] 秒   │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PROD 层（生产生效）                                                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 启用状态: [✓]                                                 │   │   │
│  │  │ 灰度策略: [10                                        ]%     │   │   │
│  │  │ 自动回滚: [✓] 检测到异常时自动回滚                           │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [保存配置]                                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、API 端点

### 3.1 执行引擎管理

```python
# 获取执行引擎状态
GET /api/core/harness/status
Response: {
  "status": "healthy",
  "components": {
    "execution": {"status": "healthy", "active_loops": 12},
    "coordination": {"status": "healthy", "coordinators": 3},
    "observability": {"status": "healthy", "events": 1024},
    "feedback_loops": {"status": "healthy", "feedback_count": 45}
  }
}

# 获取执行配置
GET /api/core/harness/config
Response: {
  "max_iterations": 25,
  "timeout_seconds": 300,
  "retry_count": 3,
  "retry_interval_seconds": 1,
  "hooks": [...]
}

# 更新执行配置
PUT /api/core/harness/config
Body: {
  "max_iterations": 30,
  "timeout_seconds": 600
}

# 获取执行日志
GET /api/core/harness/logs?limit=100&offset=0&status=completed
Response: {
  "logs": [...],
  "total": 1024
}

# 获取执行详情
GET /api/core/harness/executions/{execution_id}
Response: {
  "id": "exec-001",
  "agent": "ReAct",
  "status": "completed",
  "start_time": "2026-04-13T10:30:00Z",
  "end_time": "2026-04-13T10:30:02Z",
  "duration_ms": 2300,
  "steps": [...]
}
```

### 3.2 Hook 管理

```python
# 获取 Hook 列表
GET /api/core/harness/hooks

# 添加 Hook
POST /api/core/harness/hooks
Body: {
  "name": "LoggingHook",
  "type": "pre",
  "priority": 100,
  "enabled": true,
  "config": {...}
}

# 更新 Hook
PUT /api/core/harness/hooks/{hook_id}

# 删除 Hook
DELETE /api/core/harness/hooks/{hook_id}
```

### 3.3 协调器管理

```python
# 获取协调器列表
GET /api/core/harness/coordinators
Response: {
  "coordinators": [
    {
      "id": "coord-001",
      "pattern": "Pipeline",
      "agents": ["agent-1", "agent-2", "agent-3"],
      "status": "active"
    }
  ]
}

# 创建协调器
POST /api/core/harness/coordinators
Body: {
  "pattern": "Pipeline",
  "agents": ["agent-1", "agent-2", "agent-3"],
  "config": {...}
}

# 获取协调器详情
GET /api/core/harness/coordinators/{coordinator_id}

# 更新协调器
PUT /api/core/harness/coordinators/{coordinator_id}

# 删除协调器
DELETE /api/core/harness/coordinators/{coordinator_id}
```

### 3.4 反馈循环管理

```python
# 获取反馈循环配置
GET /api/core/harness/feedback/config
Response: {
  "local": {"enabled": true, "max_history": 1000},
  "push": {"enabled": true, "endpoint": "...", "interval_seconds": 60},
  "prod": {"enabled": true, "canary_percent": 10}
}

# 更新反馈循环配置
PUT /api/core/harness/feedback/config
Body: {
  "local": {"enabled": true, "max_history": 2000},
  "push": {"enabled": false}
}
```

---

## 四、数据模型

```typescript
// 执行引擎状态
interface HarnessStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: {
    execution: ComponentStatus;
    coordination: ComponentStatus;
    observability: ComponentStatus;
    feedback_loops: ComponentStatus;
  };
  uptime_seconds: number;
  last_check: string;
}

// 组件状态
interface ComponentStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  [key: string]: any;
}

// 执行配置
interface HarnessConfig {
  max_iterations: number;
  timeout_seconds: number;
  retry_count: number;
  retry_interval_seconds: number;
  hooks: Hook[];
}

// Hook 定义
interface Hook {
  id: string;
  name: string;
  type: 'pre' | 'post';
  priority: number;
  enabled: boolean;
  config: Record<string, any>;
}

// 执行记录
interface ExecutionLog {
  id: string;
  agent: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  start_time: string;
  end_time?: string;
  duration_ms?: number;
  error?: string;
  steps: ExecutionStep[];
}

// 执行步骤
interface ExecutionStep {
  step: number;
  action: string;
  input: any;
  output: any;
  duration_ms: number;
}

// 协调器
interface Coordinator {
  id: string;
  pattern: 'Pipeline' | 'FanOutFanIn' | 'Supervisor' | 'ExpertPool' | 'ProducerReviewer' | 'Hierarchical';
  agents: string[];
  status: 'active' | 'idle' | 'stopped';
  config: Record<string, any>;
}

// 反馈循环配置
interface FeedbackLoopConfig {
  local: {
    enabled: boolean;
    max_history: number;
    auto_cleanup: boolean;
    cleanup_days: number;
  };
  push: {
    enabled: boolean;
    endpoint: string;
    interval_seconds: number;
  };
  prod: {
    enabled: boolean;
    canary_percent: number;
    auto_rollback: boolean;
  };
}
```

---

## 五、实施步骤

| 步骤 | 功能 | 工时 |
|------|------|------|
| 1 | 执行引擎状态页面 | 1天 |
| 2 | 执行配置管理 | 0.5天 |
| 3 | Hook拦截器管理 | 1天 |
| 4 | 协调模式配置 | 1天 |
| 5 | 反馈循环配置 | 0.5天 |
| 6 | 执行日志查询 | 0.5天 |
| 7 | API开发 | 1天 |
| **总计** | | **5.5天** |

---

## 六、监控指标

### 6.1 执行引擎指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `harness.execution.active_loops` | 活跃执行循环数 | 个 |
| `harness.execution.total` | 执行总次数 | 次 |
| `harness.execution.success` | 执行成功次数 | 次 |
| `harness.execution.failed` | 执行失败次数 | 次 |
| `harness.execution.duration_ms` | 执行耗时 | 毫秒 |
| `harness.execution.iterations` | 循环迭代次数 | 次 |

### 6.2 协调系统指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `harness.coordination.active` | 活跃协调器数 | 个 |
| `harness.coordination.agents` | 参与协调的Agent数 | 个 |
| `harness.coordination.duration_ms` | 协调耗时 | 毫秒 |

### 6.3 观察系统指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `harness.observability.events_total` | 事件总数 | 个 |
| `harness.observability.events_per_second` | 每秒事件数 | 个/秒 |
| `harness.observability.traces_total` | 追踪总数 | 个 |

### 6.4 反馈循环指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `harness.feedback.local_events` | 本地反馈事件数 | 个 |
| `harness.feedback.push_success` | 推送成功次数 | 次 |
| `harness.feedback.push_failed` | 推送失败次数 | 次 |
| `harness.feedback.prod_rollbacks` | 生产回滚次数 | 次 |

---

## 七、告警规则

| 规则名称 | 条件 | 严重性 | 说明 |
|---------|------|--------|------|
| `harness_execution_failed` | 失败率 > 5% | warning | 执行失败率过高 |
| `harness_execution_timeout` | 超时次数 > 10 | warning | 执行超时过多 |
| `harness_loop_stuck` | 循环次数 > 50 | critical | 执行循环卡住 |
| `harness_coordination_error` | 协调错误 > 5 | warning | 协调系统异常 |
| `harness_feedback_push_failed` | 推送失败 > 3 | warning | 反馈推送失败 |

---

## 八、相关文档

- [核心能力层总览](index.md) - Layer 1 管理接口总览
- [智能体管理](agents.md) - Agent 实例管理
- [技能管理](skills.md) - Skill 注册与执行
- [aiPlat-core 文档](../../../aiPlat-core/docs/index.md) - core 层功能文档

---

*最后更新:2026-04-13  
**版本**：v1.0  
**维护团队**：AI Platform Team