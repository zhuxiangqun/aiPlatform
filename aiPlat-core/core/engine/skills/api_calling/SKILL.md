---
name: api_calling
display_name: API调用
description: 调用外部API接口获取数据。触发条件：需要调用第三方API、发送HTTP请求。跳过条件：内部数据查询或文件读写不使用。涉及代码生成和接口审查。 涉及API相关操作。 主要进行调用。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
- http:request
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
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
metadata:
  trigger_conditions:
  - 调用API
  - 发送HTTP请求
  - 请求接口
  - 调用外部服务
  - fetch数据
  - REST API
  - 接口调用
  - HTTP请求
  keywords:
    objects:
    - API
    - REST接口
    - HTTP端点
    - 外部服务
    actions:
    - 调用
    - 请求
    - 发送
    - fetch
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 安全地调用外部 API 并返回结构化响应
---

# API调用（Engine）

## SOP
1. 校验 URL 在白名单内，检查认证凭证可用性。
2. 构造请求并发送，处理 HTTP 状态码和重试。
3. 解析响应并返回结构化结果。

## 目标
安全地调用外部 API 并返回结构化响应

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注