---
name: api_calling
display_name: API调用
description: 按接口文档调用 API 并处理鉴权与错误。应用库默认技能（workspace）：对外可用；生产环境建议白名单/审批后方可调用。
category: execution
version: 1.0.0
status: disabled
protected: false
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
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
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# API调用（Workspace）

> 默认禁用：对外调用通常涉及外部系统写操作/鉴权配置，请在应用库按需启用，并配合审批与审计。

## SOP
1. 明确鉴权方式与参数口径（token/签名/headers）。
2. 调用并记录状态码/trace 信息（如有）。
3. 输出结构化结果与下一步建议（含错误映射）。
