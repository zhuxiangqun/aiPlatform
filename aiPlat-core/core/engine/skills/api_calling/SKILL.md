---
name: api_calling
display_name: API调用
description: 调用外部API接口获取数据。触发条件：需要调用第三方API、发送HTTP请求。跳过条件：内部数据查询或文件读写不使用此 Skill。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: inline
executable: true
permissions:
  - "http:request"
input_schema:
  url:
    type: string
    required: true
  method:
    type: string
    required: true
  headers:
    type: object
  body:
    type: object
output_schema:
  response:
    type: object
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# API调用（Engine）

## SOP
1. 校验 URL 在白名单内，检查认证凭证可用性。
2. 构造请求并发送，处理 HTTP 状态码和重试。
3. 解析响应并返回结构化结果。
