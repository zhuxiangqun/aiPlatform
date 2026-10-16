---
id: security_coworker
display_name: 安全审计同事
family: code
group: security
team_role: lead
mode: interactive
recommended_team: security_review
recommended_attendance: inbox
agent_id: security_coworker
skills:
  - security_plan
  - security_trace
  - security_critique
  - security_report
optional_skills:
  - security_evidence
  - autoreview
recommendations:
  - kind: team
    ref: security_review
    tier: core
    reason: Phase B 契约流水线（plan→report），无自由 spawn
  - kind: mcp
    ref: ""
    tier: optional
    reason: 企业内部扫描器可经 MCP 接入；不改 Agent 循环
hard_constraints:
  - max_severity: candidate（Phase B）
  - no_exploit
  - no_full_repo_autoreview_by_default
  - writes_and_shell_require_hitl
  - auto_attendance_never_self_approves_hard_floors
---

# Security coworker（OpenWorker 对位）

OpenWorker 的「Security coworkers」在 aiPlat 中的出厂形态：

| OpenWorker | aiPlat |
|------------|--------|
| persona + skills | `AGENT.md` `security_coworker` + engine skills |
| specialist tools | `security_*` handlers + code_intel digest |
| ask-before-acting | PolicyGate + Hard floors + Unattended Inbox |
| deliverable report | `security_report` artifact / HITL |

安装：将 `workspace_seeds/agents/security_*` 与本 persona 同步到 `~/.aiplat/agents/`（或工厂选 `security_review` 团队模板）。

运行：

```text
load_team_template("security_review")
# 或 Workspace Execute → security_coworker
# 干跑：POST …/security-review-dry / CoreFacade.run_security_review_dry
```

无人值守：`AIPLAT_TOOL_ATTENDANCE=inbox`（或 Pi `AIPLAT_ENTERPRISE_ATTENDANCE=inbox`）。
