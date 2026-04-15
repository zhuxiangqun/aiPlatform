# Subagent 架构设计

## 概述

本文档描述如何在 aiPlat-core 系统中实现 Subagent 架构，使主 Agent 能够派生子 Agent 执行特定任务，实现任务的并行处理和权限隔离。

## 背景

在复杂任务场景中，单一 Agent 难以同时处理多个不同维度的任务：
- 一个任务可能需要安全审查（只读）+ 代码修改（可写）+ 测试编写（可创建）
- 全在一个对话中处理，工具权限无法精细控制
- 一个方向的错误可能影响另一个方向

Claude Code 的 Subagent 模式提供了解决方案：每个 Subagent 有独立的上下文、自定义系统提示、受限的工具访问权限。

## 目标

1. **任务隔离** - 不同任务派发给不同的专业 Subagent
2. **权限控制** - Subagent 只能访问允许的工具
3. **协调调度** - 主 Agent 作为协调器派发任务、汇总结果
4. **状态管理** - Subagent 独立状态，不污染主 Agent 上下文

## 现有组件

### MultiAgent (已存在)

位置: `core/apps/agents/multi_agent.py`

功能:
- 多 Agent 协作框架
- Agent 通信和消息传递
- 任务分发和结果聚合

## 设计方案

### 1. Subagent 抽象

Subagent 是具有以下特性的 Agent 实体：

| 特性 | 描述 |
|------|------|
| 独立上下文 | 独立的对话历史和状态 |
| 受限工具集 | 只允许访问配置的工具 |
| 专属系统提示 | 每个 Subagent 可配置专属指令 |
| 生命周期 | 可创建、执行、销毁 |
| 结果返回 | 执行完成后返回结果给主 Agent |

### 2. Subagent 配置结构

```yaml
# subagent.yaml
name: secure-reviewer
description: 安全审计专家，只读审查，不能修改任何文件
type: subagent

# 工具权限配置
tool_permissions:
  allowed:
    - Read
    - Grep
    - Glob
  denied:
    - Write
    - Edit
    - Bash

# 专属系统提示
system_prompt: |
  你是一个安全审计专家。你的任务是：
  1. 检查认证和授权逻辑
  2. 识别 SQL 注入、XSS、CSRF 漏洞
  3. 检查硬编码的密钥和 Token

# 超时配置
timeout: 300

# 重试策略
retry:
  max_attempts: 3
  backoff: exponential
```

### 3. 工具权限级别

| 级别 | 权限 | 适用场景 |
|------|------|----------|
| READ_ONLY | Read, Grep, Glob | 审查、分析类任务 |
| READ_WRITE | Read, Grep, Glob, Write, Edit | 修改、完善类任务 |
| EXECUTE | Read, Write, Edit, Bash | 端到端实现任务 |
| FULL | 所有工具 | 管理员 Agent |

### 4. 协调器模式

主 Agent 作为协调器，负责：
1. 评估任务类型和复杂度
2. 选择合适的 Subagent
3. 并行或顺序派发任务
4. 汇总各 Subagent 结果
5. 输出最终结果

```
用户：帮我审查这个 PR

主 Agent（协调器）
  ├── Subagent: secure-reviewer → 安全漏洞报告
  ├── Subagent: test-engineer → 测试覆盖率分析
  └── Subagent: documentation-writer → 文档完整性检查

汇总三份报告 → 输出综合审查结果
```

### 5. Subagent 通信协议

Subagent 与主 Agent 之间的通信：

| 消息类型 | 方向 | 内容 |
|----------|------|------|
| TASK_ASSIGN | 主→子 | 任务描述、上下文、期望输出 |
| PROGRESS_UPDATE | 子→主 | 执行进度、中间结果 |
| RESULT | 子→主 | 执行结果、状态码 |
| ERROR | 子→主 | 错误信息、堆栈跟踪 |
| CANCEL | 主→子 | 取消任务请求 |

### 6. 生命周期管理

```
创建 → 初始化 → 执行 → 完成/失败 → 销毁

状态转换：
CREATE    → INIT     (分配资源、加载配置)
INIT      → RUNNING  (开始执行)
RUNNING   → COMPLETE (正常完成)
RUNNING   → FAILED   (执行失败)
RUNNING   → CANCELLED (被取消)
*         → DESTROY  (清理资源)
```

## 模块结构

```
core/apps/agents/
├── subagent/
│   ├── __init__.py
│   ├── config.py        # Subagent 配置定义
│   ├── registry.py      # Subagent 注册表
│   ├── executor.py      # Subagent 执行器
│   ├── coordinator.py   # 协调器模式
│   └── message.py       # 通信协议
└── multi_agent.py       # 更新 - 集成 Subagent
```

## 核心组件

### SubagentConfig

```python
@dataclass
class SubagentConfig:
    name: str
    description: str
    type: str = "subagent"
    
    # 工具权限
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    
    # 系统提示
    system_prompt: str = ""
    
    # 执行配置
    timeout: int = 300
    max_retries: int = 3
    
    # 资源限制
    max_context_tokens: int = 100000
    max_tools_per_task: int = 50
```

### SubagentRegistry

管理所有 Subagent 注册：
- 注册/注销 Subagent
- 查询可用 Subagent
- 工具兼容性检查

### SubagentCoordinator

协调器实现：
- 任务分解和派发
- 并行/顺序执行策略
- 结果聚合和冲突处理

## 使用方式

### 1. 注册 Subagent

```python
from core.apps.agents.subagent import SubagentRegistry, SubagentConfig

registry = SubagentRegistry()

# 注册安全审查 Subagent
config = SubagentConfig(
    name="secure-reviewer",
    description="安全审计专家",
    allowed_tools=["Read", "Grep", "Glob"],
    denied_tools=["Write", "Edit", "Bash"],
    system_prompt="你是安全审计专家..."
)
registry.register(config)
```

### 2. 协调器派发任务

```python
from core.apps.agents.subagent import SubagentCoordinator

coordinator = SubagentCoordinator()

# 并行执行多个 Subagent
results = await coordinator.execute_parallel(
    task="审查这个 PR",
    subagents=["secure-reviewer", "test-engineer", "doc-writer"]
)

# 汇总结果
final_report = coordinator.aggregate_results(results)
```

### 3. 动态创建 Subagent

```python
# 根据任务动态创建临时 Subagent
temp_agent = await coordinator.create_subagent(
    name="temp-debugger",
    tools=["Read", "Edit"],
    purpose="修复特定 bug"
)
```

## 与现有系统集成

### 与 Skills 集成

Subagent 可预加载特定 Skill：

```python
# 审查 Subagent 预加载 code-review Skill
reviewer = SubagentConfig(
    name="code-reviewer",
    skills=["code-review", "security-scan"]
)
```

### 与 Tools 集成

Tool 执行前检查 Subagent 权限：

```python
# 在 ToolExecutor 中集成权限检查
def can_execute(subagent: Subagent, tool: str) -> bool:
    if tool in subagent.config.denied_tools:
        return False
    if subagent.config.allowed_tools and tool not in subagent.config.allowed_tools:
        return False
    return True
```

### 与 Memory 集成

每个 Subagent 有独立记忆空间：

```python
# Subagent 独立记忆
subagent_memory = {
    "short_term": deque(maxlen=20),  # 滑动窗口
    "long_term": VectorStore()         # 长期记忆
}
```

## 内置 Subagent 示例

| Subagent | 工具权限 | 用途 |
|----------|----------|------|
| secure-reviewer | Read, Grep, Glob | 安全审查（只读） |
| debugger | Read, Edit | 代码调试（可修改） |
| test-engineer | Read, Write, Bash | 测试编写（可创建） |
| documentation-writer | Read, Write | 文档生成 |
| performance-analyzer | Read, Grep | 性能分析 |
| refactor-agent | Read, Write, Edit, Bash | 重构执行 |

## 错误处理

| 错误类型 | 处理策略 |
|----------|----------|
| 工具权限不足 | 返回错误，继续其他 Subagent |
| 执行超时 | 重试 max_retries 次后标记失败 |
| 子 Agent 崩溃 | 记录错误，返回部分结果 |
| 结果冲突 | 协调器进行优先级裁决 |

## 待实现

- [ ] core/apps/agents/subagent/ 模块实现
- [ ] SubagentRegistry 实现
- [ ] SubagentCoordinator 实现
- [ ] 工具权限检查集成
- [ ] 与 Skills 系统集成
- [ ] 内置 Subagent 定义