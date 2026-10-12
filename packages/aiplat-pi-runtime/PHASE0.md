# Phase 0 hard gate — aiplat-pi-runtime

Run after `pi` is installed (Node ≥ 22.19):

```bash
# from repo root
cd packages/aiplat-pi-runtime
pi -e . --help   # package loads

# interactive (recommended for human check)
AIPLAT_APP_HOME=  pi -e .
# then:
#   /aiplat-status
#   /aiplat-sop-check          → reply must contain AIPLAT_SOP_INJECT_OK
#   /skill:fixture-skill      → reply must contain AIPLAT_FIXTURE_SKILL_OK
#   /skill-test               → same intent via registerCommand
# ask model to call tool aiplat_handler with skill=fixture → AIPLAT_HANDLER_ECHO_OK
```

## Checklist

| # | Check | Evidence |
|---|--------|----------|
| 1 | Skills auto-discover from package `skills/` | `/skill:fixture-skill` works |
| 2 | `before_agent_start` systemPrompt inject | `/aiplat-sop-check` → `AIPLAT_SOP_INJECT_OK` |
| 3 | `registerCommand` | `/aiplat-status`, `/skill-test` |
| 4 | `registerTool` + Python stdin/stdout | `aiplat_handler` → `AIPLAT_HANDLER_ECHO_OK` |
| 5 | Local package load | `pi -e .` / `pi install ./packages/aiplat-pi-runtime` |

## Doc-backed conclusions (pre-install)

From Pi upstream docs (coding-agent):

- **Skills**: conventional `skills/` + package `pi.skills` — Scheme A OK; no `registerSkill` needed.
- **systemPrompt**: `before_agent_start` may return `systemPrompt` / `forceSystemPrompt` — inject path OK.
- **Commands/Tools**: `registerCommand` / `registerTool` (`defineTool`) documented.

Live smoke still required on a machine with `pi` + network LLM (or print mode).
