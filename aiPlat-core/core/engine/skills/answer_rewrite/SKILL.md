---
name: answer_rewrite
display_name: 问答答案重写
description: 基于当前问题、原回答与检索命中依据，使用 LLM 生成更自然、正式的中文答案。
category: document
version: 0.1.0
skill_kind: executable
permissions:
  - doc:read
auto_trigger_allowed: false
requires_approval: false
input_schema:
  type: object
  properties:
    tenant_id: {type: string, description: 租户ID（默认 default）}
    collection_id: {type: string, description: 集合ID（默认 default）}
    question: {type: string, description: 用户问题}
    current_answer: {type: string, description: 当前检索回答}
    items:
      type: array
      description: 检索命中片段
      items: {type: object}
  required: [question]
output_schema:
  type: object
  properties:
    collection_id: {type: string}
    question: {type: string}
    rewritten_answer: {type: string}
    mode: {type: string}
---
