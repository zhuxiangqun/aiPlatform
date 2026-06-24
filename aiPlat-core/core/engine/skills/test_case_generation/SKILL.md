---
name: test_case_generation
display_name: 测试用例生成
description: 根据 PRD 的 acceptance_criteria 生成结构化测试用例。触发条件：QA阶段自动触发。跳过条件：非功能需求变更。 涉及测试用例相关操作。
category: quality
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
- fs:write
- fs:read
effects:
- type: write
  resources:
  - filesystem:/tmp
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
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 测试用例
  - 生成测试
  - 单元测试
  - 测试生成
  - 写测试
  - pytest用例
  - 测试覆盖
  keywords:
    objects:
    - 测试用例
    - pytest
    - 验收标准
    actions:
    - 生成
    - 编写
    - 创建
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 根据验收标准生成测试用例
protected: true
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个可执行的验证步骤
  2. 测试覆盖 happy path + 至少一个边界 case
  3. red-capable command 已确认能稳定复现目标行为
keywords:
  objects:
  - 测试用例
  - 测试场景
  - 测试数据
  actions:
  - 生成
  - 编写
  - 设计
  constraints:
  - 覆盖率
  - 边界条件
trigger_conditions:
- when: 用户要求生成测试用例
  query: 生成测试/写测试用例
- when: 不应用场景
  description: 跳过条件：代码模块过小或已有充分测试覆盖时不触发。
skip_when: 跳过条件：代码模块过小或已有充分测试覆盖时不触发。
---



# 测试用例生成（Engine）

## SOP
1. 读取 PRD 的 functional_requirements 和 acceptance_criteria。
2. 按风险分级策略：高风险接口→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常。
3. 输出结构化 test_cases JSON。
4. 标注覆盖矩阵（接口×维度）。

## 目标
根据验收标准生成测试用例

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注