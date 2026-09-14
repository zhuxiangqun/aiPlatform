---
name: security_planner
display_name: 安全计划器
description: Phase B — 确定性安全视图计划（security_plan handler，无自由 spawn）
agent_type: react
version: 1.0.0
status: ready
category: analysis
tags: [security, phase_b]
required_skills: [security_plan]
skills: [security_plan]
tools: []
skill_model_purpose: chat
config:
  system_prompt: >
    你是 security_planner。只执行 security_plan。禁止动态拉起其他 Agent。
    产出 security_plan artifact；severity 上限 candidate。
---

## 交接规范

1. **做了什么**：编译并过滤 secview digest
2. **产出物在哪**：state["security_plan"]
3. **如何验证**：top_hot_paths 非空或明确为空列表；params.heuristic=true
4. **已知问题**：无
5. **下一步**：security_tracer
