---
name: test_case_generation
display_name: 测试用例生成
description: 根据 PRD 的 acceptance_criteria 生成结构化测试用例。触发条件：QA阶段自动触发。跳过条件：非功能需求变更。
category: quality
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "fs:write"
  - "fs:read"
effects:
  - type: write
    resources: ["filesystem:/tmp"]
    idempotent: true
    rollback_available: true
input_schema:
  prd:
    type: object
    required: true
output_schema:
  test_cases:
    type: array
  markdown:
    type: string
---

# 测试用例生成（Engine）

## SOP
1. 读取 PRD 的 functional_requirements 和 acceptance_criteria。
2. 按风险分级策略：高风险接口→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常。
3. 输出结构化 test_cases JSON。
4. 标注覆盖矩阵（接口×维度）。
