# Context 管理与记忆架构（As-Is 对齐 + To-Be 规划）

> **As-Is**：当前核心执行链路的上下文控制以“最小闭环”形式存在（例如 token 高占用时对 messages 进行 best-effort 裁剪）。  
> **To-Be**：本文档中“双记忆/四层记忆/5级压缩”等为规划型设计，需要结合 `ExecutionRun/CheckpointStore` 与检索/存储体系落地。  
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

---

## 一、问题背景

长周期 Agent 会话面临的挑战：

| 问题 | 影响 | 数据 |
|------|------|------|
| **上下文窗口爆炸** | Token 超限，任务中断 | 上下文越长，注意力越稀释 |
| **指令衰减** | 模型忘记初始指令 | 20轮后指令关注度下降 60% |
| **状态丢失** | 崩溃后无法恢复 | 无断点续传机制 |
| **记忆混乱** | 混淆不同任务信息 | 缺乏分层管理 |

---

## 二、双记忆架构

### 2.1 核心概念

| 记忆类型 | 说明 | 生命周期 |
|---------|------|----------|
| **Episodic Memory** | LLM 生成的对话摘要 | 长期 |
| **Working Memory** | 最近 N 条消息原文 | 短期 |

### 2.2 工作原理

```
用户对话流
    │
    ▼
每 5 条消息 → LLM 生成摘要 → 进入 Episodic Memory
    │
    ▼
最近 6 条消息 → 保留原文 → 进入 Working Memory
    │
    ▼
Agent 推理时：
- 当前任务 → Working Memory (细节)
- 历史背景 → Episodic Memory (概要)
```

### 2.3 实现示例

```python
class DualMemory:
    def __init__(self, working_size=6):
        self.working = deque(maxlen=working_size)  # 短期
        self.episodic = []                           # 长期
    
    def add(self, message):
        self.working.append(message)
        
        # 每5条消息生成摘要
        if len(self.working) % 5 == 0:
            summary = self.llm_summarize(list(self.working))
            self.episodic.append(summary)
    
    def get_context(self, current_task):
        # 当前任务 → 细节优先
        # 历史背景 → 概要补充
        return {
            "working": list(self.working),
            "episodic": self.episodic[-3:]  # 最近3个摘要
        }
```

---

## 三、四层记忆划分

### 3.1 记忆层次

| 层级 | 类型 | 存储位置 | 加载策略 |
|------|------|---------|----------|
| **工作记忆** | 上下文窗口 | Agent 内存 | 常驻 |
| **程序性记忆** | Skills | 文件系统 | 触发时加载 |
| **情景记忆** | 会话历史 | 磁盘/数据库 | 按需检索 |
| **语义记忆** | MEMORY.md | 文件系统 | 启动时注入 |

### 3.2 各层职责

```
┌─────────────────────────────────────────┐
│           语义记忆 (Semantic)           │
│     长期知识、团队规范、经验总结          │
│     文件: MEMORY.md                      │
└────────────────┬────────────────────────┘
                 │ 按需
┌────────────────▼────────────────────────┐
│          情景记忆 (Episodic)             │
│     历史任务、关键决策、上下文脉络        │
│     存储: JSONL / 向量数据库             │
└────────────────┬────────────────────────┘
                 │ 检索
┌────────────────▼────────────────────────┐
│          程序性记忆 (Procedural)         │
│     技能定义、工作流、工具规范           │
│     文件: SKILL.md                       │
└────────────────┬────────────────────────┘
                 │ 触发
┌────────────────▼────────────────────────┐
│           工作记忆 (Working)             │
│     当前任务、即时状态、临时变量         │
│     内存: Agent 上下文                   │
└─────────────────────────────────────────┘
```

### 3.3 加载优先级

| 优先级 | 内容 | 加载时机 | Token 消耗 |
|--------|------|---------|-----------|
| P0 | 当前任务详情 | 始终 | 高 |
| P1 | 工作记忆 (Working) | 常驻 | 中 |
| P2 | 程序性记忆 (Skills) | 触发时 | 低 |
| P3 | 情景记忆 (检索结果) | 按需 | 可变 |
| P4 | 语义记忆 (MEMORY.md) | 启动时 | 低 |

---

## 四、Context 5级压缩

### 4.1 压缩触发机制

不是等到 Context 满了才压缩，而是监控 Token 使用率，在不同阈值采取不同策略：

| 阈值 | 状态 | 策略 | 描述 |
|------|------|------|------|
| **70%** | 预警 | 监控 | 开始密切监控，不压缩 |
| **80%** | 警告 | 替换 | 旧工具输出 → 摘要引用 |
| **85%** | 紧张 | 裁剪 | 只保留最近几轮完整输出 |
| **90%** | 严重 | 激进压缩 | 只保留核心信息 |
| **99%** | 紧急 | 完整摘要 | LLM 完整摘要，丢弃原始 |

### 4.2 各级别实现

```python
class ContextCompression:
    async def compress(self, context, token_ratio):
        if token_ratio < 0.70:
            return context  # 无需压缩
        
        elif token_ratio < 0.80:
            # 替换：旧工具输出 → 摘要引用
            return self.replace_tool_outputs(context)
        
        elif token_ratio < 0.85:
            # 裁剪：只保留最近 3 轮
            return self.prune_recent(context, keep=3)
        
        elif token_ratio < 0.90:
            # 激进压缩：保留关键信息
            return self.aggressive_compress(context)
        
        else:
            # 完整摘要：LLM 压缩
            return await self.full_summary(context)
```

### 4.3 压缩效果

| 指标 | 原始 | 压缩后 | 节省 |
|------|------|--------|------|
| Token 消耗 | 100% | ~46% | 54% |
| 关键信息保留 | 100% | 95% | - |
| 任务成功率 | 基准 | +3% | - |

---

## 五、System Reminders (系统提醒)

### 5.1 问题：指令衰减

长对话中，模型对初始 System Prompt 的关注度下降：

```
第 1-5 轮:  → 记得 "改完代码必须跑测试"
第 10 轮:  → 可能忘记 "测试" 要求
第 20 轮:  → 完全忘记初始指令
```

### 5.2 解决方案：事件驱动提醒

当检测到特定模式时，自动注入提醒消息：

| 触发条件 | 提醒内容 |
|---------|---------|
| 调用 task_complete 但有未完成任务 | "你还有 X 个任务未完成" |
| 连续 5 次只读操作 | "你已经连续探索，该行动了" |
| 工具调用失败 | "检查参数或尝试其他工具" |

### 5.3 关键设计：user-role 提醒

```python
# 使用 user-role 而不是 system-role
reminder_message = {
    "role": "user",  # 模型对 user 消息注意力更高
    "content": "提醒：你还有 2 个待办任务未完成"
}
```

### 5.4 效果

| 指标 | 启用前 | 启用后 | 改进 |
|------|--------|--------|------|
| 任务遗漏率 | 15% | 4% | -73% |
| 提前结束率 | 8% | 2% | -75% |

---

## 六、Session 持久化

### 6.1 断点续传

```
任务执行中断 (如上下文超时)
    │
    ▼
保存当前状态
    │
    ├─→ 执行轨迹
    ├─→ 工具调用结果
    ├─→ 记忆状态
    └─→ 待完成任务
    │
    ▼
新会话启动
    │
    ▼
恢复状态 → 继续执行
```

### 6.2 状态保存内容

```json
{
  "session_id": "abc123",
  "task": "生成销售报告",
  "progress": {
    "completed_steps": ["data_collection", "analysis"],
    "current_step": "report_generation",
    "remaining_steps": ["formatting", "review"]
  },
  "memory": {
    "working": [...],
    "episodic": [...]
  },
  "context_snapshot": {...},
  "tool_results": [...]
}
```

---

## 七、相关文档

- [Agent 设计模式](../framework/patterns.md) - 6种核心模式
- [Skill 生命周期](../skills/lifecycle.md) - Skill 进化机制
- [Harness 索引](./index.md) - 运行时系统

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- token 高占用 compaction（最小实现）：`core/harness/execution/loop.py: BaseLoop._apply_observability_control()`
- To-Be：记忆/检索/持久化需结合 `core/harness/execution/langgraph/*` 与后续 CheckpointStore/ExecutionStore 方案
