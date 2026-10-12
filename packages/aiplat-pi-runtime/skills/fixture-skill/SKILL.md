---
name: fixture-skill
description: Phase 0 smoke skill for aiplat-pi-runtime. Use when verifying Pi skill auto-discovery or when the user asks for fixture-skill.
---

# Fixture skill (aiPlat Pi Runtime)

You are verifying that Pi discovered this skill from the package `skills/` directory.

When invoked via `/skill:fixture-skill` or selected by the model:

1. Reply with exactly one short paragraph confirming the skill loaded.
2. Include the marker string `AIPLAT_FIXTURE_SKILL_OK` in the reply.
3. Do not invent file changes or tool calls unless the user asks.
