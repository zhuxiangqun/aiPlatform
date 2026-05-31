---
name: file_operations
display_name: 文件操作
description: 读取、写入、编辑文件的原子操作。触发条件：需要读写文件。跳过条件：代码搜索用 sys_code_search 处理。
category: execution
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "fs:read"
  - "fs:write"
effects:
  - type: write
    resources: ["filesystem:~"]
    idempotent: false
    rollback_available: false
input_schema:
  path:
    type: string
    required: true
output_schema:
  result:
    type: object
  markdown:
    type: string
---

# 文件操作（Engine）

## SOP
1. 检查路径是否在 workspace 内。
2. 执行读/写/编辑操作。
3. 返回操作结果（success + 字节数/路径）。
