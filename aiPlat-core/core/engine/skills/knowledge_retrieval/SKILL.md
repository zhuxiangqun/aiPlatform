---
name: knowledge_retrieval
display_name: 知识召回
description: 从内部知识库召回相关片段。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: retrieval
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  query:
    type: string
    required: true
output_schema:
  snippets:
    type: string
---

# 知识召回（Engine）

## SOP
1. 规范化 query（补实体/同义词）。
2. 召回 Top-K，去重并排序。
3. 输出片段 + 来源 + 相关性说明，并可给综合结论。
