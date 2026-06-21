---
name: materials_chat
display_name: RAG 知识库助手
description: 企业级六阶段认知 RAG Agent — 域路由 → 本体感知 → 多路检索 → CRAG回退 → Self-RAG自评 → 流式生成
agent_type: materials_chat
version: 1.0.1
status: ready
protected: false
category: knowledge
tags: [rag, retrieval, ontology, conversational]
model: auto
phase: serving
stages:
  - id: question_understand
    order: 1
    node_type: llm
    prompt_template: dmqr-rewrite
    output_artifact: enhanced_question
    
  - id: domain_route
    order: 2
    node_type: knowledge  
    routing_rules:
      tiers: [label_match, embedding, llm]
      fallback_domain: ai-knowledge
    depends_on: [question_understand]
    output_artifact: domain_id
    
  - id: ontology_map
    order: 3
    node_type: knowledge
    dependency_type: ontology_query_map
    expand_subclasses: true
    depends_on: [domain_route]
    output_artifact: matched_classes
    
  - id: graph_traverse
    order: 4
    node_type: knowledge
    dependency_type: graph_traversal
    max_hops: 2
    cross_domain_degradation: 3
    depends_on: [ontology_map, domain_route]
    
  - id: multi_retrieve
    order: 5
    pipeline_mode: parallel
    quality_gate:
      condition: "len(result.retrieved_docs) < 100"
      fallback: fts5_retrieve
      final_fallback: hyde_retrieve
    knowledge_bases: [wiki, kb]
    depends_on: [graph_traverse]
    output_artifact: retrieved_docs
    
  - id: quality_assess
    order: 6
    node_type: llm
    review_gate: llm
    retry_policy:
      "on": low_evidence
      action: re_retrieve_with_hyde
      max_retries: 1
    depends_on: [multi_retrieve]
    output_artifact: quality_label
    
  - id: answer_generate
    order: 7
    node_type: llm
    render_upstream: true
    streaming: true
    scene_id: "{{domain_id}}-prompt"
    depends_on: [multi_retrieve, quality_assess]
    output_artifact: answer
---
# MaterialsChatAgent — 企业级 RAG 认知架构

## 做了什么
基于用户问题，执行六阶段认知流水线生成答案：
1. **问题理解** — DMQR 多查询改写，生成语义变体增强检索召回率
2. **域路由** — DomainRouter 三级级联分类（T1倒排索引/T2向量余弦/T3 LLM），定位问题所属知识域
3. **本体感知** — OntologyQueryMapper 映射查询到领域本体类 + GraphIndex 图遍历扩展关联实体
4. **多路检索** — Wiki优先检索（FTS5+embedding）→ KB向量回退 → 级联CRAG回退 → RRF融合 → Cross-Encoder重排序
5. **质量评估** — Self-RAG自动评估答案证据充分性，低置信度时触发HyDE假设答案重检索
6. **流式生成** — domain-prompt注入 + 检索文档上下文 → LLM SSE流式输出

## 产出物在哪
- 答案通过 SSE 流式返回前端 ChatPanel
- 推理路径（reasoning_path）、检索标签（strategy/mode）、质量标签（quality）、域标签（domain_id/domain_name）通过元数据透传
- 对话记录持久化到 ConversationService
- 六阶段 pipeline_trace 通过 SSE `data.pipeline_trace` 下发，前端 PipelineTrace 组件渲染时间线
- 👍/👎 反馈写入 `state_history.db` 的 feedback 表

## 如何验证
在知识库页面提问，观察以下指标：
- **答案下方标签**：📍 域 / 🔍 检索策略 / ⚠️ 质量
- **🧠 思考链**：点击展开查看六阶段时序（每阶段延迟 + 元数据）
- **检索路径**：蓝色 `direct_retrieve` = 正常检索，紫色 `hyde` = 假设答案回退
- **质量标志**：绿色无标记 = ok，黄色 = needs_review，红色 = low_evidence

## 已知问题
- 检索质量依赖 Wiki 页面覆盖度，空知识库或边缘话题时自动回退到 HyDE/Skill 模式
- 单页单实例场景下不自动产图边，需额外调用 `POST /ontology/domains/{id}/build-edges`
- 同步文件系统扫描（`list_all_pages`）可能阻塞单 worker 事件循环，建议部署时使用 `--workers 2`

## 下一步
- 定期运行 `build-edges` 维护跨页面知识图谱边
- 在 v3.0 监控仪表盘观察检索质量 EWM A趋势和 Fallback 率
- 积累 👍/👎 反馈数据后，可接入自动化权重调优
