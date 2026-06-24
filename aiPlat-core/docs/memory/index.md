# 记忆系统 (Memory)（设计真值：以代码事实为准）

> 说明：本文档描述 Harness 的 Memory 子系统（`core/harness/memory/*`）。
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

> 记忆系统负责智能体的短期记忆和长期记忆管理，支持上下文保持和经验积累。

---

## 模块定位

Memory 模块为 Agent 提供记忆存储和检索能力，是 Harness 框架的核心组件之一。

**代码位置**：`core/harness/memory/`

**核心能力**：
- 四层记忆架构（Working → Episodic → Semantic → Task Skills）
- 5 级上下文压缩（含工具输出预算帽）
- 语义记忆动态续期 + 软删除
- 记忆投毒防御（来源标签 + 信任加权 + 溯源）
- Episodic 预评分 + 关键决策永保
- 记忆迁移与同步
- 记忆分析与统计

---

## 模块结构

```
harness/memory/
├── __init__.py              # 模块入口
├── base.py                  # 记忆基类 (MemoryBase, MemoryEntry)
├── manager.py               # 统一记忆管理器 (四层记忆整合)
├── short_term.py            # 短期记忆 (ShortTermMemory, TTL 1h)
├── long_term.py             # 长期记忆 (LongTermMemory, TTL 30d)
├── session.py               # 会话管理 (SessionManager)
├── working.py               # 工作记忆 (deque滑动窗口, 30K token)
├── episodic.py              # 情景记忆 (会话摘要 + importance_score预评分)
├── semantic.py              # 语义记忆 (向量存储 + 动态续期 + 软删除)
├── compression.py           # 上下文压缩 (5级策略 + TOOL_OUTPUT_BUDGET)
├── reminders.py             # 系统提醒 (指令衰减防护)
├── profile_builder.py       # 用户画像 (结构化卡片, 原地更新)
└── shared_memory.py         # 跨实例共享记忆 (置信度去重)
```

## 核心组件

### 1. MemoryManager - 统一记忆管理器

> 整合 Working、Episodic、Semantic、Task Skills 四层记忆的统一入口

**位置**：`manager.py`

**功能**：
- 构建完整上下文（四层记忆整合 + critical_episodes注入）
- 保存交互记录（stability分级：high→语义, medium→情景, low→仅工作）
- 语义记忆捕获（含 expires_at TTL控制）
- 后台 Episodic 重要性评分（零阻塞热路径）
- 上下文压缩触发
- 系统提醒注入

**核心方法**：

| 方法 | 功能 |
|------|------|
| `build_context()` | 从所有记忆层构建完整上下文（含critical_episodes） |
| `save_interaction()` | 保存交互，支持 stability + is_critical 标记 |
| `capture_to_semantic()` | 捕获重要信息到语义记忆（含 expires_at） |
| `cleanup_semantic_expired()` | 软删除过期低频语义记忆 |

### 2. 四层记忆架构

| 记忆层 | 组件 | 存储 | 功能 |
|--------|------|------|------|
| **工作记忆 (Hot)** | `working.py` | deque 滑动窗口, 30K token | 当前任务上下文 |
| **情景记忆 (Warm)** | `episodic.py` | in-memory + critical_episodes | 会话摘要 + LLM预评分 + 关键决策永保 |
| **语义记忆 (Cold)** | `semantic.py` | SQLite + 向量 + FTS5 | 长期知识, 动态续期, 软删除, TTL驱动过期 |
| **任务技能 (External)** | `manager.py:TaskSkill` | JSON 文件 + SkillRegistry | 可复用执行模式, pass_rate≥85%自动晶体化 |

### 3. 上下文压缩 & 工具输出预算帽

**位置**：`compression.py`

根据 Token 使用率触发 5 级压缩，同时保护系统级上下文：

| 阈值 | 状态 | 压缩策略 |
|------|------|---------|
| <70% | 正常 | 不压缩 |
| 70-80% | 预警 | 监控 |
| 80-85% | 替换 | 旧工具输出→摘要（protected_roles永不压缩） |
| 85-90% | 裁剪 | 低优先级优先删除 |
| 90-99% | 激进 | 仅保留 system + 最后2条 |
| ≥99% | 紧急 | 仅保留 system + 最后1条 |

**工具输出预算帽**（方案一）：
- 输出≤2000字 → 原文通过
- 输出>2000字 → 占位符 + `asyncio.create_task(后台LLM摘要)`
- 摘要超时3s → 降级 `[TRUNCATED]`，不阻塞主流程
- 幽灵占位符防御：`finally`块确保 scratchpad 必有内容

### 4. 语义记忆过期 & 投毒防御

**位置**：`semantic.py`, `base.py`

**动态续期机制**（方案二）：
- 写入时 `expires_at = now + 7d`
- 每次 `search()` 命中 → `expires_at = max(expires_at, now + 7d)`（自动续命）
- 每日清理条件：`expired AND access_count < 3`
- **软删除**：设置 `is_deleted=1`，不物理删除
- 可通过 `sys_read_deleted_memory(id)` 恢复（强制 tenant+session 隔离）

**投毒防御字段**（MemoryEntry，方案二）：
| 字段 | 说明 |
|------|------|
| `source_tag` | 来源标签（user/system/agent/auto_learned） |
| `trust_weight` | 信任加权 0-1（1.0=fully trusted） |
| `provenance` | 溯源路径（pipeline_id/session_id/source_uri） |

### 5. Episodic 预评分 & 关键决策

**位置**：`episodic.py`

**写入时预评分**（方案三）：
- `save_interaction()` → `asyncio.create_task(_score_interactions(llm))` 后台打分
- 压缩时直接读 `importance_score`，零延迟
- `>0.8` 分 → 提升为 `critical_episode`，永不参与常规压缩
- `build_context()` 自动注入 critical episodes 到上下文

### 6. 系统提醒

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
| **MemoryEntry** | 记忆条目基类，含 source_tag/trust_weight/provenance |
| **WorkingMemory** | 工作记忆，deque滑动窗口，当前任务上下文 |
| **EpisodicMemory** | 情景记忆，会话摘要 + 预评分 + critical_episodes |
| **SemanticMemory** | 语义记忆，向量存储 + 动态续期 + 软删除 |
| **ContextCompression** | 上下文压缩，5级策略 + 工具输出预算帽 + protected_roles |

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

- 四层记忆按温度分层：Hot→Warm→Cold→External
- 短期记忆快速访问，长期记忆持久可靠 + 动态续期
- 记忆支持按相关性检索 + 自动过期清理
- 记忆支持跨会话共享
- 工具输出不污染长期记忆（stability="low" → Working only）
- 关键决策永不压缩（critical_episodes）
- 语义记忆写前校验来源（source_tag/trust_weight/provenance）

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **harness** | 使用 Harness 的记忆接口，loop.py 调用 build_context/save_interaction |
| **agents** | Agent 使用记忆存储上下文 |
| **knowledge** | SemanticCache 版本号原子切换（INCR version O(1)） |
| **skills** | SkillRegistry 滑动窗口追踪 recent_pass_rate |
| **services** | 公共服务支持记忆管理 |

---

## 相关文档

- [Harness 索引](../harness/index.md) - 智能体框架
- [Context 管理](../harness/context.md) - 上下文压缩与双记忆架构
- [渐进式披露](../harness/progressive-disclosure.md) - 记忆加载策略

---

*最后更新: 2026-06-24*

---

## 证据索引（Evidence Index｜抽样）

- Memory 模块：`core/harness/memory/*`
- MemoryManager：`core/harness/memory/manager.py`
- Compression + Tool Budget：`core/harness/memory/compression.py`
- Semantic Expiry + Soft Delete：`core/harness/memory/semantic.py`
- MemoryEntry (投毒防御)：`core/harness/memory/base.py`
- Episodic Scoring：`core/harness/memory/episodic.py`
- RRF + Early Exit：`core/harness/syscalls/retrieval.py`
- Cache Versioning：`core/harness/knowledge/semantic_cache.py`
- Skill Decay：`core/apps/skills/registry.py`
