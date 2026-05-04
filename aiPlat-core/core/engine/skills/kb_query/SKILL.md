---
name: kb_query
display_name: 知识库查询
description: 多模态知识库查询（MVP）：支持“投资预算”类问答，返回结构化条目与 citations（bbox/页码）。
category: knowledge
version: 0.1.0
skill_kind: executable
permissions:
  - kb:read
auto_trigger_allowed: true
requires_approval: false
trigger_conditions:
  - 查询知识库
  - 问答文档内容
  - 投资预算是多少
  - 预算有哪些
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: 租户ID（多租户隔离）
    collection_id:
      type: string
      description: 知识库集合ID（默认 default）
    question:
      type: string
      description: 问题，例如：2026年投资预算是哪些？
    year:
      type: integer
      description: 可选：指定年度（默认从问题推断，缺省为 2026）
    limit:
      type: integer
      description: 返回条数上限（默认 50）
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
---

# 知识库查询（MVP）

## 说明
当前 MVP 优先支持“投资预算/预算有哪些”这类问题，会从已入库的预算表结构化行中返回条目，并给出每个金额的 bbox 引用（页码+坐标+页图路径）。

