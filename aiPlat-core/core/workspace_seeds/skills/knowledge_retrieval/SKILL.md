---
name: knowledge_retrieval
display_name: 知识召回
description: 从内部知识库/向量库中召回相关文档片段。应用库默认技能（workspace）：用于 RAG 类 Agent；需配套权限控制与数据隔离。
category: retrieval
version: 1.0.0
status: enabled
protected: false
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  query:
    type: string
    required: true
    description: 检索问题/关键词
  top_k:
    type: integer
    required: false
    description: 返回片段数量（默认 5）
  filters:
    type: object
    required: false
    description: 过滤条件（如 collection、时间范围、标签等）
output_schema:
  passages:
    type: array
    required: true
    description: 召回片段列表（含文本与元信息）
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 知识召回（Workspace）

## SOP
1. 解析 query 与 filters，确定检索数据域。
2. 从知识库/向量库召回 top_k 个相关片段。
3. 输出 passages（文本 + 关键元信息），供上游 Agent 综合生成并引用证据。
