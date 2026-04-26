---
name: information_search
display_name: 信息检索
description: 从知识库与互联网检索信息并汇总来源与结论。
category: retrieval
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "帮我查"
  - "搜索一下"
  - "找资料"
  - "检索信息"
input_schema:
  query:
    type: string
    required: true
    description: 检索问题/关键词
output_schema:
  results:
    type: string
    description: 结构化结果与来源
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 信息检索

## 目标
快速检索并给出可信答案，附带可追溯来源。

## 工作流程（SOP）
1. 明确检索范围与新鲜度要求（是否需要最新/是否只看官方）。
2. 先给出检索策略（关键词、限定条件）。
3. 执行检索，至少对比 2 个来源（优先官方/权威）。
4. 输出：结论 + 证据要点 + 来源链接列表。

## 质量要求（Checklist）
- [ ] 结论可追溯（含来源）
- [ ] 不确定处明确标注
