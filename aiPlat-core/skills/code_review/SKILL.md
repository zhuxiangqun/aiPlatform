---
name: code_review
display_name: 代码审查
description: 审查代码质量并给出可操作的改进建议（正确性/可读性/安全/性能）。
category: analysis
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
  report:
    type: object
    required: true
    description: 结构化审查结果（机器可读）
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
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

## 输出格式（JSON + Markdown）
执行时请输出严格 JSON，包含两个字段：

- `report`：结构化对象，建议字段（允许扩展）：
  - `summary`：一句话总结
  - `blocking`：数组，每项包含 `title/why/how_to_fix/location(selections)/severity`
  - `non_blocking`：数组，同上但严重度较低
  - `risk`：例如 `low|medium|high`
- `markdown`：把上述内容渲染为 Markdown

## 质量要求（Checklist）
- [ ] 指出问题所在位置（行号/片段）
- [ ] 每条建议都可落地
