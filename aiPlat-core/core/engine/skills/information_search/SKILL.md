---
name: information_search
display_name: 信息检索
description: 从知识库和互联网中检索相关信息。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: retrieval
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "web:search"
  - "kb:query"
input_schema:
  query:
    type: string
    required: true
  sources:
    type: array
    description: 检索源，如 kb, web
output_schema:
  results:
    type: array
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 信息检索（Engine）

## SOP
1. 分析查询意图，确定检索源和范围。
2. 执行多源检索并对结果去重排序。
3. 输出相关性排序的结果列表及每条的去源信息。
