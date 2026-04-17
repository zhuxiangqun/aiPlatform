---
name: api_calling
display_name: API调用
description: 按接口文档调用 API 并处理鉴权与错误（引擎内置）。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
input_schema:
  endpoint:
    type: string
    required: true
  method:
    type: string
    required: false
  payload:
    type: object
    required: false
output_schema:
  response:
    type: object
---

# API调用（Engine）

## SOP
1. 明确鉴权方式与参数口径。
2. 调用并记录状态码/trace 信息（如有）。
3. 输出结构化结果与下一步建议（含错误映射）。
