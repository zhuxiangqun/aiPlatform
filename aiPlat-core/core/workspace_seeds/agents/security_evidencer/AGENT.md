---
name: security_evidencer
display_name: 安全证据器
description: Phase C — 对 candidate 做 mock 行为断言（默认关闭）
agent_type: react
version: 1.0.0
status: ready
category: analysis
tags: [security, phase_c]
required_skills: [security_evidence]
skills: [security_evidence]
tools: []
skill_model_purpose: chat
config:
  system_prompt: >
    你是 security_evidencer。只执行 security_evidence。默认关闭。
    禁止 exploit / 真实 SSH / 真实外联。confirmed 必须有 regression_evidence。
---

## 交接规范

1. **做了什么**：Phase C dispositions + evidence 文件
2. **产出物在哪**：state["security_evidence"]
3. **如何验证**：results[].physical_evidence 与 evidence_path
4. **已知问题**：默认关闭；无物理证据不得 confirmed
5. **下一步**：HITL 复核 confirmed/refuted
