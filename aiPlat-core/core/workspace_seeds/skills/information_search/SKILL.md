---
name: information_search
display_name: 信息检索
description: 检索外部/公开信息并汇总来源。应用库默认技能（workspace）：对外可用；生产环境建议仅走受控数据源并配合白名单/审批。
category: retrieval
version: 1.0.0
status: disabled
protected: false
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
input_schema:
  query:
    type: string
    required: true
output_schema:
  results:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# 信息检索（Workspace）

> 默认禁用：公网检索存在合规/来源不可控风险，建议在 workspace 侧封装受控检索策略后再启用。

## SOP
1. 明确检索范围与新鲜度要求。
2. 执行检索并对比多个权威来源。
3. 输出结论 + 证据要点 + 来源链接。
