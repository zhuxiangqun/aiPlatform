# MODULE.md — {capability_id} charter (template)

> Status: Draft · Owner: {owner} · Level target: A1 → …

## Scope

- …

## Non-goals

- …

## Public API

- …

## Data owned

- … (no cross-module table reads)

## Dependencies

- Shared kernel only (contracts / identity client / telemetry)
- **Forbidden**: other capability internal imports

## Deploy unit

- Central | Field | Edge

## SLO / disable behavior

- When disabled: host degrades, does not crash

## CODEOWNERS

- `{path} @owner`
