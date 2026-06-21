---
name: task_planning
display_name: 任务规划
description: 将目标拆解为可执行计划。触发条件：用户描述"怎么实现""拆一下""分几步"等需求。跳过条件：单步骤任务直接执行。 涉及任务相关操作。 主要进行规划。
category: execution
version: 1.0.0
status: enabled
protected: true
execution_mode: prompt
permissions:
- llm:generate
effects:
- type: read
  resources:
  - filesystem:~/.aiplat
  idempotent: true
  rollback_available: false
input_schema:
  goal:
    type: string
    required: true
output_schema:
  plan:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 任务规划
  - 规划
  - 制定计划
  - 任务安排
  - 项目规划
  - 工作安排
  - 排期
  keywords:
    objects:
    - 任务
    - 计划
    - 项目
    actions:
    - 规划
    - 安排
    - 分解
    - 排期
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 根据目标制定执行计划
keywords:
  objects:
  - 任务
  - 计划
  - 步骤
  - 流程
  actions:
  - 规划
  - 拆解
  - 编排
  - 分配
  constraints:
  - 优先级
  - 依赖关系
  - 资源
trigger_conditions:
- when: 用户要求任务规划
  query: 规划/拆解任务/编排
- when: 不应用场景
  description: 跳过条件：任务过于简单（单步可完成）时不触发。
skip_when: 跳过条件：任务过于简单（单步可完成）时不触发。
---



# 任务规划（Engine）

## SOP
1. 明确目标/范围/验收标准/截止时间。
2. 分阶段拆解步骤并标注依赖与风险。
3. 每阶段给出验证方式与回滚建议。

## 目标
根据目标制定执行计划

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注