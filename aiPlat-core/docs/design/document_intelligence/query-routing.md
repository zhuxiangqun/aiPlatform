# Query Routing（Document Intelligence）

> 最后更新: 2026-07-04

## 目标与边界

本文档描述 `aiPlat-core` 在资料问答/资料对话场景下的通用决策机制，包括：
- 问题分析（question analysis）
- 检索路由（retrieval policy）
- 回答策略（answer strategy）

本文档不覆盖 Harness 运行时细节，也不替代 Skill/Agent 架构文档。

## 核心原则（Policy decides, Skill executes）

1. 问题分析、检索路由、回答策略属于 `aiPlat-core` 内部 policy 层（Internal Policy / Service）。
2. Agent 负责会话级编排，不承载底层检索实现细节。
3. Skill 负责单一职责执行，不承担系统级高层策略决策。
4. 执行层与决策层解耦：由 policy 做决策，由 skill 做执行。

## 推荐执行链

`question -> analysis -> retrieval_policy -> answer_strategy -> skill -> response -> memory`

### 接入点

- Agent：负责调用 analysis / policy / strategy，并决定执行哪一个或哪几个 skill。
- Skill：负责执行具体查询/导入/处理能力。
- Query 执行层：根据 `retrieval_policy` 调整执行路径（例如是否进入 video window 路径）。

## 问题分析模型（question_analysis）

推荐输出字段：
- `intent`
- `evidence_granularity`
- `answer_shape`
- `follow_up`
- `entity_sensitive`
- `dominant_doc_kind`

### intent（问题性质）

- `summary`：总结/概括/主要内容
- `compare`：对比/差异/共同点
- `fact_lookup`：事实型问题（短答案，依赖少量证据）
- `evidence_trace`：询问依据/出处/引用位置
- `follow_up`：追问/延展/承接上文
- `applicability_analysis`：适用性分析（“对我的系统有何借鉴意义”）

### evidence_granularity（证据粒度需求）

- `fine`：细粒度（句级/短片段，适合人名、数字、精确事实）
- `coarse`：粗粒度（大窗口/多片段聚合，适合总结）
- `mixed`：混合粒度（既要总体也要部分精确证据，适合比较与适用性分析）

### answer_shape（答案形态）

- `short_grounded`
- `grounded_summary`
- `comparative_analysis`
- `evidence_first`
- `conditional_analysis`

## 检索路由模型（retrieval_policy）

推荐输出字段：
- `route`
- `skill_name`
- `top_k`
- `granularity`
- `needs_aggregation`

示例 route：
- `single_doc_query`
- `multi_doc_query`
- `video_window_query`
- `video_fact_lookup`（v1 可先语义路由，v2 独立实现 skill）
- `evidence_trace_lookup`（可选）

## 回答策略模型（answer_strategy）

推荐输出字段：
- `style`
- `need_direct_answer`
- `cite_first`
- `allow_conditional_answer`

## 与现有实现的映射（As-Is）

当前仓库中，决策层与执行层的落点建议如下：

- Internal Policy modules：
  - `core/apps/document_intelligence/question_analysis.py`
  - `core/apps/document_intelligence/retrieval_policy.py`
  - `core/apps/document_intelligence/answer_strategy.py`
- 执行入口：
  - `materials_chat_agent`（会话编排）
  - `doc_query` / `multi_doc_query`（能力执行）
  - `core/apps/document_intelligence/query.py`（检索与引用构造执行层）

## 演进路线（To-Be）

### v1（当前）
- `video_window_query` 通过 `retrieval_policy.route` 显式路由到 `query.py` 的视频窗口路径。
- `video_fact_lookup` 可先作为 route 语义落地，通过 `fine` 粒度策略影响执行层行为（暂复用 `doc_query`）。

### v2（建议）
- 新增独立 `video_fact_lookup` skill：面向细粒度事实问题（人名、数字、时间、组织等）。
- 拆分 `query.py`：
  - `video_retrieval.py`：视频窗口与视频事实检索
  - `citation_builder.py`：引用与资产映射
  - `retrievers.py`：embedding/keyword 检索与 rerank

### v3（可选）
- 如需灰度与可替换策略：将 policy 层演进为 internal system skills（而非普通业务 skill），纳入变更治理与 A/B 能力。

