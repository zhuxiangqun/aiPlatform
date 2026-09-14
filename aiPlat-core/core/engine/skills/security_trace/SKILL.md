---
name: security_trace
display_name: 安全路径溯源
description: >
  Phase B trace: follow plan hot_paths; read only edge/anchor snippets.
  Do not load whole files or whole repos. Output structured traces.
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline
skill_model_purpose: chat
triggers:
  - security_trace
  - 安全溯源
permissions:
  - llm:generate
  - sys:file_read
  - sys:code_search
effects:
  - type: read
    resources: [filesystem:workspace]
    idempotent: true
    rollback_available: true
input_schema:
  security_plan:
    type: object
    required: true
output_schema:
  traces:
    type: array
    required: true
metadata:
  phase: B
  max_severity: candidate
---

# security_trace

## Goal

For each `security_plan.top_hot_paths` item, produce a **trace** with evidence anchors.

## Hard constraints

1. Read **only** files on the path (entry / via / sink). Cap each snippet to ≤40 lines.
2. Prefer `sys_code_intel_*` over grep/glob. Never target `.` / `*` / whole repo.
3. Do **not** claim confirmed vulnerability. Label `confidence: heuristic`.
4. If gate symbols appear near the sink (Depends, PolicyGate, check_ssrf), note them even if not on import path.
5. Output JSON only:

```json
{
  "traces": [
    {
      "path_id": "path:1",
      "entry_id": "...",
      "sink_id": "...",
      "anchors": [{"file": "...", "line": 1, "snippet": "..."}],
      "possible_gates": [],
      "confidence": "heuristic",
      "notes": []
    }
  ],
  "notes": []
}
```

## Anti-patterns

- Loading entire modules "for context"
- Calling autoreview
- Writing exploit PoCs or attack payloads
