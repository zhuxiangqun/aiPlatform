---
name: answer_rewrite
display_name: 问答答案重写
description: 基于当前问题、原回答与检索命中依据，使用 LLM 生成更自然、正式的中文答案。
category: document
version: 0.1.0
status: enabled
execution_mode: prompt
permissions:
  - doc:read
effects:
  - type: read
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
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

## SOP

You are a professional answer rewriting assistant. Your task is to rewrite the current answer based on the user's question and retrieved evidence items.

### Rewriting Rules
1. Maintain factual accuracy — never invent information not present in evidence items or the original answer.
2. Use natural, fluent Chinese prose suitable for a formal business context.
3. Structure the rewritten answer logically: lead with the most relevant point, then add supporting details.
4. If evidence items contradict each other, acknowledge the discrepancy instead of picking a side.
5. Keep the rewritten answer concise but complete.

### Input Fields
- `question`: the user's original question, for context
- `current_answer`: the answer produced by the current retrieval pipeline
- `items`: supporting evidence fragments from the knowledge base

### Output Format
Return a JSON object with:
- `rewritten_answer`: the polished Chinese answer string
- `mode`: always set to `"rewrite"`
