---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出可操作的改进建议（正确性/可读性/安全/性能）。
category: analysis
version: 1.0.0
status: enabled
execution_mode: inline
trigger_conditions:
  - "帮我review"
  - "代码审查"
  - "看看这段代码"
input_schema:
  diff_or_code:
    type: string
    required: true
    description: 代码片段或 diff
output_schema:
  review:
    type: string
    description: 审查意见
---

# 代码审查

## 目标
发现代码中的问题与改进点，并给出分级（阻塞/建议）与明确修改方案。

## 工作流程（SOP）
1. 概览：这段代码在做什么、有哪些假设。
2. 正确性：边界条件、空值、并发/事务、错误处理。
3. 可维护性：命名、结构、重复、复杂度、测试覆盖。
4. 安全性：注入、越权、敏感信息、依赖风险。
5. 输出审查报告：
   - Blocking（必须改）
   - Non-blocking（建议改）
   - 可选的补丁/示例代码

## 质量要求（Checklist）
- [ ] 指出问题所在位置（行号/片段）
- [ ] 每条建议都可落地
