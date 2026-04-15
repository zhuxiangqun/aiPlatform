# 渐进式披露机制设计

## 概述

本文档描述如何实现渐进式披露机制（Progressive Disclosure），让 AI 系统按需加载上下文，而非一次性加载全部内容。

## 目标

1. **按需加载上下文** - 仅加载当前任务所需的上下文
2. **目录摘要注入** - 自动生成并注入目录结构摘要
3. **智能上下文管理** - 基于任务类型动态调整上下文量
4. **减少上下文窗口浪费** - 优化 token 使用效率

## 现有组件

### ContextService (已实现)

位置: `core/services/context_service.py`

功能:
- 会话上下文管理 (SessionContext)
- 上下文生命周期 (创建、获取、更新、删除)
- TTL 和过期管理
- 上下文导出/导入

### FileService (已实现)

功能:
- 文件创建和存储
- 版本控制
- 文件模板

## 设计方案

### 1. 上下文加载策略

| 策略 | 描述 | 适用场景 |
|------|------|----------|
| `lazy` | 延迟加载，按需获取 | 大项目、复杂任务 |
| `eager` | 提前加载相关上下文 | 小项目、简单任务 |
| `adaptive` | 根据任务类型自适应 | 通用场景 |

### 2. 目录摘要注入

自动生成目录结构摘要，注入到上下文中:

```
project/
├── src/
│   ├── main.py
│   └── utils/
│       └── helper.py
├── tests/
├── docs/
└── README.md
```

生成摘要:
```
project/
├── src/ (2 files)
│   ├── main.py
│   └── utils/helper.py
├── tests/ (0 files)
├── docs/ (0 files)
└── README.md
```

### 3. 上下文优先级

根据文件类型和相关性设置优先级:

| 类型 | 优先级 | 说明 |
|------|--------|------|
| 当前文件 | P0 | 正在编辑的文件 |
| 关联文件 | P1 | import/引用关系 |
| 配置文件 | P2 | .env, config.yaml |
| 文档 | P3 | README, docs |
| 其他 | P4 | 剩余文件 |

### 4. 上下文裁剪

当上下文超限时，自动裁剪:

1. **压缩注释** - 保留功能，删除冗余注释
2. **合并相似文件** - 批量处理
3. **摘要代替全文** - 用摘要替换非关键文件
4. **延迟加载** - 标记待加载，后续按需加载

## 模块结构

```
core/harness/context/
├── __init__.py
├── loader.py         # ContextLoader
├── strategies.py     # 加载策略
├── summarizer.py     # 目录/文件摘要
├── priority.py       # 优先级管理
└── trimmer.py        # 上下文裁剪
```

### 核心组件

#### ContextLoader

```python
class ContextLoader:
    async def load(
        self,
        task: TaskSpec,
        strategy: LoadStrategy = LoadStrategy.ADAPTIVE
    ) -> LoadedContext:
        """按策略加载上下文"""
        pass
    
    async def load_file(self, path: str, priority: Priority) -> FileContext:
        """加载单个文件"""
        pass
    
    async def load_directory(self, root: str, max_depth: int) -> DirectorySummary:
        """加载目录摘要"""
        pass
```

#### DirectorySummarizer

```python
class DirectorySummarizer:
    async def summarize(
        self,
        root: str,
        max_depth: int = 2,
        include_patterns: List[str] = None
    ) -> DirectorySummary:
        """生成目录摘要"""
        pass
    
    def to_prompt(self, summary: DirectorySummary) -> str:
        """转换为 prompt 格式"""
        pass
```

#### ContextTrimmer

```python
class ContextTrimmer:
    def trim(
        self,
        context: LoadedContext,
        max_tokens: int
    ) -> TrimmedContext:
        """裁剪上下文到指定 token 数"""
        pass
```

## 使用方式

### 1. 自动按需加载

```python
from core.harness.context import ContextLoader, LoadStrategy

loader = ContextLoader()

# 自适应加载
context = await loader.load(
    task=TaskSpec(
        type="code_edit",
        target_file="src/main.py"
    ),
    strategy=LoadStrategy.ADAPTIVE
)
```

### 2. 手动指定加载范围

```python
# 仅加载当前文件和依赖
context = await loader.load(
    task=task,
    scope={
        "files": ["src/main.py"],
        "include_dependencies": True,
        "max_depth": 1
    }
)
```

### 3. 目录摘要注入

```python
summary = await loader.load_directory(".", max_depth=2)
prompt = summary.to_prompt()

# 注入到系统 prompt
system_prompt += f"\n## Project Structure\n{summary}"
```

### 4. 手动裁剪

```python
from core.harness.context import ContextTrimmer

trimmer = ContextTrimmer(max_tokens=8000)
trimmed = trimmer.trim(full_context, max_tokens=6000)
```

## 配置

```python
# 上下文加载配置
context_config = {
    "default_strategy": "adaptive",
    "max_tokens": 100000,
    "trim_threshold": 80000,
    "directory": {
        "max_depth": 2,
        "exclude_patterns": ["__pycache__", ".git", "node_modules"],
        "include_patterns": ["*.py", "*.js", "*.md"]
    },
    "priorities": {
        "current_file": 0,
        "dependencies": 1,
        "config": 2,
        "docs": 3,
        "other": 4
    }
}
```

## 与现有系统集成

### 与 ContextService 集成

```python
# ContextLoader 使用 ContextService 存储加载的上下文
loader = ContextLoader(context_service)
```

### 与 Agent 集成

```python
class ProactiveAgent:
    def __init__(self):
        self.context_loader = ContextLoader()
    
    async def think(self, task):
        # 按需加载上下文
        context = await self.context_loader.load(task)
        
        # 使用上下文
        return await self._execute(task, context)
```

### 与 Feedback 集成

```python
# 记录上下文加载统计
feedback.collector.add(
    FeedbackType.PERFORMANCE,
    FeedbackSeverity.LOW,
    "context_loader",
    f"Loaded {context.file_count} files, {context.token_count} tokens",
    metadata={"strategy": strategy.value}
)
```

## 实施计划

1. **Phase 1**: 实现 ContextLoader 基础框架
2. **Phase 2**: 实现 DirectorySummarizer
3. **Phase 3**: 实现优先级管理
4. **Phase 4**: 实现 ContextTrimmer
5. **Phase 5**: 与 Agent 集成

## 待实现

- [ ] core/harness/context/ 模块
- [ ] ContextLoader 实现
- [ ] DirectorySummarizer 实现
- [ ] 优先级管理
- [ ] 上下文裁剪
- [ ] 与 Agent 集成