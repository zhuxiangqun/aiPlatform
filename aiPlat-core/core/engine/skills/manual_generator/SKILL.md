---
id: manual_generator
name: manual_generator
display_name: 交付手册生成器
description: 调用 /fde/manual/generate 聚合 Pipeline 数据生成标准交付手册，支持自定义区段保留和版本管理
execution_type: prompt
category: fde
version: 1.0.0
status: enabled
effects:
  - type: read
    resources: ["http://localhost:8002/api/core/fde/manual/generate"]
    idempotent: true
    rollback_available: false
  - type: write
    resources: ["filesystem:~/fde_workspace/"]
    idempotent: false
    rollback_available: true
input_schema:
  type: object
  properties:
    customer_name:
      type: string
      description: 客户名称
    project_name:
      type: string
      description: 项目名称
    pipeline_data:
      type: object
      description: 聚合后的 Pipeline 数据（customer_name, diagnosis_deep_problem, poc_accuracy, canary_passed 等）
output_schema:
  type: object
  properties:
    markdown:
      type: string
      description: 交付手册 Markdown 内容
    manual:
      type: object
  required:
    - markdown
---

# 交付手册生成 Skill

## 触发条件
当 FDE 在 ⑦ 验收移交 Tab 中点击"生成交付手册"时调用。

## SOP

### Step 1: 聚合 Pipeline 数据
- 从 `pipeline_data` 中提取关键字段：`customer_name`、`customer_industry`、`diagnosis_deep_problem`、`poc_accuracy`、`canary_passed`、`canary_score`
- 确认所有必需字段均不为空（缺字段时向 FDE 发出警告）

### Step 2: 调用生成端点
- 通过 `sys_tool_call` 调用 HTTP 请求：`GET /api/core/fde/manual/generate?customer_name={name}&project_name={project}`
- 端点返回完整 Markdown 交付手册，包含：项目概况、诊断回顾、POC结果、部署记录、灰度评测、验收 Checklist

### Step 3: 自定义区段处理
- 如果手册中已有自定义区段（通过 `PUT /api/core/fde/manuals/{project_id}` 编辑），保留它们不被重新生成覆盖
- 自定义区段包括：FDE 签名、客户备注、特别注意事项等

### Step 4: 版本管理
- 生成后通过 `POST /api/core/fde/manuals/{project_id}/regenerate` 创建新版本
- 旧版本通过 `GET /api/core/fde/manuals/{project_id}/versions` 可回溯

## 输出格式

同 `docs/manuals/fde/templates/template-delivery-summary.md` 的完整示例结构。

## 反模式

| 错误 | 正确 |
|------|------|
| 跳过数据完整性检查直接生成 | 先验证所有必需字段，缺字段时报错并列出缺失项 |
| 生成后覆盖客户自定义区段 | 先生成 → 再合并已有自定义内容 → 最后保存 |
| 不创建版本直接覆盖 | 每次生成必须通过 regenerate 端点创建新版本 |
