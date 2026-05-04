---
name: doc_summarize
display_name: 资料核心要点总结
description: 通用资料总结（MVP）：基于 kb_elements 生成核心要点（可配置 profile/max_points），返回要点与引用信息；后续可接入 LLM 做更高质量总结。
category: document
version: 0.1.0
skill_kind: executable
permissions:
  - doc:read
auto_trigger_allowed: true
requires_approval: false
trigger_conditions:
  - 总结文档
  - 核心要点
  - 提炼要点
input_schema:
  type: object
  properties:
    tenant_id: {type: string, description: 租户ID（默认 default）}
    collection_id: {type: string, description: 集合ID（默认 default）}
    doc_id: {type: string, description: 文档ID（MVP 必填）}
    profile: {type: string, description: key_points|outline|actions|risks（默认 key_points）}
    max_points: {type: integer, description: 要点条数（默认 10）}
  required: [doc_id]
output_schema:
  type: object
  properties:
    summary: {type: string}
    points:
      type: array
      items: {type: object}
    citations:
      type: array
      items: {type: object}
    tenant_id: {type: string}
    collection_id: {type: string}
    doc_id: {type: string}
---
