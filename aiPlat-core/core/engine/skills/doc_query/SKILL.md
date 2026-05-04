---
name: doc_query
display_name: 资料对话查询
description: 通用资料查询（MVP）：基于已解析写入 kb_elements 的内容进行检索，返回匹配片段与引用信息，供上层对话生成/总结使用。
category: document
version: 0.1.0
skill_kind: executable
permissions:
  - doc:read
auto_trigger_allowed: true
requires_approval: false
trigger_conditions:
  - 查询资料
  - 问答文档
  - 总结要点
input_schema:
  type: object
  properties:
    tenant_id: {type: string, description: 租户ID（默认 default）}
    collection_id: {type: string, description: 集合ID（默认 default）}
    doc_id: {type: string, description: 可选：指定文档ID；缺省则按 collection_id 检索}
    question: {type: string, description: 用户问题}
    top_k: {type: integer, description: 返回片段数量（默认 8）}
  required: [question]
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
