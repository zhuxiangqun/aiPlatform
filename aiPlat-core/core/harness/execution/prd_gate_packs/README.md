# Builtin PRD gate packs (kernel-only)

This directory may contain **only** cross-cutting packs that belong in the harness
kernel (today: `_common.yaml`).

**Do not** put vertical / industry / product domain rules here (media, finance,
healthcare, …). Those live in:

- `core/workspace_seeds/prd_gates/` — shipped seeds (copied to user dir on start)
- `~/.aiplat/prd_gates/` or `$AIPLAT_PRD_GATES_DIR` — overrides / extra domains

Harness code (`prd_quality_gate.py` + `prd_gate_loader.py`) only interprets YAML.
