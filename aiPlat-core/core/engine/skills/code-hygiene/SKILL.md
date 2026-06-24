---
name: code-hygiene
display_name: Code Hygiene (Karpathy Principles)
description: AI 编码行为规范——减少 LLM 常见编程错误。基于 Andrej Karpathy 的 CLAUDE.md 最佳实践，融入 aiPlat
  架构规约。用于编程类 Agent 的系统 prompt 注入，确保代码质量、最小改动面、可验证闭环。
category: development
version: 1.0.0
status: enabled
completion_criterion: |
  1. 每个改动都有明确的验收标准（可验证的 pass/fail 条件）
  2. 如存在相关测试，修改后所有测试通过或明确标注预期失败
  3. 不产生新的已知 lint 问题
execution_type: prompt
effects:
- type: read
  resources: []
  idempotent: true
  rollback_available: false
tags:
- coding
- hygiene
- qa
- best-practices
keywords:
  objects:
  - 代码
  - 代码库
  - 项目
  actions:
  - 清理
  - 重构
  - 优化
  - 审查
  constraints:
  - Karpathy原则
  - 复杂度
  - 重复度
trigger_conditions:
- when: 用户要求代码卫生检查
  query: 代码卫生/清理代码/代码质量
- when: 不应用场景
  description: 跳过条件：代码量极少（<50行）或有明确的人为编码规范时不触发。
input_schema:
  context:
    type: string
    required: true
    description: 当前编码上下文
output_schema:
  principles:
    type: string
    required: true
    description: 注入的编码行为规范
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
skip_when: 跳过条件：代码量极少（<50行）或有明确的人为编码规范时不触发。
---





## 1. Think Before Coding — 先思考再编码

**不假设、不隐藏困惑、暴露权衡。**

动手之前：
- 明确说出你的假设。不确定就提问。
- 如果存在多种解释，呈现它们——不要默默选择。
- 如果存在更简单的方案，说出来。在合理的时候提出反对意见。
- 如果有东西不清楚，停下来。说出困惑所在。提问。

输出澄清时：
- 你发现的歧义点
- 2~3 个可选方案（各自利弊）
- 你推荐的默认方案

## 2. Simplicity First — 简洁优先

**最小代码解决问题。不添加推测性内容。**

- 不要引入"未来可能用到"的抽象或配置
- 不要为一次性代码建立新框架层或基类
- 不要为了"可扩展"而扩展——除非被明确要求
- 不要为不可能的场景添加错误处理
- **如果你写了 200 行代码可以缩到 50 行，重写它**

自检："一个资深工程师 review 时会不会说太复杂/太重了？"——如果会，简化它。

## 3. Surgical Changes — 精准修改

**只碰必须碰的。只清理自己制造的混乱。**

编辑现有代码时：
- 不要"改善"相邻的代码、注释或格式
- 不要重构没有坏的东西
- 匹配现有风格——即使你更想用另一种方式
- 如果发现旁边有无关的死代码，**指出它**——不要删除它

当你的修改产生了孤儿代码：
- 删除你的修改导致不再使用的 imports / 变量 / 函数
- 不要删除本来就存在的死代码——除非被明确要求

**溯源测试**：diff 中的每一行修改都应该能直接追溯到用户的需求。

## 4. Goal-Driven Execution — 目标驱动

**定义成功标准。循环直到验证通过。**

把任务转化为可验证的目标：
- "添加验证" → "为非法输入写测试，让它们通过"
- "修复 bug" → "写一个能复现它的测试，让它通过"
- "重构 X" → "确保重构前后测试都通过"

多步骤任务先给简短计划：
```
1. [步骤] → verify: [检查]
2. [步骤] → verify: [检查]
3. [步骤] → verify: [检查]
```

**为什么这个很重要**：强成功标准让你可以独立循环。弱标准（"让它能用"）需要持续的澄清。

---

## aiPlat 项目特定规则（附加）

以下规则补充到通用编码卫生之上，适用于本仓库：

- Architecture Guard: `bash scripts/architecture_guard.sh` 必须在改动后通过
- 跨层导入: 遵循 `app → platform → core → infra` 单向依赖
- 门面优先: API 通过 CoreFacade 访问引擎，禁止直接 import `core.harness.execution.*`
- 接线完整: 新公共方法必须有至少 1 个非测试调用者
- 配置驱动: Harness 层禁止硬编码业务概念（agent_id 字符串匹配 / 业务阶段名）

---

**这些规范生效的标志**：diff 中不必要的修改变少了，因过度复杂导致的重写变少了，澄清问题在实现之前提出而不是在犯错之后。
