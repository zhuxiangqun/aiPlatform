---
name: verify_tool_agent
display_name: verify_tool_agent
description: 工具验证 Agent，负责 skill_load 调用和工具正确性验证。引擎内置（engine）。
agent_type: tool
version: 1.0.0
status: ready
model: deepseek-reasoner
protected: true
category: quality
tags: [verification, tool, validation]
phase: review
required_skills: [code_review, test_case_generation]
pipeline:
  output_artifact: verify_report
  phase: testing
  auto_hitl: true
  phase_description: 工具验证
required_tools:
- skill_load
- sysgraph_search
- sysgraph_context
config:
  max_tokens: 100
  temperature: 0.0
---
# verify_tool_agent

## 目标
说明该 Agent 的职责边界与适用场景。

## 工作流程（SOP）
1. 第一步……
2. 第二步……

> 探索代码结构时优先用 sysgraph_* 工具（比 grep/read 快 10×）
3. 第三步……

## 权限与工具
- required_tools：['skill_load']
- required_skills：[]

## 交接规范
1. **做了什么**：工具验证完成，输出验证报告
2. **产出物在哪**：state["verify_report"]，验证结果在 findings，建议在 recommendations
3. **如何验证**：检查验证用例是否覆盖关键路径；运行 pytest 复现
4. **已知问题**：边界条件可能未完全覆盖；需要代码审查补充
5. **下一步**：对应 developer 根据报告修复问题；重新运行验证
