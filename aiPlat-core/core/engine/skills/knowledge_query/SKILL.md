---
name: knowledge_query
display_name: 知识库查询
description: 多模态知识库查询（MVP）：支持“投资预算”类问答，返回结构化条目与 citations（bbox/页码）。 涉及知识库相关操作。 主要进行查询。
category: knowledge
version: 0.1.0
status: enabled
execution_mode: prompt
permissions:
- kb:read
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
triggers:
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
  required:
  - question
output_schema:
  type: object
  properties:
    answer:
      type: string
    items:
      type: array
      items:
        type: object
    citations:
      type: array
      items:
        type: object
    tenant_id:
      type: string
    collection_id:
      type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 知识库查询
  - 查知识库
  - 检索知识
  - 搜索知识库
  - budget查询
  - FTS5搜索
  - 知识检索
  keywords:
    objects:
    - 知识库
    - SQL
    - 条目
    - budget
    actions:
    - 查询
    - 检索
    - 搜索
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 从结构化知识库返回带引用的精准答案

protected: true
---

# 知识库查询

## SOP
1. 确认 question（问题文本）、tenant_id、collection_id
2. **如果参数中包含 `doc_content`**（已检索的文档内容）：
   - 直接基于 `doc_content` 内容回答 `question`
   - 回答要准确、简洁，引用原文关键信息
   - 如果 `doc_content` 不足以回答问题，如实告知
3. **如果没有 `doc_content`**：调用 `kb_query` Tool 执行查询
4. 返回结构化结果（answer + citations）

## 参数
- `question`: 用户问题（必填）
- `doc_content`: 已检索的文档内容文本（可选，有此参数时跳过 Tool 调用）
- `doc_id` / `doc_ids`: 目标文档 ID
- `tenant_id`, `collection_id`: 租户与集合信息
- `analysis`, `retrieval_policy`, `answer_strategy`: 策略元数据（可选）

## 输出格式
```json
{"answer": "...", "citations": [...], "items": [...]}
```

## Tool（后备）
- `kb_query`: KBQueryTool (core/apps/tools/kb_tools.py)

## 目标
从结构化知识库返回带引用的精准答案

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注