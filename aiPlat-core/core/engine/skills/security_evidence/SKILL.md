---
name: security_evidence
display_name: 安全证据门（Phase C）
description: >
  Phase C: promote/refute Phase B candidates via mocked behavioral asserts
  and durable regression_evidence. Default OFF. No exploit PoCs. No live SSH/network.
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline
skill_model_purpose: chat
triggers:
  - security_evidence
  - phase_c
permissions:
  - sys:exec_cmd
effects:
  - type: read
    resources: [filesystem:workspace]
    idempotent: true
    rollback_available: true
  - type: write
    resources: [filesystem:~/.aiplat/cache]
    idempotent: false
    rollback_available: false
input_schema:
  security_report:
    type: object
    required: true
  enabled:
    type: boolean
    default: false
output_schema:
  phase:
    type: string
  results:
    type: array
    required: true
metadata:
  phase: C
  default_enabled: false
---

# security_evidence

## Goal

Only `severity=candidate` findings. Produce `confirmed|refuted|inconclusive`
with durable `regression_evidence` JSON. Never invent exploits.

## Enable

- `enabled=true` in params / node_config, **or**
- env `AIPLAT_SECURITY_PHASE_C=1`

Default is OFF (skip_stage / empty results).

## Assert catalog (mocked)

| category | assert |
|----------|--------|
| ssrf / network_egress | `is_blocked_url` on fixture private/file URLs |
| rce / eval_exec (ssh driver) | SSHExecDriver rejects eval/exec **before** subprocess |
| other | inconclusive |

## Promotion

- `confirmed` — assert proves missing control / unsafe behavior (rare; needs evidence blob)
- `refuted` — assert proves mitigation (e.g. driver reject) with evidence
- `inconclusive` — sandbox/env missing or no mapped assert

## Forbidden

- Real SSH / real network egress
- Exploit payloads / attack scripts
- Escalating Phase B candidates without evidence file
