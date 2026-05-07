---
name: rag_agent
display_name: 知识增强助手
description: RAG Agent（检索增强生成）。应用库默认 Agent（workspace）：对外可用；需配套知识库权限与数据隔离。
agent_type: rag
version: 1.0.0
status: ready
protected: false
required_skills:
  - knowledge_retrieval
required_tools: []
config:
  model: gpt-4
  temperature: 0.3
---

# 知识增强助手（Workspace）

## SOP
1. 澄清问题与范围（数据域/时间/权限）。
2. 检索召回并引用关键片段。
3. 综合生成答案并标注证据。

## 交接规范
1. **做了什么**：知识检索+答案生成完成，输出基于证据的回答和引用
2. **产出物在哪**：state["rag_output"]，答案在 answer，引用在 citations
3. **如何验证**：检查 citations 中 source_id 是否可追溯；confidence 级别是否合理
4. **已知问题**：检索结果可能不完整；答案置信度=LOW时需要人工确认
5. **下一步**：下游 Agent 基于 answers 继续研究；在必要时重新检索
