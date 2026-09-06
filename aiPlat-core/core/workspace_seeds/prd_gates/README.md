# PRD Gate Packs (workspace seeds)

Declarative **domain** rules for `prd_quality_gate`. Engine only interprets YAML;
do **not** put vertical checklists in Agent/Skill markdown or in harness Python.

## Ownership (kernel-agnostic)

| Location | What belongs here |
|----------|-------------------|
| `core/harness/execution/prd_gate_packs/` | Kernel-only: `_common.yaml` (SSRF / 加密 / 基线约束) |
| **This directory** (`workspace_seeds/prd_gates/`) | Vertical domains only (e.g. `media.yaml`) — no `_common` duplicate |
| `~/.aiplat/prd_gates/` or `$AIPLAT_PRD_GATES_DIR` | Overrides / extra domains |

## Load order (later wins)

1. Package builtins: `prd_gate_packs/` (kernel `_common` only)
2. These seeds: `workspace_seeds/prd_gates/` (vertical packs)
3. User overrides: `~/.aiplat/prd_gates/` or `$AIPLAT_PRD_GATES_DIR`

Server start / first load copies **missing** seed files into `~/.aiplat/prd_gates`
(no overwrite). To pick up repo updates to a domain pack:

```bash
cp aiPlat-core/core/workspace_seeds/prd_gates/media.yaml ~/.aiplat/prd_gates/media.yaml
# or: rm ~/.aiplat/prd_gates/media.yaml  # then restart to re-seed
```

## Pack schema

```yaml
domain_id: media          # unique id; `_common` is always applied
always: false             # true → match every PRD
triggers:                 # regex/literal; any hit → pack applies (if not always)
  - 视频
  - "\\bvideo\\b"

pm_hints:                 # optional; injected into PM chat *before* PRD generation
  - "短句规则…（勿把垂直条款写进 AGENT.md）"

checks:                   # assess-only; block confirm when severity=error
  - id: my_check_code
    severity: error       # error | warning
    block_finalize_wash: true  # optional; raw hit → factory_finalize scrub must NOT green-pass
    when: { all: [ ... ] }
    message: human text

repairs:                  # enrich / factory_finalize word-level rewrites (scrub alone)
  - id: my_repair
    when: { all: [ ... ] }
    actions:
      - set_decision: { key: foo, value: bar }
      - replace_ac: { match: "regex", text: "new AC" }
      - scrub_prose: { match: "regex", text: "replacement" }  # title/desc/FR prose/US story, not ACs
      - annotate_ac: { match: "regex", note: "（注）" }
      - append_ac: { prefer_fr_match: "导入", text: "..." }
      - append_constraint: { key: security, value: "..." }
      - ensure_constraint_platform: "Web"
      - ensure_constraint_security_generic: "HTTPS + authentication"
      - ensure_constraint_performance_from_decision: { key: analysis_sla, fallback: "..." }
      - ensure_constraint_security_ssrf: true
      - infer_url_scope: true
      - infer_speech_pipeline: true

structural_repairs:       # optional; run when wash-blocked codes match clears_codes
  - id: my_structural
    clears_codes: [asr_topic_contradiction]  # may clear wash block after re-assess
    when: { all: [ ... ] }
    actions:
      - upsert_fr: { match: "语音|音轨", fr: { id: FR-004, name: "...", acceptance_criteria: [...] } }
      - upsert_us: { match: "语音|主题", id: US-004, related_fr: [FR-004], story: "..." }
```

`block_finalize_wash`: scrub (`repairs`) alone must not green-pass. `structural_repairs`
rewrites whole FR/US from templates; if those codes no longer fire on re-assess, factory
may READY.
### Condition operators (`when`)

- `always: true`
- `blob_match` / `not_blob_match` — regex on flattened PRD text
- `decision` / `not_decision` — key present & non-empty
- `decision_in` / `not_decision_in` — `{ key, values: [...] }`
- `all` / `any` — nested boolean groups

## Adding a domain

1. Add `my_domain.yaml` here (not under `prd_gate_packs/`), set `domain_id` + `triggers`.
2. Keep checks/repairs domain-specific; put cross-cutting rules in
   `prd_gate_packs/_common.yaml` (kernel), not in this seeds directory.
3. Restart core (or clear pack cache) and confirm with a sample PRD.
