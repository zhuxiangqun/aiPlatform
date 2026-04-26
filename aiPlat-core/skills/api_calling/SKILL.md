---
name: api_calling
display_name: API调用
description: 按指定接口文档调用外部/内部 API 获取数据，并处理鉴权、重试与错误映射。
category: execution
version: 1.0.0
status: enabled
execution_mode: inline
executable: true
permissions:
  - "llm:generate"
trigger_conditions:
  - "调用接口"
  - "请求API"
  - "调一下这个服务"
input_schema:
  endpoint:
    type: string
    required: true
    description: API 地址或接口名称
  method:
    type: string
    required: false
    description: HTTP 方法（GET/POST/...）
  payload:
    type: object
    required: false
    description: 请求体/参数
output_schema:
  response:
    type: object
    description: API 响应
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
---

# API调用

## 目标
稳定完成 API 调用，并在失败时给出可诊断的错误信息与重试建议。

## 工作流程（SOP）
1. 明确 endpoint/method/参数/鉴权方式（token、header、cookie）。
2. 组织请求并调用，记录 request_id/trace_id（如有）。
3. 处理常见错误：
   - 4xx：参数/权限/资源不存在
   - 5xx：服务异常/超时
4. 输出结构化结果：状态码、关键字段、错误信息与下一步建议。

## 质量要求（Checklist）
- [ ] 输出包含可诊断信息（状态码/错误体/trace）
- [ ] 不泄漏敏感信息（token/密钥）
