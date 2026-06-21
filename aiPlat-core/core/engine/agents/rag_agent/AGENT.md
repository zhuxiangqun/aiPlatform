---
name: rag_agent
display_name: RAG问答引擎
description: 基于检索增强生成的问答 Agent。引擎内置（engine）：仅核心能力层默认可用。
agent_type: rag
version: 1.0.0
status: running
protected: true
category: engineering
tags:
- rag
- retrieval
- generation
skills:
- knowledge_retrieval
- summarization
- code-hygiene
- information_search
- doc_query
- multi_doc_query
tools:
- search
- sysgraph_search
- sysgraph_context
model: deepseek-reasoner
config:
  system_prompt: 你是 rag_agent，基于检索增强生成的问答 Agent。引擎内置（engine）：仅核心能力层默认可用。
  model: deepseek-chat
---


## 交接协议 (Handoff)

**做了什么**: 执行 rag_agent 的 SOP 定义的任务
**产出物在哪**: state[output_artifact] 中
**如何验证**: 检查 output_artifact 是否存在且非空
**已知问题**: Engine seed — 完整 SOP 需在 workspace agent 中定义
**下一步**: 下游阶段读取本阶段的产出物继续执行

> 探索代码结构时优先用 sysgraph_* 工具（比 grep/read 快 10×）
