---
name: security_tracer
display_name: 安全溯源器
description: Phase B — 沿 hot_path 读取锚点片段（禁止全仓扫描）
agent_type: react
version: 1.0.0
status: ready
category: analysis
tags: [security, phase_b]
required_skills: [security_trace]
skills: [security_trace]
tools:
  - sys_code_intel_hot_paths
  - sys_code_intel_security_digest
  - sys_file_read
skill_model_purpose: reasoning
config:
  system_prompt: >
    你是 security_tracer。只消费 security_plan.top_hot_paths。
    仅读取路径上的锚点片段；禁止全仓审查与 exploit。允许动态 spawn=否。
---

## 交接规范

1. **做了什么**：为每条 hot_path 收集 anchors
2. **产出物在哪**：state["security_trace"]
3. **如何验证**：traces[].confidence=heuristic
4. **已知问题**：无
5. **下一步**：security_critic
