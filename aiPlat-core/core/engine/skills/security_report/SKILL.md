---
name: security_report
display_name: 安全审计报告
description: >
  Phase B report: assemble plan/trace/critique into a human review artifact.
  Header must include token baseline fields. Max severity candidate.
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline
skill_model_purpose: chat
triggers:
  - security_report
  - 安全报告
permissions:
  - llm:generate
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: true
input_schema:
  security_plan:
    type: object
    required: true
  security_trace:
    type: object
  security_critique:
    type: object
    required: true
output_schema:
  header:
    type: object
    required: true
  findings:
    type: array
    required: true
metadata:
  phase: B
  max_severity: candidate
---

# security_report

## Goal

Produce a reviewable report for HITL. No new investigation.

## Header (required)

Include:
- `schema_version`, `phase: B`, `heuristic: true`
- `token_baseline`: digest `_token_estimate` from plan + stage notes if any
- `counts`: findings / refuted / hot_paths_selected
- Disclaimer: reachability ≠ taint; no sandbox confirmation in Phase B

## Findings

Copy from critique; do not escalate severity above `candidate`.
Sort by score/risk from plan when available.

## Output JSON only

```json
{
  "header": {
    "phase": "B",
    "heuristic": true,
    "max_severity": "candidate",
    "token_baseline": {},
    "disclaimer": "call/import reachability ≠ taint; confirmed requires Phase C sandbox"
  },
  "findings": [],
  "refuted": [],
  "next": "optional Phase C evidence for selected candidates"
}
```

## Forbidden

- Inventing new findings not in critique
- Confirmed labels
- Exploit instructions
