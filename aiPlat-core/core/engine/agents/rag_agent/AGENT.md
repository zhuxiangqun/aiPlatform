---
name: rag_agent
display_name: RAG问答引擎
description: 检索增强问答 Agent（引擎内置）。
agent_type: rag
version: 1.0.0
status: ready
protected: true
required_skills:
  - knowledge_retrieval
  - summarization
required_tools: []
config:
  model: gpt-4
  temperature: 0.3
---

# RAG问答引擎（Engine）

## SOP
1. 召回相关片段并提炼证据。
2. 基于证据回答并标注不确定处。
