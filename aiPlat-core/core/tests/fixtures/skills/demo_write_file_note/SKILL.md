---
name: demo_write_file_note
display_name: 写文件便签（示范，需审批）
description: 将输入内容写入指定路径（高风险，默认需审批），用于验证权限/审批链路与证据链。
category: execution
version: 0.1.0
status: test_fixture
execution_mode: prompt
permissions:
  - tool:file_write
effects:
  - type: write
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
triggers:
  - 写入文件
  - 保存到文件
  - 生成并写入
  - 记录到便签
input_schema:
  type: object
  properties:
    path:
      type: string
      description: 绝对路径（必须在 AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS 之内）
    content:
      type: string
      description: 写入内容
  required: [path, content]
output_schema:
  type: object
  properties:
    path: {type: string}
    bytes_written: {type: integer}
    sha256: {type: string}
---

# 写文件便签（示范，需审批）

## 目标
把 `content` 写到 `path`，并返回写入后的 sha256 等信息。

## 治理约束
- 该技能默认 requires_approval=true。
- 内部通过 file_operations 工具写入（因此还受 file_operations 的 allowed_roots 约束）。

