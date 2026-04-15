# 技能管理

> Skill 注册与执行的完整管理

---

## 一、模块定位

技能系统定义和管理智能体可执行的能力单元，是智能体完成任务的具体手段。

### 核心职责

```
技能管理
├── Skill 注册管理
│   ├── Skill 注册与注销
│   ├── Skill 版本管理
│   ├── Skill 依赖管理
│   └── Skill 权限控制
│
├── Skill 执行管理
│   ├── Skill 执行调度
│   ├── Skill 执行监控
│   ├── Skill 执行日志
│   └── Skill 执行结果
│
├── Skill 配置管理
│   ├── Skill 参数配置
│   ├── Skill 输入输出定义
│   └── Skill 超时配置
│
└── Skill 性能分析
    ├── 调用统计分析
    ├── 成功率统计
    └── 性能瓶颈分析
```

### Skill 类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **生成类** | 文本/代码/图像生成 | 文案生成、代码生成 |
| **分析类** | 数据/文本分析 | 情感分析、代码分析 |
| **转换类** | 格式/语言转换 | 格式转换、翻译 |
| **检索类** | 信息检索 | 知识检索、文档搜索 |
| **执行类** | 命令/API执行 | 系统命令、API调用 |

---

## 二、界面设计

### 2.1 Skill 列表

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  技能管理                                                    [注册Skill] [刷新]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Skill 总览                                                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 注册总数 │ │ 启用     │ │ 禁用     │ │ 今日调用 │               │   │
│  │  │   50     │ │   45     │ │   5      │ │ 12,345   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Skill 列表                                          [搜索] [过滤]   │   │
│  │  ┌──────────────┬────────┬────────┬──────────┬──────────┬────────┐│   │
│  │  │ Skill ID     │ 类型   │ 状态   │ 调用次数 │ 成功率   │ 操作   ││   │
│  │  ├──────────────┼────────┼────────┼──────────┼──────────┼────────┤│   │
│  │  │ skill-001   │ 生成类 │ 🟢 启用 │ 5,678    │ 99.2%    │ [详情] ││   │
│  │  │ skill-002   │ 分析类 │ 🟢 启用 │ 3,456    │ 98.5%    │ [详情] ││   │
│  │  │ skill-003   │ 检索类 │ 🟢 启用 │ 2,890    │ 97.8%    │ [详情] ││   │
│  │  │ skill-004   │ 执行类 │ ⚠️ 禁用 │ 1,234    │ 95.3%    │ [启用] ││   │
│  │  │ skill-005   │ 转换类 │ 🟢 启用 │ 890      │ 99.9%    │ [详情] ││   │
│  │  └──────────────┴────────┴────────┴──────────┴──────────┴────────┘│   │
│  │  [上一页] [1] [2] [3] ... [10] [下一页]                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Skill 详情

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Skill 详情: skill-001 (文案生成)                     [编辑] [禁用] [执行] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  基本信息                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ ID: skill-001       │ 类型: 生成类    │ 状态: 🟢 启用        │   │   │
│  │  │ 版本: v1.2.0        │ 注册时间: 2026-03-01  │ 创建者: admin    │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  调用统计                                                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 总调用   │ │ 成功     │ │ 失败     │ │ 平均耗时 │               │   │
│  │  │ 5,678    │ │ 5,632    │ │ 46       │ │ 1.2s     │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  输入输出定义                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 输入参数:                                                    │   │   │
│  │  │   - prompt: string (必填) - 生成提示                       │   │   │
│  │  │   - max_length: int (可选) - 最大长度，默认1000              │   │   │
│  │  │   - temperature: float (可选) - 温度，默认0.7               │   │   │
│  │  │ 输出:                                                        │   │   │
│  │  │   - text: string - 生成的文本                               │   │   │
│  │  │   - tokens: int - 消耗的Token数                             │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  依赖管理                                                            │   │
│  │  ┌──────────────┬────────────┬──────────┬──────────┐            │   │
│  │  │ 依赖模块     │ 版本       │ 状态     │ 操作     │            │   │
│  │  ├──────────────┼────────────┼──────────┼──────────┤            │   │
│  │  │ langchain    │ >=0.1.0    │ ✅ 满足  │ -        │            │   │
│  │  │ openai       │ >=1.0.0    │ ✅ 满足  │ -        │            │   │
│  │  │ transformers │ >=4.30.0    │ ✅ 满足  │ -        │            │   │
│  │  └──────────────┴────────────┴──────────┴──────────┘            │   │
│  │ [添加依赖]                                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  绑定Agent                                                   [查看全部]   │   │
│  │  ┌──────────────┬────────────┬──────────┬──────────┬──────────┐   │   │
│  │  │ Agent名称   │ 类型       │ 调用次数 │ 成功率   │ 操作     │   │   │
│  │  ├──────────────┼────────────┼──────────┼──────────┼──────────┤   │   │
│  │  │ agent-001   │ ReAct      │ 3,456    │ 99.1%    │ [详情]   │   │   │
│  │  │ agent-002   │ RAG        │ 1,234    │ 98.5%    │ [详情]   │   │   │
│  │  │ agent-003   │ Plan       │ 567      │ 100%     │ [详情]   │   │   │
│  │  └──────────────┴────────────┴──────────┴──────────┴──────────┘   │   │
│  │  已绑定 3 个 Agent                                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  版本历史                                                            │   │
│  │  ┌──────────┬──────────┬──────────────────────┬────────┐         │   │
│  │  │ 版本     │ 状态     │ 更新时间             │ 操作   │         │   │
│  │  ├──────────┼──────────┼──────────────────────┼────────┤│         │   │
│  │  │ v1.2.0   │ 当前版本 │ 2026-04-10 10:00:00  │ -      ││         │   │
│  │  │ v1.1.0   │ 历史版本 │ 2026-04-01 10:00:00  │ [回滚] ││         │   │
│  │  │ v1.0.0   │ 历史版本 │ 2026-03-01 10:00:00  │ [回滚] ││         │   │
│  │  └──────────┴──────────┴──────────────────────┴────────┘│         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 注册 Skill 弹窗

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  注册 Skill                                                   [取消] [注册] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  基本信息                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  Skill名称: [文案生成                               ]     │   │   │
│  │  │ Skill类型: [生成类                         ▼]            │   │   │
│  │  │ 描述:     [根据提示生成各类文本内容               ]     │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  输入定义                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ [+ 添加参数]                                                  │   │   │
│  │  │                                                               │   │   │
│  │  │ 参数1: prompt (string, 必填) - 生成提示                     │   │   │
│  │  │ 参数2: max_length (int, 可选) - 最大长度，默认1000           │   │   │
│  │  │ 参数3: temperature (float, 可选) - 温度，默认0.7            │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  输出定义                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ [+ 添加输出]                                                  │   │   │
│  │  │                                                               │   │   │
│  │  │ 输出1: text (string) - 生成的文本                            │   │   │
│  │  │ 输出2: tokens (int) - 消耗的Token数                         │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  配置参数                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ 超时时间(秒): [60                                    ]     │   │   │
│  │  │ 最大并发数:   [10                                    ]     │   │   │
│  │  │ 重试次数:     [3                                     ]     │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [取消] [注册]                                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、API 端点

### 3.1 Skill 注册管理

```python
# 获取 Skill 列表
GET /api/core/skills
Query: ?type=generation&status=enabled&limit=100&offset=0
Response: {
  "skills": [...],
  "total": 50,
  "enabled": 45,
  "disabled": 5
}

# 注册 Skill
POST /api/core/skills
Body: {
  "name": "文案生成",
  "type": "generation",
  "description": "根据提示生成各类文本内容",
  "input_schema": {
    "type": "object",
    "properties": {
      "prompt": {"type": "string", "description": "生成提示"},
      "max_length": {"type": "integer", "default": 1000},
      "temperature": {"type": "number", "default": 0.7}
    },
    "required": ["prompt"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "text": {"type": "string"},
      "tokens": {"type": "integer"}
    }
  },
  "config": {
    "timeout_seconds": 60,
    "max_concurrent": 10,
    "retry_count": 3
  }
}
Response: {
  "id": "skill-001",
  "status": "registered"
}

# 获取 Skill 详情
GET /api/core/skills/{skill_id}

# 更新 Skill 配置
PUT /api/core/skills/{skill_id}
Body: {
  "config": {
    "timeout_seconds": 120
  }
}

# 启用 Skill
POST /api/core/skills/{skill_id}/enable

# 禁用 Skill
POST /api/core/skills/{skill_id}/disable

# 注销 Skill
DELETE /api/core/skills/{skill_id}
```

### 3.2 Skill 版本管理

```python
# 获取版本列表
GET /api/core/skills/{skill_id}/versions

# 获取指定版本
GET /api/core/skills/{skill_id}/versions/{version}

# 回滚到指定版本
POST /api/core/skills/{skill_id}/versions/{version}/rollback
```

### 3.3 Skill 执行

```python
# 执行 Skill
POST /api/core/skills/{skill_id}/execute
Body: {
  "input": {
    "prompt": "写一篇关于AI的文章",
    "max_length": 2000,
    "temperature": 0.8
  },
  "context": {
    "user_id": "user-001"
  }
}
Response: {
  "execution_id": "exec-001",
  "status": "running"
}

# 获取执行结果
GET /api/core/skills/executions/{execution_id}
Response: {
  "id": "exec-001",
  "skill_id": "skill-001",
  "status": "completed",
  "output": {
    "text": "生成的文章内容...",
    "tokens": 1500
  },
  "duration_ms": 1200
}

# 获取执行历史
GET /api/core/skills/{skill_id}/executions?limit=100&offset=0
```

### 3.4 Skill 与 Agent 绑定

```python
# 获取绑定此 Skill 的 Agent 列表
GET /api/core/skills/{skill_id}/agents
Response: {
  "agents": [
    {
      "agent_id": "agent-001",
      "agent_name": "ReAct Agent",
      "agent_type": "ReAct",
      "call_count": 3456,
      "success_rate": 0.991,
      "last_called": "2026-04-13T10:30:00Z"
    }
  ],
  "total": 3
}

# 获取 Skill 绑定统计
GET /api/core/skills/{skill_id}/binding-stats
Response: {
  "total_agents": 3,
  "total_calls": 5678,
  "avg_success_rate": 0.985,
  "call_distribution": {
    "agent-001": 3456,
    "agent-002": 1234,
    "agent-003": 567
  }
}
```

**注意**：Skill 与 Agent 的绑定关系在 Agent 管理中维护（参见 [智能体管理](agents.md)），此 API 仅用于查询。

---

## 四、数据模型

```typescript
// Skill 定义
interface Skill {
  id: string;
  name: string;
  type: SkillType;
  description: string;
  status: 'enabled' | 'disabled' | 'deprecated';
  input_schema: JSONSchema;
  output_schema: JSONSchema;
  config: SkillConfig;
  dependencies: Dependency[];
  version: string;
  created_at: string;
  updated_at: string;
  created_by: string;
}

// Skill 类型
type SkillType = 'generation' | 'analysis' | 'transformation' | 'retrieval' | 'execution';

// Skill 配置
interface SkillConfig {
  timeout_seconds: number;
  max_concurrent: number;
  retry_count: number;
  retry_interval_seconds: number;
  rate_limit?: {
    requests_per_minute: number;
    tokens_per_minute: number;
  };
}

// 依赖定义
interface Dependency {
  name: string;
  version: string;
  status: 'satisfied' | 'missing' | 'version_mismatch';
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
interface SkillExecution {
  id: string;
  skill_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  input: any;
  output?: any;
  error?: string;
  start_time: string;
  end_time?: string;
  duration_ms?: number;
}

// Skill 与 Agent 绑定
interface SkillAgentBinding {
  skill_id: string;
  agent_id: string;
  agent_name: string;
  agent_type: string;
  call_count: number;
  success_rate: number;
  last_called: string;
}

// Skill 绑定统计
interface SkillBindingStats {
  total_agents: number;
  total_calls: number;
  avg_success_rate: number;
  call_distribution: Record<string, number>;
}
```

---

## 五、实施步骤

| 步骤 | 功能 | 工时 |
|------|------|------|
| 1 | Skill 列表页面 | 1天 |
| 2 | Skill 详情页面 | 0.5天 |
| 3 | 注册 Skill 弹窗 | 1天 |
| 4 | Skill 执行功能 | 0.5天 |
| 5 | 版本管理功能 | 0.5天 |
| 6 | API 开发 | 1天 |
| **总计** | | **4.5天** |

---

## 五、Skill 进阶功能（2026 新增）

### 5.1 触发条件（Trigger Conditions）

> Skill 的"路由表" - 用于 AI 自动选择合适的 Skill

**定义**：trigger_conditions 是 Skill 的触发条件列表，用于 AI 根据用户输入自动匹配合适的 Skill。

**触发条件示例**：

```yaml
trigger_conditions:
  - "用户要求生成文本内容"
  - "需要撰写文档或文案"
  - "写一篇关于..."
```

**API**：

```python
# 获取触发条件
GET /api/core/skills/{skill_id}/trigger-conditions
Response: {
  "trigger_conditions": ["生成文本", "撰写文案"],
  "updated_at": "2026-04-14T10:00:00Z"
}

# 更新触发条件
PUT /api/core/skills/{skill_id}/trigger-conditions
Body: {
  "trigger_conditions": ["新条件1", "新条件2"]
}

# 测试触发
POST /api/core/skills/{skill_id}/test-trigger
Body: {
  "input": "帮我写一篇文章"
}
Response: {
  "skill_id": "skill-001",
  "would_trigger": True,
  "matched_conditions": ["撰写文案"]
}
```

### 5.2 Skill 进化（Evolution）

> 让 AI 从执行轨迹中自动蒸馏、生成和优化 Skill

**进化状态**：

| 状态 | 说明 | 触发条件 |
|------|------|----------|
| **CAPTURED** | 正在捕获执行轨迹 | 自动/手动 |
| **FIX** | 正在修复问题 | 失败反馈 |
| **DERIVED** | 从父 Skill 衍生 | 成功执行 |
| **stable** | 稳定状态 | - |

**API**：

```python
# 获取进化状态
GET /api/core/skills/{skill_id}/evolution
Response: {
  "status": "stable",
  "last_evolution": "2026-04-14T10:00:00Z",
  "evolution_count": 5,
  "parent_skill_id": None,
  "child_skill_ids": ["skill-002", "skill-003"]
}

# 手动触发进化
POST /api/core/skills/{skill_id}/evolution
Body: {
  "trigger_type": "manual"  # manual / auto / capture
}

# 获取进化血缘
GET /api/core/skills/{skill_id}/lineage

# 获取捕获的交互
GET /api/core/skills/{skill_id}/captures

# 获取派生的子技能
GET /api/core/skills/{skill_id}/derived
```

### 5.3 Skill 结构（Agent Skill 模式）

> 2026 新标准 - 独立目录结构

```
my-skill/
├── SKILL.md         # 元数据 + 核心指令（必须）
├── handler.py      # Skill 实现
├── scripts/        # 确定性脚本（可选）
│   ├── fetch_data.py
│   └── transform.py
└── references/     # 按需加载知识（可选）
    ├── api_docs.md
    └── examples.md
```

---

## 七、监控指标

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `skills.total` | Skill 总数 | 个 |
| `skills.enabled` | 启用的 Skill 数 | 个 |
| `skills.executions.total` | 执行总次数 | 次 |
| `skills.executions.success` | 成功次数 | 次 |
| `skills.executions.failed` | 失败次数 | 次 |
| `skills.executions.duration_ms` | 执行耗时 | 毫秒 |

---

## 八、相关文档

- [核心能力层总览](index.md) - Layer 1 管理接口总览
- [智能体管理](agents.md) - Agent 实例管理
- [执行引擎管理](harness.md) - Harness 执行引擎运维
- [aiPlat-core 文档](../../../aiPlat-core/docs/index.md) - core 层功能文档

---

*最后更新:2026-04-13  
**版本**：v1.0  
**维护团队**：AI Platform Team