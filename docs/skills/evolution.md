# Skill 动态进化设计

## 概述

本文档描述如何实现 Skill 的自动进化机制，使 Agent 能够从执行经验中自动学习、修复和衍生新技能，告别静态 Skill 配置，实现"越用越聪明"的动态 Skill 系统。

## 背景

当前 Skill 系统的局限：
- **静态配置**：SKILL.md 写好后不会自动更新
- **被动维护**：依赖人工发现并修复问题
- **无法复用**：成功经验无法自动沉淀
- **工具退化**：外部 API 更新导致 Skill 失效

OpenSpace 的核心洞察：Skill 应该是有生命周期的"活"实体，可以被自动捕获、自动修复、自动衍生。

## 目标

1. **自动捕获** - 从成功执行中提取可复用模式
2. **自动修复** - 工具失败时自动修复 Skill
3. **自动衍生** - 场景不匹配时自动派生新分支
4. **版本追溯** - 完整的进化血缘记录
5. **跨 Agent 共享** - 进化成果可共享给其他 Agent

## 现有组件

### BaseSkill (已存在)

位置: `core/apps/skills/base.py`

功能:
- Skill 基类实现
- SkillMetadata 定义
- 参数验证

### SkillRegistry (已存在)

位置: `core/apps/skills/registry.py`

功能:
- Skill 注册和管理
- Skill 发现和检索
- 依赖解析

## 设计方案

### 1. 三种进化模式

| 模式 | 触发条件 | 操作 | 示例 |
|------|----------|------|------|
| **FIX** | Skill 执行失败 | 原地修复，版本号递增 | 代码审查 Skill 报错 → 修复提示词 |
| **DERIVED** | 现有 Skill 无法覆盖场景 | 新建分支，与父 Skill 共存 | 通用文档生成 → 法律文书专用版本 |
| **CAPTURED** | 执行中发现新模式 | 全新 Skill，无父级 | 一次性调试技巧 → 可复用 Skill |

### 2. 进化触发器

#### 触发器一：Post-Execution Analysis（任务后分析）

每次任务完成后，LLM 分析执行记录，提出进化建议：

```
分析内容：
- 执行成功/失败原因
- 暴露的改进点
- 可复用的成功模式
- 建议的进化类型（FIX/DERIVED/CAPTURED）
```

#### 触发器二：Tool Degradation Detection（工具退化检测）

监控系统监控工具成功率：

```
检测逻辑：
1. 监控工具调用成功率
2. 成功率下降 > 20% 时触发
3. 找到所有依赖该工具的 Skill
4. 批量触发进化修复
```

#### 触发器三：Metric Monitor（指标监控）

周期性扫描 Skill 健康指标：

```
监控指标：
- 应用率（被选中次数 / 被检索次数）
- 成功率（执行成功 / 执行总数）
- 回退率（进化后性能下降）
- 过期率（依赖的工具已过时）
```

### 3. 版本血缘（DAG）

每个 Skill 版本形成有向无环图：

```
document-gen-fallback v1.0 (导入)
    │
    ├── FIX v1.1 (修复输出格式)
    │
    └── DERIVED v2.0 (法律文书版)
            │
            ├── DERIVED v2.1 (加州隐私法)
            │
            └── DERIVED v2.2 (联邦法规)
```

存储结构：
```python
@dataclass
class SkillVersion:
    version: str          # e.g., "v1.1"
    parent: str           # 父版本 ID
    evolution_type: str   # FIX/DERIVED/CAPTURED
    trigger: str         # 触发原因
    content_hash: str   # 内容哈希
    created_at: datetime
    diff: str            # 与父版本的差异
```

### 4. 存储机制

使用 SQLite + WAL 模式：

```sql
-- Skill 表
CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 版本表
CREATE TABLE skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT REFERENCES skills(id),
    version TEXT NOT NULL,
    parent_version TEXT,
    evolution_type TEXT,  -- FIX/DERIVED/CAPTURED
    trigger TEXT,
    content_hash TEXT,
    diff TEXT,
    created_at TIMESTAMP
);

-- 进化触发记录
CREATE TABLE evolution_triggers (
    id TEXT PRIMARY KEY,
    skill_id TEXT REFERENCES skills(id),
    trigger_type TEXT,  -- post_exec/tool_degradation/metric
    status TEXT,       -- pending/running/completed/failed
    suggestion TEXT,
    created_at TIMESTAMP
);
```

### 5. 自动捕获流程（CAPTURED）

从成功执行中捕获新 Skill：

```
步骤：
1. 任务执行成功
2. LLM 分析执行轨迹
3. 判断是否有可复用模式
4. 生成 Skill 雏形（SKILL.md）
5. 验证有效性
6. 注册到 SkillRegistry
```

捕获判定条件：
- 相同的解决思路可用于 ≥3 个不同任务
- 包含明确的输入→输出模式
- 不依赖特定任务上下文

### 6. 自动修复流程（FIX）

工具失败时触发修复：

```
步骤：
1. 工具调用失败
2. 记录失败上下文
3. 分析失败原因
4. 生成修复建议
5. 应用修复
6. 验证修复有效
7. 更新版本号
```

### 7. 衍生流程（DERIVED）

场景不匹配时派生新分支：

```
判定条件：
- 现有 Skill 输出无法满足场景要求
- 场景特殊性无法通过修改解决
- 需要不同的工具或工作流

操作：
1. 创建新 Skill 目录
2. 复制父 Skill 内容
3. 修改场景相关内容
4. 标记父子关系
5. 注册新 Skill
```

### 8. 防无限进化机制

| 机制 | 描述 |
|------|------|
| 冷却期 | 同一 Skill 进化后 24 小时内不再触发 |
| 最大版本数 | 单个 Skill 最多 50 个版本 |
| 人工审批 | 高风险进化（删除大量内容）需审批 |
| 回滚机制 | 进化后性能下降 > 10% 自动回滚 |

## 模块结构

```
core/apps/skills/
├── evolution/
│   ├── __init__.py
│   ├── engine.py         # 进化引擎
│   ├── triggers.py      # 三触发器
│   ├── lineage.py        # 版本血缘管理
│   ├── capture.py        # 自动捕获
│   ├── fix.py            # 自动修复
│   └── derive.py         # 衍生分支
└── registry.py          # 更新 - 集成进化
```

## 核心组件

### SkillEvolutionEngine

```python
class SkillEvolutionEngine:
    """Skill 进化引擎"""
    
    async def trigger_evolution(
        self,
        skill_id: str,
        trigger_type: TriggerType,
        context: Dict
    ) -> EvolutionResult:
        """触发进化"""
        pass
    
    async def analyze_execution(
        self,
        execution_record: ExecutionRecord
    ) -> List[EvolutionSuggestion]:
        """分析执行记录，生成进化建议"""
        pass
    
    async def apply_fix(
        self,
        skill: Skill,
        error: ToolError
    ) -> Skill:
        """应用修复"""
        pass
```

### TriggerManager

```python
class TriggerManager:
    """触发器管理器"""
    
    def __init__(self):
        self._triggers = {
            TriggerType.POST_EXEC: PostExecutionTrigger(),
            TriggerType.TOOL_DEGRADATION: ToolDegradationTrigger(),
            TriggerType.METRIC: MetricMonitorTrigger()
        }
    
    async def check_and_trigger(self) -> List[EvolutionRequest]:
        """检查所有触发器，返回待处理请求"""
        pass
```

### VersionLineage

```python
class VersionLineage:
    """版本血缘管理"""
    
    async def create_version(
        self,
        skill_id: str,
        parent_version: str,
        evolution_type: str,
        content: str
    ) -> SkillVersion:
        """创建新版本"""
        pass
    
    async def get_lineage(self, skill_id: str) -> List[SkillVersion]:
        """获取完整血缘"""
        pass
    
    async def rollback(self, skill_id: str, version: str) -> bool:
        """回滚到指定版本"""
        pass
```

## 进化判定规则

### FIX 判定

```python
def should_fix(skill: Skill, error: ToolError) -> bool:
    """判断是否应该执行 FIX"""
    return (
        error.is_recoverable and          # 可恢复错误
        error.root_cause_in_skill and     # 根因在 Skill
        fix_cost < rebuild_cost           # 修复成本 < 重写成本
    )
```

### DERIVED 判定

```python
def should_derive(skill: Skill, context: TaskContext) -> bool:
    """判断是否应该执行 DERIVED"""
    return (
        skill.output_mismatch(context) and       # 输出不匹配
        not fix_applicable(skill, context) and   # 修复不适用
        unique_scenario(context)                  # 独特场景
    )
```

### CAPTURED 判定

```python
def should_capture(execution: ExecutionRecord) -> bool:
    """判断是否应该执行 CAPTURED"""
    return (
        execution.success and
        pattern_reusable(execution) and
        not already_in_skills(execution.pattern) and
        sufficient_samples(execution.pattern, min=3)
    )
```

## 性能指标

| 指标 | 目标值 |
|------|--------|
| 自动捕获率 | > 30% 的可复用模式被捕获 |
| 修复成功率 | > 80% 的工具退化问题被修复 |
| 衍生有效性 | > 70% 的衍生 Skill 被实际使用 |
| Token 节省 | > 40% 的重复任务 token 消耗降低 |

## 与现有系统集成

### 与 Tool 系统集成

工具执行失败时触发修复：

```python
# ToolExecutor 中集成
async def execute(self, tool: Tool, params: Dict):
    try:
        result = await tool.execute(params)
    except ToolError as e:
        # 触发 Skill 进化
        await evolution_engine.trigger_evolution(
            skill_id=find_skill_using_tool(tool.name),
            trigger_type=TriggerType.TOOL_DEGRADATION,
            context={"error": e}
        )
        raise
```

### 与 Memory 系统集成

进化触发时记录上下文：

```python
# 保存用于捕获的上下文
await memory.save(
    key=f"execution:{execution_id}",
    value=execution_record.to_dict(),
    ttl=7 * 24 * 3600  # 7 天
)
```

### 与 Quality Gate 集成

进化前验证有效性：

```python
# 进化前运行质量门禁
result = await quality_gate.check(evolved_skill)
if not result.passed:
    logger.warning(f"进化质量不通过: {result.message}")
    # 不应用进化，或标记为待审批
```

## 使用方式

### 1. 启用自动进化

```python
from core.apps.skills.evolution import SkillEvolutionEngine

engine = SkillEvolutionEngine()

# 启用所有触发器
await engine.enable_all_triggers()

# 或只启用特定触发器
await engine.enable_trigger(TriggerType.POST_EXEC)
```

### 2. 手动触发修复

```python
# 手动触发 Skill 修复
result = await engine.trigger_evolution(
    skill_id="code-review",
    trigger_type=TriggerType.TOOL_DEGRADATION,
    context={"tool": "eslint", "error": "ESLint API changed"}
)
```

### 3. 查看进化历史

```python
# 获取 Skill 进化历史
lineage = await version_lineage.get_lineage("code-review")

for version in lineage:
    print(f"{version.version} ({version.evolution_type}) - {version.trigger}")
```

### 4. 回滚版本

```python
# 回滚到指定版本
await version_lineage.rollback("code-review", "v1.5")
```

## UI/CLI 支持

### 查看进化状态

```bash
# 查看所有 Skill 进化状态
aiplat skills evolution status

# 查看特定 Skill 进化历史
aiplat skills evolution history code-review
```

### 手动触发

```bash
# 手动触发进化
aiplat skills evolution trigger code-review --type=metric

# 强制捕获
aiplat skills evolution capture --execution-id=xxx
```

## 待实现

- [ ] core/apps/skills/evolution/ 模块实现
- [ ] PostExecutionTrigger 实现
- [ ] ToolDegradationTrigger 实现
- [ ] MetricMonitorTrigger 实现
- [ ] VersionLineage 实现（SQLite + DAG）
- [ ] 与 ToolExecutor 集成
- [ ] CLI 命令支持
- [ ] 进化可视化面板