---
name: security_critique
display_name: 安全路径批评
description: >
  Phase B critique: rule-first refute/keep. Counterfactual gate search.
  Autoreview only on clipped anchors if needed — never full-repo.
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline
skill_model_purpose: chat
triggers:
  - security_critique
  - 安全批评
permissions:
  - llm:generate
  - sys:file_read
effects:
  - type: read
    resources: [filesystem:workspace]
    idempotent: true
    rollback_available: true
input_schema:
  security_plan:
    type: object
    required: true
  security_trace:
    type: object
    required: true
output_schema:
  findings:
    type: array
    required: true
  refuted:
    type: array
    required: true
metadata:
  phase: B
  max_severity: candidate
---

# security_critique

## Goal

Reduce false positives from graph reachability. Keep ≤12 findings, severity ≤ `candidate`.

## Rule-first checklist (do these before any LLM judgment)

1. Edge exists? If entry→sink path not backed by plan/trace anchors → **refute**.
2. Same-file or middleware gate? Search for Depends / PolicyGate / check_ssrf / require_auth near entry → may **refute** or mark `gate_likely`.
3. Sink is intentional ops (health check, installer) with fixed args → **refute** or `accepted_risk`.
4. filesystem_write-only / no user-controlled source in anchors → **refute**.
5. Counterfactual: "If a gate existed, where?" Check decorators, middleware, config YAML — note `gate_search`.

## Autoreview (optional, clipped only)

If still uncertain after rules: you may reason over **anchor snippets already in security_trace** only.
Do **not** invoke full-repo autoreview targets (`.`, `*`, workspace).

## Output JSON only

```json
{
  "findings": [
    {
      "path_id": "path:1",
      "severity": "candidate",
      "category": "ssrf|rce|injection|authz|other",
      "summary": "...",
      "evidence_anchors": [],
      "gate_search": [],
      "heuristic": true
    }
  ],
  "refuted": [
    {"path_id": "path:2", "reason": "..."}
  ]
}
```

## Forbidden

- severity `confirmed` or `critical` (Phase C only)
- Exploit / PoC / weaponized payloads
- Silent drop of findings without `refuted` entry
