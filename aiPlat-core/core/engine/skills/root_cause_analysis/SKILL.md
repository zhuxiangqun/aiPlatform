---
name: root_cause_analysis
display_name: 根因分析
description: 根据测试失败输出，分析失败根因并给出修复建议。触发条件：测试未通过时。跳过条件：测试全部通过。
category: quality
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "fs:read"
effects:
  - type: read
    resources: ["filesystem:~"]
    idempotent: true
    rollback_available: false
input_schema:
  test_report:
    type: object
    required: true
output_schema:
  analysis:
    type: object
---

# 根因分析（Engine）

## SOP
1. 读取 test_report 中的 failed cases 和 issues。
2. 按错误模式分类：代码逻辑错误、配置错误、环境问题、安全违规。
3. 对每类失败给出根因+建议修复方向。
4. 输出结构化分析报告（root_causes + fix_suggestions）。
