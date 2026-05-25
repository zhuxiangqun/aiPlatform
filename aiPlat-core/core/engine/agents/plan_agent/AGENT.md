---
name: plan_agent
display_name: 任务规划器
description: 基于 Plan-Execute 模式的任务规划 Agent。引擎内置（engine）：仅核心能力层默认可用。
agent_type: plan
version: 1.0.0
status: ready
model: deepseek-reasoner
protected: true
category: engineering
tags: [planning, decomposition]
skills: [task_planning, task_decomposition]
tools: []
---

## 交接协议 (Handoff)

**做了什么**: 执行 plan_agent 的 SOP 定义的任务
**产出物在哪**: state[output_artifact] 中
**如何验证**: 检查 output_artifact 是否存在且非空
**已知问题**: Engine seed — 完整 SOP 需在 workspace agent 中定义
**下一步**: 下游阶段读取本阶段的产出物继续执行
