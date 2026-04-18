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

