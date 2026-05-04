---
name: video_fact_lookup
display_name: 视频事实查询
description: 面向单视频的细粒度事实型问答，优先基于 transcript 句级/短片段检索返回带时间引用的回答。
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
    tenant_id: {type: string}
    collection_id: {type: string}
    doc_id: {type: string}
    question: {type: string}
    top_k: {type: integer}
  required: [doc_id, question]
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
    doc_id: {type: string}
---
