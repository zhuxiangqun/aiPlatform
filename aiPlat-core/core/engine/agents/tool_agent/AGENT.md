---
name: tool_agent
display_name: 工具调用器
description: 基于工具使用模式的操作 Agent。引擎内置（engine）：仅核心能力层默认可用。
agent_type: tool
version: 1.0.0
status: running
protected: true
category: engineering
tags: [tool, api, execution]
skills: [api_calling, browser_automation, file_operations]
tools: [search, calculator, sysgraph_search, sysgraph_context]
model: deepseek-chat
---

## 交接协议 (Handoff)

**做了什么**: 执行 tool_agent 的 SOP 定义的任务
**产出物在哪**: state[output_artifact] 中
**如何验证**: 检查 output_artifact 是否存在且非空
**已知问题**: Engine seed — 完整 SOP 需在 workspace agent 中定义
**下一步**: 下游阶段读取本阶段的产出物继续执行

> 探索代码结构时优先用 sysgraph_* 工具（比 grep/read 快 10×）
