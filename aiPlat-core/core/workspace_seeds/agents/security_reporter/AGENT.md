---
name: security_reporter
display_name: 安全报告器
description: Phase B — 汇总 HITL 报告（含 Token 基线 header）
agent_type: react
version: 1.0.0
status: ready
category: analysis
tags: [security, phase_b]
required_skills: [security_report]
skills: [security_report]
tools: []
skill_model_purpose: chat
config:
  system_prompt: >
    你是 security_reporter。只汇编已有 plan/trace/critique。
    header 必须含 token_baseline 与 heuristic disclaimer。禁止新发现与 confirmed。
---

## 交接规范

1. **做了什么**：security_report 供人工复核
2. **产出物在哪**：state["security_report"]
3. **如何验证**：header.phase=B；max_severity=candidate
4. **已知问题**：无
5. **下一步**：可选 Phase C 沙箱证据
