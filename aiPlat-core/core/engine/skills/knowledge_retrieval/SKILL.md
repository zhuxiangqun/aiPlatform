---
name: knowledge_retrieval
display_name: 知识召回
description: 从内部知识库召回相关片段。触发条件：用户问"查一下""有没有相关文档""知识库里有什么"。跳过条件：外部网络搜索由 information_search 处理。
category: retrieval
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  query:
    type: string
    required: true
output_schema:
  snippets:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 知识召回（Engine）

## SOP
1. 规范化 query（补实体/同义词）。
2. 召回 Top-K，去重并排序。
3. 输出片段 + 来源 + 相关性说明，并可给综合结论。
