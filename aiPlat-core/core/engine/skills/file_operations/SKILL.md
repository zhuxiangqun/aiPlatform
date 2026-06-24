---
name: file_operations
display_name: 文件操作
description: 读取、写入、编辑文件的原子操作。只读文件可用sys_code_search处理。涉及代码生成和接口审查。 涉及文件相关操作。 主要进行读写。
category: execution
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
- fs:read
- fs:write
effects:
- type: write
  resources:
  - filesystem:~
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
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 文件操作
  - 读写文件
  - 文件处理
  - 文件管理
  - 文件读写
  - 文件编辑
  - 文件创建
  - 目录操作
  keywords:
    objects:
    - 文件
    - 代码
    - 文本
    actions:
    - 读写
    - 编辑
    - 创建
    constraints:
    - 只读
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 安全执行原子化文件读写编辑操作
protected: true
completion_criterion: |
  1. 每个改动都有明确的验收标准（可验证的 pass/fail 条件）
  2. 如存在相关测试，修改后所有测试通过或明确标注预期失败
  3. 不产生新的已知 lint 问题
keywords:
  objects:
  - 文件
  - 目录
  - 代码文件
  actions:
  - 读取
  - 写入
  - 编辑
  - 创建
  - 删除
  constraints:
  - 文件路径
  - 权限
  - 备份
trigger_conditions:
- when: 用户要求文件操作
  query: 读文件/写文件/编辑
- when: 不应用场景
  description: 跳过条件：路径涉及系统文件（/etc/、~/.ssh/）时不触发；建议人工确认。
skip_when: 跳过条件：路径涉及系统文件（/etc/、~/.ssh/）时不触发；建议人工确认。
---



# 文件操作（Engine）

## SOP
1. 检查路径是否在 workspace 内。
2. 执行读/写/编辑操作。
3. 返回操作结果（success + 字节数/路径）。

## 目标
安全执行原子化文件读写编辑操作

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注