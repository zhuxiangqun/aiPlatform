---
name: security_plan
display_name: 安全视图计划（确定性）
description: >
  Phase B plan stage: compile/filter Phase A secview digest. No LLM.
  Outputs top hot_paths for trace. Severity cap remains candidate.
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline
skill_model_purpose: chat
triggers:
  - security plan
  - security_plan
  - 安全审计计划
permissions:
  - sys:code_search
effects:
  - type: read
    resources: [filesystem:workspace]
    idempotent: true
    rollback_available: true
input_schema:
  max_paths:
    type: number
    default: 12
  max_depth:
    type: number
    default: 6
  force:
    type: boolean
    default: false
output_schema:
  schema_version:
    type: string
    required: true
  top_hot_paths:
    type: array
    required: true
  params:
    type: object
    required: true
metadata:
  phase: B
  max_severity: candidate
---

# security_plan

Deterministic planner. Calls `build_security_view` + filters by Phase B params.

## Rules

1. No LLM. Prefer cache unless `force=true`.
2. Default sink whitelist: subprocess, eval_exec, network_egress, deserialize, sql.
3. Prefer entry layers platform/app when enough paths remain.
4. Every hot_path stays `heuristic: true`; severity never exceeds `candidate`.
5. Embed `_token_estimate` and compile metrics for baseline headers.
