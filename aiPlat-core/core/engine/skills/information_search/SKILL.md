---
name: information_search
display_name: 信息检索
description: 检索外部/公开信息并汇总来源。引擎内置（engine）：仅核心能力层默认可用；对外（workspace）需白名单/审批后方可调用。
category: retrieval
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  query:
    type: string
    required: true
output_schema:
  results:
    type: string
---

# 信息检索（Engine）

## SOP
1. 明确检索范围与新鲜度要求。
2. 执行检索并对比多个权威来源。
3. 输出结论 + 证据要点 + 来源链接。
