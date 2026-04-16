# 记忆系统 (Memory)（设计真值：以代码事实为准）

> 说明：本文档描述 Harness 的 Memory 子系统（`core/harness/memory/*`）。  
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

> 记忆系统负责智能体的短期记忆和长期记忆管理，支持上下文保持和经验积累。

---

## 模块定位

Memory 模块为 Agent 提供记忆存储和检索能力，是 Harness 框架的核心组件之一。

**代码位置**：`core/harness/memory/`

**核心能力**：
- 记忆存储与检索
- 记忆压缩与摘要
- 记忆遗忘与清理
- 记忆迁移与同步
- 记忆分析与统计

---

## 模块结构

```
harness/memory/
├── __init__.py              # 模块入口
├── base.py                  # 记忆基类 (MemoryBase, MemoryEntry)
├── manager.py               # 统一记忆管理器 (三层记忆整合)
├── short_term.py            # 短期记忆 (ShortTermMemory)
├── long_term.py             # 长期记忆 (LongTermMemory)
├── session.py               # 会话管理 (SessionManager)
├── langchain_adapter.py     # LangChain 适配器
├── working.py               # 工作记忆 (当前任务上下文)
├── episodic.py              # 情景记忆 (会话历史摘要)
├── semantic.py              # 语义记忆 (向量存储的长期知识)
├── compression.py           # 上下文压缩 (Token 优化)
└── reminders.py             # 系统提醒 (指令衰减防护)
```

## 核心组件

### 1. MemoryManager - 统一记忆管理器

> 整合 Working、Episodic、Semantic 三层记忆的统一入口

**位置**：`manager.py`

**功能**：
- 构建完整上下文（三层记忆整合）
- 保存交互记录
- 语义记忆捕获
- 上下文压缩触发
- 系统提醒注入

**核心方法**：

| 方法 | 功能 |
|------|------|
| `build_context()` | 从所有记忆层构建完整上下文 |
| `save_interaction()` | 保存交互到工作记忆和情景记忆 |
| `capture_to_semantic()` | 捕获重要信息到语义记忆 |

### 2. 三层记忆架构

| 记忆层 | 组件 | 功能 |
|--------|------|------|
| **工作记忆** | `working.py` | 当前任务细节、即时状态 |
| **情景记忆** | `episodic.py` | 会话历史摘要、关键决策 |
| **语义记忆** | `semantic.py` | 向量存储的长期知识 |

### 3. 上下文压缩

**位置**：`compression.py`

根据 Token 使用率触发不同级别压缩：

| 阈值 | 状态 | 压缩策略 |
|------|------|---------|
| 70% | 预警 | 监控，不压缩 |
| 80% | 警告 | 旧工具输出 → 摘要引用 |
| 85% | 紧张 | 只保留最近 3 轮 |
| 90% | 严重 | 激进压缩 |
| 99% | 紧急 | LLM 完整摘要 |

### 4. 系统提醒

**位置**：`reminders.py`

解决指令衰减问题，事件驱动注入提醒：

| 触发条件 | 提醒内容 |
|---------|---------|
| 有未完成任务但调用 task_complete | "你还有 X 个任务未完成" |
| 连续 5 次只读操作 | "你已经连续探索，该行动了" |
| 工具调用失败 | "检查参数或尝试其他工具" |

## 核心概念

| 概念 | 说明 |
|------|------|
| **Memory** | 记忆，是智能体在执行过程中积累的信息 |
| **ShortTermMemory** | 短期记忆，存储当前会话的上下文信息 |
| **LongTermMemory** | 长期记忆，存储跨会话的经验和知识 |
| **MemoryStore** | 记忆存储，负责记忆的持久化 |
| **MemoryRetriever** | 记忆检索，负责从记忆中检索相关信息 |

---

## 记忆类型

| 类型 | 说明 |
|------|------|
| **对话记忆** | 存储对话历史，支持多轮对话 |
| **执行记忆** | 存储执行历史，支持任务恢复 |
| **经验记忆** | 存储成功/失败案例，支持学习 |
| **知识记忆** | 存储外部知识，支持知识增强 |

---

## 设计原则

- 短期记忆应该快速访问，长期记忆应该持久可靠
- 记忆应该支持按相关性检索
- 记忆应该支持自动过期清理
- 记忆应该支持跨会话共享

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **harness** | 使用 Harness 的记忆接口 |
| **agents** | Agent 使用记忆存储上下文 |
| **services** | 公共服务支持记忆管理 |

---

## 相关文档

- [Harness 索引](../harness/index.md) - 智能体框架
- [Context 管理](../harness/context.md) - 上下文压缩与双记忆架构
- [渐进式披露](../harness/progressive-disclosure.md) - 记忆加载策略

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- Memory 模块：`core/harness/memory/*`
- MemoryManager：`core/harness/memory/manager.py`
- Compression：`core/harness/memory/compression.py`
