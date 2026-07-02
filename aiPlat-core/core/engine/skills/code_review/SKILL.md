---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出改进建议。触发条件：用户要求审查代码、review PR、检查代码质量。跳过条件：代码生成由 code_generation
  处理。
category: analysis
version: 1.0.0
status: enabled
protected: true
completion_criterion: |
  1. 每个改动都有明确的验收标准（可验证的 pass/fail 条件）
  2. 如存在相关测试，修改后所有测试通过或明确标注预期失败
  3. 不产生新的已知 lint 问题
execution_mode: prompt
execution_type: prompt
triggers:
  - 代码审查
  - 审查代码
  - review code
  - 检查代码
permissions:
- llm:generate
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
input_schema:
  code:
    type: string
    required: true
  language:
    type: string
output_schema:
  review:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 审查代码
  - Code Review
  - 检查代码
  - 代码评审
  - review代码
  - 代码质量
  - 代码检查
  - review PR
  - 代码质量检查
  - 安全审查
  keywords:
    objects:
    - 代码
    - PR
    - 提交
    - diff
    actions:
    - 审查
    - 检查
    - 评审
    - review
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 系统性审查代码质量并给出改进建议
sop_flow:
  - "代码审查（Engine）"
  - "理解代码意图、上下文和依赖。"
  - "按维度审查：正确性、安全性、性能、可维护性、风格。"
  - "输出分级问题列表（P0/P1/P2）及改进建议。"
  - "系统性审查代码质量并给出改进建议"
  - "[ ] 输出格式符合规范"
  - "[ ] 正确处理错误和边界条件"
  - "[ ] 返回结果包含引用和来源标注"
keywords:
  objects:
  - 代码
  - PR
  - diff
  - 提交
  actions:
  - 审查
  - review
  - 检查
  - 评估
  constraints:
  - 安全
  - 性能
  - 可读性
  - 最佳实践
trigger_conditions:
- when: 用户要求审查代码
  query: review/审查/代码质量
- when: 不应用场景
  description: 跳过条件：用户仅询问最佳实践而非审查具体代码时不触发。
skip_when: 跳过条件：用户仅询问最佳实践而非审查具体代码时不触发。
---



# 代码审查（Engine）

## SOP
1. 理解代码意图、上下文和依赖。
2. 按维度审查：正确性、安全性、性能、可维护性、风格。
3. 输出分级问题列表（P0/P1/P2）及改进建议。

## 目标
系统性审查代码质量并给出改进建议

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注