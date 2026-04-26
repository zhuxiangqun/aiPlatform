---
name: demo_readonly_summarize
display_name: 只读摘要（示范）
description: 对输入文本做结构化摘要（无副作用、可自动触发），用于验证 Skill Contract/路由/可观测闭环。
category: transformation
version: 0.1.0
skill_kind: executable
permissions:
  - read_only
auto_trigger_allowed: true
requires_approval: false
trigger_conditions:
  - 摘要
  - 总结
  - 梳理要点
  - 提炼重点
  - 归纳
input_schema:
  type: object
  properties:
    text:
      type: string
      description: 待摘要的文本
    max_bullets:
      type: integer
      description: 要点条数上限（默认 6）
  required: [text]
output_schema:
  type: object
  properties:
    title:
      type: string
      description: 自动生成的标题
    bullets:
      type: array
      items: {type: string}
      description: 要点列表
    short_summary:
      type: string
      description: 一句话摘要
---

# 只读摘要（示范）

## 目标
对输入 `text` 输出：
1) `title`：标题
2) `bullets`：要点（默认最多 6 条）
3) `short_summary`：一句话摘要

## 约束
- 只做文本处理，不进行任何外部调用或写入操作。
- 输出必须是 JSON（由 handler.py 返回）。

