---
name: multi_doc_query
display_name: 多资料对话查询
description: 在指定 doc_ids 范围内进行统一检索与问答，返回匹配片段与引用信息，供资料对话 Agent 使用。
category: document
version: 0.1.0
skill_kind: executable
permissions:
  - doc:read
auto_trigger_allowed: true
requires_approval: false
input_schema:
  type: object
  properties:
    tenant_id: {type: string, description: 租户ID}
    collection_id: {type: string, description: 集合ID}
    doc_ids:
      type: array
      items: {type: string}
      description: 指定资料范围
    question: {type: string, description: 用户问题}
    top_k: {type: integer, description: 返回片段数量}
  required: [doc_ids, question]
output_schema:
  type: object
  properties:
    answer: {type: string}
    items:
      type: array
      items: {type: object}
    citations:
      type: array
      items: {type: object}
    tenant_id: {type: string}
    collection_id: {type: string}
    doc_ids:
      type: array
      items: {type: string}
---
