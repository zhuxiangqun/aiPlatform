# 渐进式披露机制

> 实现按需加载上下文与条件触发，构建高效的记忆调度系统

---

## 一句话定义

**渐进式披露机制**通过 ContextLoader 按需加载、ProgressiveDisclosurePolicy 分层策略、TaskComplexityAnalyzer 复杂度分析，实现 Agent 只在需要时获取必要信息——避免上下文膨胀同时保证任务完成质量。

---

## 核心概念

### 当前系统已有能力

| 能力 | 实现位置 | 状态 |
|------|---------|------|
| Context 5级压缩 | services/context_service.py | ✅ 已实现 |
| 四层记忆划分 | docs/harness/context.md | ✅ 已实现 |
| Skill 按需加载 | apps/skills/discovery.py | ✅ 已实现 |
| references 按需加载 | apps/skills/loader.py | ✅ 部分实现 |

### 新增能力

| 能力 | 说明 | 优先级 |
|------|------|--------|
| **ContextLoader** | 统一上下文加载器 | P0 |
| **ProgressiveDisclosurePolicy** | 分层披露策略 | P0 |
| **TaskComplexityAnalyzer** | 任务复杂度分析 | P1 |
| **条件触发器** | references/scripts 条件加载 | P1 |
| **记忆优先级调度** | 自适应加载优先级 | P2 |

---

## ContextLoader 设计

### 按需加载架构

```python
class ContextLoader:
    """统一上下文加载器"""
    
    async def load(
        self, 
        context_type: ContextType,
        urgency: LoadingUrgency,
        task: Optional[Task] = None
    ) -> ContextData:
        """
        参数:
            context_type: 上下文类型 (memory | skill | reference | tool)
            urgency: 加载紧急度 (critical | normal | low)
            task: 当前任务上下文
        """
        
    async def load_references(
        self, 
        skill_name: str, 
        urgency: LoadingUrgency
    ) -> Dict[str, Any]:
        """按需加载 references"""
        
    async def load_scripts(
        self, 
        skill_name: str, 
        trigger: Trigger
    ) -> List[str]:
        """条件加载 scripts"""
```

### LoadingUrgency 枚举

```python
class LoadingUrgency(Enum):
    """加载紧急度"""
    CRITICAL = "critical"    # 立即需要
    NORMAL = "normal"       # 正常加载
    LOW = "low"             # 后台预加载
```

---

## 渐进式披露策略

### ProgressiveDisclosurePolicy

```python
class ProgressiveDisclosurePolicy(Enum):
    """渐进式披露策略"""
    
    MINIMAL = "minimal"  # 仅元数据
    STANDARD = "standard" # 标准加载
    FULL = "full"       # 完整加载
```

### 策略详情

| 策略 | 加载内容 | Token 消耗 | 适用场景 |
|------|---------|-----------|----------|
| **MINIMAL** | SKILL.md metadata only | ~100 | 快速探索、任务识别 |
| **STANDARD** | metadata + handler + common refs | ~500 | 常规任务执行 |
| **FULL** | 全部加载 | ~2000+ | 复杂任务/调试 |

### 策略选择规则

```python
def select_policy(task: Task, context: ContextState) -> ProgressiveDisclosurePolicy:
    """根据任务和上下文状态选择披露策略"""
    
    # 任务复杂度高 → FULL
    if task.complexity > COMPLEXITY_THRESHOLD:
        return ProgressiveDisclosurePolicy.FULL
        
    # 上下文已满 → MINIMAL
    if context.usage_ratio > 0.9:
        return ProgressiveDisclosurePolicy.MINIMAL
        
    # 常规任务 → STANDARD
    return ProgressiveDisclosurePolicy.STANDARD
```

---

## 任务复杂度分析

### TaskComplexityAnalyzer

```python
class TaskComplexityAnalyzer:
    """任务复杂度分析器"""
    
    async def analyze(self, task: Task) -> ComplexityReport:
        """
        分析任务复杂度，返回:
        - complexity_score: 0-100
        - factors: 复杂度因素
        - recommended_policy: 建议披露策略
        """
        
    def _calculate_score(self, task: Task) -> int:
        """计算复杂度分数"""
        score = 0
        
        # 代码行数影响
        score += min(task.estimated_lines / 100, 20)
        
        # 依赖数量影响
        score += min(len(task.dependencies) * 5, 20)
        
        # 工具调用影响
        score += min(len(task.tool_calls) * 10, 30)
        
        # 跨文件影响
        score += min(len(task.affected_files) * 5, 20)
        
        # 测试需求影响
        if task.requires_tests:
            score += 10
            
        return min(int(score), 100)
```

### 复杂度因素

| 因素 | 影响 | 阈值 |
|------|------|------|
| 代码行数 | + | >1000 行 +20 |
| 依赖数量 | + | >5 个依赖 +20 |
| 工具调用数 | + | >3 个工具 +30 |
| 跨文件数 | + | >10 个文件 +20 |
| 测试需求 | + | 需测试 +10 |

---

## 条件触发器

### Trigger 类型

```python
class Trigger(Enum):
    """加载触发条件"""
    
    # Skill 触发
    SKILL_INVOKED = "skill_invoked"
    SKILL_COMPLETED = "skill_completed"
    
    # 工具触发
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    
    # 任务触发
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    
    # 上下文触发
    CONTEXT_NEAR_FULL = "context_near_full"
    CONTEXT_FULL = "context_full"
```

### 条件加载示例

```python
# Skill references 条件加载
class ConditionalReferenceLoader:
    """条件引用加载器"""
    
    async def should_load(
        self,
        reference_name: str,
        context: ContextState,
        task: Task
    ) -> bool:
        """判断是否需要加载引用"""
        
        # 低内存时不加载大型引用
        if context.usage_ratio > 0.85:
            ref_size = self._get_reference_size(reference_name)
            if ref_size > 100_000:  # > 100KB
                return False
                
        # 任务完成后不加载新引用
        if task.status == TaskStatus.COMPLETED:
            return False
            
        return True
```

---

## 记忆优先级调度

### AdaptiveMemoryScheduler

```python
class AdaptiveMemoryScheduler:
    """自适应记忆调度器"""
    
    async def schedule(self, task: Task) -> MemoryPriority:
        """
        根据任务返回记忆优先级配置
        """
        
@dataclass
class MemoryPriority:
    """记忆优先级配置"""
    working_memory: int   # 工作记忆保留轮数
    episodic_retrieval: int # 情景记忆检索数量
    semantic_injection: bool # 是否注入语义记忆
    skill_loading: str       # Skill 加载策略
```

### 优先级规则

| 任务类型 | 工作记忆 | 情景记忆 | 语义记忆 | Skill 加载 |
|---------|---------|---------|---------|------------|
| **简单查询** | 2 轮 | 3 条 | 关闭 | MINIMAL |
| **常规开发** | 6 轮 | 10 条 | 开启 | STANDARD |
| **复杂重构** | 10 轮 | 20 条 | 开启 | FULL |
| **调试排查** | 15 轮 | 50 条 | 开启 | FULL |

---

## 与现有系统集成

### Context Service 集成

```python
class ContextService:
    """集成渐进式披露的上下文服务"""
    
    def __init__(self):
        self._loader = ContextLoader()
        self._scheduler = AdaptiveMemoryScheduler()
        self._analyzer = TaskComplexityAnalyzer()
        
    async def prepare_context(
        self, 
        task: Task,
        available_tokens: int
    ) -> PreparedContext:
        """准备任务上下文"""
        
        # 分析任务复杂度
        complexity = await self._analyzer.analyze(task)
        
        # 选择披露策略
        policy = select_policy(task, self._current_state)
        
        # 调度记忆优先级
        priority = await self._scheduler.schedule(task)
        
        # 按策略加载内容
        context = await self._loader.load_for_policy(
            policy, 
            task,
            priority
        )
        
        return context
```

### 与 Skill 系统集成

```python
class SkillLoader:
    """集成渐进式披露的 Skill 加载器"""
    
    async def load_skill(
        self,
        skill_name: str,
        disclosure: ProgressiveDisclosurePolicy
    ) -> DiscoveredSkill:
        """根据披露策略加载 Skill"""
        
        if disclosure == ProgressiveDisclosurePolicy.MINIMAL:
            # 只加载元数据
            return await self._load_metadata_only(skill_name)
            
        elif disclosure == ProgressiveDisclosurePolicy.STANDARD:
            # 加载元数据 + handler + 常用引用
            return await self._load_standard(skill_name)
            
        else:  # FULL
            # 加载全部
            return await self._load_full(skill_name)
```

---

## 配置示例

```yaml
# config/progressive-disclosure.yaml
progressive_disclosure:
  # 默认策略
  default_policy: "standard"
  
  # 复杂度阈值
  complexity:
    low: 30
    medium: 60
    high: 80
    
  # 上下文预算
  context_budget:
    max_tokens: 80000
    warning_threshold: 0.7
    critical_threshold: 0.9
    
  # 记忆调度
  memory:
    working_memory:
      min_rounds: 2
      max_rounds: 20
      adaptive: true
      
    episodic:
      min_items: 3
      max_items: 50
      retrieval_weight: 0.6
      
    semantic:
      enabled: true
      injection_threshold: 0.6
      
  # 条件加载
  conditional:
    large_reference_threshold: 100000  # 100KB
    skip_on_context_full: true
    background_preload: true
    
  # 策略切换
  policy_switch:
    auto_upgrade_on_complexity: true
    auto_downgrade_on_full: true
    downgrade_delay_seconds: 5
```

---

## 相关文档

- [Context 管理](./context.md) - 现有 Context 机制
- [Skill 生命周期](./skills/lifecycle.md) - Skill 进化机制
- [工具系统](./tools/index.md) - 工具接口

---

*最后更新: 2026-04-14*