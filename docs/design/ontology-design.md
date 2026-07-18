---
last_synced: 2026-07-18
---
> **最后更新**: 2026-07-18

# aiPlat 本体论框架设计方案

> 📄 设计阶段文档 · 实际实现见 [本体模型管理使用手册](../manuals/ontology.md) 和 [知识管理完整指南](../manuals/knowledge-management.md)

## 摘要

aiPlat 系统已有 5 套独立的图结构——能力图、代码图、Wiki 链接图、Skill 依赖图、实体关系图——但它们各自为政，无法跨域查询。本方案设计了统一的 `Ontology` 抽象层来整合这些孤岛，基于 SPO（Subject-Predicate-Object）三元组模型，实现跨 Agent/Skill/Tool/Wiki/KB/Pipeline/Memory 全域推理。

---

## 一、现有实体全景（当前分散在不同模块的 50+ 种实体）

### 能力层（Capability Layer）
| 实体 | 来源 | 典型属性 |
|------|------|---------|
| **Agent** | `agent_manager.py:22` | id, agent_type, status, model, skills[], tools[], mcp_ids[], scope, phase |
| **Skill** | `skill_manager.py:22` | id, name, category, status, trigger_conditions, keywords, effects[], skill_kind |
| **Tool** | `tools/base.py:34` | name, description, parameters, risk_level, category |
| **MCP Server** | `mcp_manager.py:22` | name, transport, command, allowed_tools[], source |
| **PipelineConfig** | `schemas_builder.py:283` | stages[], max_iterations, max_tokens_per_run |
| **PipelineStageConfig** | `schemas_builder.py:219` | agent_id, order, output_artifact, hitl, execution_mode, review_gate, routing_rules[], 50+ fields |
| **TaskSkill** | `memory/manager.py:26` | skill_id, pipeline_id, agent_sequence[], pass_rate, is_hot |

### 知识层（Knowledge Layer）
| 实体 | 来源 | 典型属性 |
|------|------|---------|
| **Wiki 页面** | `wiki_engine.py` | title, category, tags[], related[], relationships[{type,target}], source_articles[], summary |
| **KB 文档** | `platform/kb/db.py` | doc_id, source_uri, kind, collection_id, wiki_pages[] |
| **KB 元素** | `platform/kb/db.py` | element_id, type(text/table/image/transcript), text, bbox |
| **KB 嵌入** | `platform/kb/db.py` | embedding_type, model, vector |
| **实体关系三元组** | `graph.py` | source_entity, relation, target_entity (LLM 抽取) |

### 记忆层（Memory Layer）
| 实体 | 来源 | 典型属性 |
|------|------|---------|
| **WorkingMemory** | `memory/working.py` | deque 滑动窗口, 30K tokens |
| **EpisodicMemory** | `memory/episodic.py` | session_id, summary, key_decisions |
| **SemanticMemory** | `memory/semantic.py` | items[], embeddings, access_count |
| **MemorySession** | `execution_store.py:694` | id, user_id, agent_type, message_count |

### 执行层（Execution Layer）
| 实体 | 来源 | 典型属性 |
|------|------|---------|
| **Run** | `execution_store_schema.py:53` | run_id, status, phase, tokens_used |
| **Trace** | `execution_store.py:277` | trace_id, name, status |
| **SyscallEvent** | `execution_store_schema.py:87` | kind(llm/tool/skill), name, status, args_json, result_json |
| **PromptTemplate** | `prompt_loader.py` | template_id, category, variables[], classification |
| **Job/Cron** | `execution_store.py:510` | name, cron, kind, target_id |
| **Adapter** | `execution_store.py:1008` | name, provider, status, models[] |
| **ModelInfo** | infra `ModelManager` | name, provider, capability_type, is_available |

---

## 二、现有关系全景（已定义在代码中但彼此不认识）

### 已存在但孤立的关系
```
Agent               pip:requires_skill      → Skill
Agent               pip:requires_tool       → Tool
Agent               pip:uses_mcp            → MCP Server
Agent               pip:delegates_to        → Agent (subagent)

PipelineStage       pip:assigns_agent       → Agent
PipelineStage       pip:depends_on          → PipelineStage
PipelineStage       pip:requires_skill      → Skill

Skill               pip:uses_syscall        → Syscall
Skill               pip:uses_tool           → Tool

MCP Server          pip:provides_tool       → Tool (mcp.<server>.tool)

Wiki                pip:cites               → Wiki
Wiki                pip:supports            → Wiki
Wiki                pip:contradicts          → Wiki
Wiki                pip:example_of           → Wiki
Wiki                pip:from_kb_doc          → KB Document

TaskSkill           pip:from_pipeline        → Pipeline Run
TaskSkill           pip:uses_agent           → Agent

Run                 pip:contains_trace       → Trace
Trace               pip:contains_syscall     → SyscallEvent

KB Document         pip:contains_element     → KB Element
KB Element          pip:has_embedding        → KB Embedding

Job                 pip:targets              → Agent/Skill/Tool

PromptTemplate      pip:used_by              → Source File (通过调用点分析)

Agent               pip:uses_model           → ModelInfo
```

---

## 三、现在"不能问"的跨域查询（本体论要解决的）

| 查询 | 为什么现在不能做 |
|------|-----------------|
| "删除 Tool test-1 影响哪些 Skill/Agent/Pipeline/Wiki？" | 需要在能力图 + Skill 依赖图 + Pipeline 图中做多跳遍历——三个独立的图没有统一 ID |
| "Wiki 页面 X 被哪些 Agent 的 Skill 引用了？" | Wiki 有 relationship 字段，能力图有 Agent-Skill-Tool 边——但没有跨图桥接 |
| "如果禁用 deepseek-chat 模型，哪些 Agent/Pipeline 受影响？" | Agent 配置里有 model 字段，但没被建模为"uses_model"关系 |
| "哪些 Skill 既没有 Agent 绑定，也没有 Pipeline 使用？" | skill_deps.py 只查 engine scope，workspace scope 没查 |
| "展示从用户请求 → Pipeline → Agent → Skill → Tool → Syscall 的完整链路" | 每个环节在各自的图里，没有统一的追踪 ID |
| "KB 文档 D 产生了哪些 Wiki 页面？那些页面又关联了哪些 Agent 和 Skill？" | 是 wiki→kb→graph 的三层跨接，需要统一查询 |
| "Prompt 模板 T 被哪些模块调用？其中多少来自已弃用的 agent？" | 调用点扫描结果 + agent 状态信息在不相关的模块中 |

---

## 四、本体论框架设计

### 核心模型：SPO 三元组

采用 RDF 风格的三元组模型，但不引入 RDF 库——用 Python dict 实现，轻量可控：

```python
# 三元组格式
triple = {
    "s": "agent:rag_agent",         # Subject (URN)
    "p": "requires_skill",          # Predicate (关系类型)
    "o": "skill:knowledge_retrieval", # Object (URN)
}

# URN 格式: namespace:entity_type:local_id
# 例如: engine:agent:rag_agent, workspace:skill:code_generation
```

### 实体类层次（继承树）

```
OntologyNode（基类）
├── CapabilityNode（能力基类）
│   ├── AgentNode
│   ├── SkillNode
│   ├── ToolNode
│   └── MCPServerNode
├── KnowledgeNode（知识基类）
│   ├── WikiNode
│   ├── KBDocumentNode
│   └── KBGraphTripleNode
├── PipelineNode（流水线基类）
│   ├── PipelineConfigNode
│   └── PipelineStageNode
├── MemoryNode（记忆基类）
│   ├── MemorySessionNode
│   └── TaskSkillNode
├── ExecutionNode（执行记录基类）
│   ├── RunNode
│   ├── SyscallEventNode
│   └── JobNode
└── ResourceNode（资源基类）
    ├── ModelNode
    ├── PromptTemplateNode
    └── AdapterNode
```

### 跨域桥接边的设计

现有的"类内关系"（如 Agent→Skill、Wiki→Wiki）保持不变。新增的桥接边负责跨域连接：

```
# Wiki ↔ 能力层
Wiki.CITES → KB_Document      # Wiki 引用 KB 文档（已有）
Wiki.USED_BY → Agent          # Agent 的 Skill 引用了这个概念（新增）

# 能力层 ↔ 执行层  
Agent.USES_MODEL → ModelInfo  # Agent 配置了哪个模型（新增）
Skill.CALLED_IN → SyscallEvent # Skill 在哪些事件中被调用（新增）

# Pipeline ↔ 知识层
PipelineStage.PRODUCES → Wiki # 流水线产出物是否沉淀为 Wiki 页面（新增）
TaskSkill.REFERENCES → Wiki   # 晶体化技能是否引用了知识（新增）

# 提示词 ↔ 能力层
PromptTemplate.USED_BY → Source → Agent # 模板→源文件→Agent（新增）
```

---

## 五、实现路线图

### Phase 1：统一 URN 体系和三元组引擎（~200 行，1 个文件）

**产出**：`core/harness/knowledge/ontology.py`

- `OntologyTriple` 数据结构
- `OntologyStore` 内存三元组存储（支持增删查改）
- `infer_transitive_closure(subject, predicate)` 传递闭包推理
- `find_path(source, target, max_depth)` BFS 路径搜索
- URN 解析和验证

### Phase 2：数据采集——从现有 5 个图中提取实体和关系（~150 行）

每个图实现一个 `OntologyLoader`：

- `CapabilityGraphLoader` → Agent/Skill/Tool/MCP 实体 + 关系
- `WikiGraphLoader` → Wiki 页面 + 关系
- `CodeGraphLoader` → 文件/符号实体 + import/call 关系
- `PipelineLoader` → Pipeline/Stage 实体 + assign/depend 关系
- `MemoryLoader` → TaskSkill/MemorySession 实体 + 关系

### Phase 3：跨域边推导（~100 行）

- `WikiToAgentBridge`：用 embedding 匹配 Wiki 页面→相关 Skill→相关 Agent
- `ModelUsageBridge`：扫描所有 Agent 的 model 字段→建立 uses_model 边
- `PromptToAgentBridge`：复用 `auto_classify()` 的调用点扫描结果
- `TaskSkillToPipelineBridge`：TaskSkill.pipeline_id→Run→Pipeline/Stages

### Phase 4：查询引擎和 API（~100 行）

- `OntologyQueryEngine`：SPARQL-like DSL
- `GET /ontology/query?s=<urn>&p=<pred>&depth=<n>` REST端点
- `GET /ontology/impact/<urn>` 影响分析
- `sys_ontology_context(task)` Syscall 工具

### Phase 5：本体驱动的健康检查（~80 行）

- `agent_has_no_skills_or_tools` 
- `skill_is_orphan`（0 个 Agent 绑定 + 0 个 Pipeline 使用）
- `wiki_page_unreachable_from_agents`
- `model_used_by_deprecated_agents`
- `prompt_template_unused`

---

## 六、与现有系统的关系（不破坏，只增强）

```
现状：
  CapabilityGraph ──独立的
  CodeGraph ──独立的
  WikiGraph ──独立的
  SkillDeps ──独立的
  KB Entity Graph ──独立的

目标：
  CapabilityGraph ──┐
  CodeGraph ────────┤
  WikiGraph ────────┼──→ OntologyStore ←──→ QueryEngine ←── REST API + Syscall
  SkillDeps ────────┤       (三元组存储)    (跨域查询)     (Agent 可调用)
  KB Entity Graph ──┘
```

- 所有现有图保持不变——继续各自独立运行
- `OntologyStore` 从它们读数据（非破坏性），统一存储三元组
- 跨域查询走 `OntologyQueryEngine`；单域查询继续走原图

---

## 七、投入产出总结

| 维度 | 评估 |
|------|------|
| **新增文件** | 1 个核心文件 `ontology.py`，5 个加载器（可逐步实现） |
| **代码量** | ~600 行（全部 phase） |
| **改动范围** | 纯增量——所有现有系统不受影响 |
| **关键价值** | 从"5 个互不知晓的图"升级为"1 个统一知识网络" |
| **首个可见效果** | `GET /ontology/impact/agent:rag_agent` — 一次性展示全部影响链 |
| **长尾价值** | 为未来的自学习（"该 Agent 应该绑定哪些 Skill？"、"哪些 Wiki 页面需要更新？"）提供数据基础 |
