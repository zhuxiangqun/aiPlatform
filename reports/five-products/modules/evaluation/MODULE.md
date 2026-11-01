# MODULE.md — Evaluation Service

> Status: **A2 + D1 Thin (D1c/cohost) + D2 ops pack** · A3 **Accepted（有条件）** · Owner: platform · Deploy unit: **Central**

## Scope

- Eval Protocol: tasks, sandbox, trajectories, metrics, reports
- First: Agent / Skill / Workflow artifacts; later HTTP/CLI programs
- Independent service/module within Central deploy unit

See [`EVAL_PROTOCOL.md`](./EVAL_PROTOCOL.md).

## Non-goals

- Source-system operational truth (that stays in runtime / FDE evidence)
- “All programs” coverage in v1
- A3 process/DB split without ADR

## Public API

- Eval Protocol v0, Evidence ingest refs, Report schema
- As-is home: `aiPlat-platform/apps/eval` (+ core eval helpers)

## Data owned

- Eval tasks, trajectories, scores, reports (retention policy TBD)
- No reads of Ontology / FDE / tenant tables except via API

## Dependencies

- Shared kernel: Bundle, Evidence, Eval Protocol
- **Forbidden**: aiPlat / FDE / Ontology internal imports
- May read published Artifacts / Evidence only

## Deploy unit

- **Central** (default co-hosted with aiPlat + Ontology)
- A3 → `a3_adr_required: true`

## Contracts (A1)

| Schema | Path |
|--------|------|
| Eval Protocol v0 | `contracts/schemas/eval_protocol.schema.json` |
| validate | `python3 contracts/validate_sample.py` |

## SLO / disable behavior

- When disabled: host skips eval routes/jobs; pipelines that need eval degrade with explicit skip, no crash

## CODEOWNERS

- `aiPlat-platform/apps/eval/ @platform`

## Wiring (A1)

| Path | Behavior |
|------|----------|
| `POST …/runs/{id}/evaluate` | response includes `eval_protocol` |
| `POST …/runs/{id}/evaluate/auto` | response includes `eval_protocol` |
| `GET …/runs/{id}/evaluation/latest` | response includes `eval_protocol` |
| `POST …/skill-evals/suites/{id}/run` | response includes `eval_protocol` |
| `GET …/skill-evals/runs/{id}` | response includes `eval_protocol` |
| `POST …/code-review-gold/evaluate` (+ reevaluate) | `eval_protocol` |
| `POST …/kb-eval/run` | `eval_protocol` |
| `POST …/prompts/eval/runs` (+ GET run) | `eval_protocol` |
| `POST …/arena/run` | `eval_protocol` |
| Adapter | `core.harness.evaluation.eval_protocol` via CoreFacade |
| `GET /api/core/eval/healthz` | `product_id=evaluation` |

## D1 (Thin, co-hosted) — done

| Item | Path |
|------|------|
| Package | `packages/aiplat-evaluation` |
| Install / smoke | `scripts/d1_install.sh` / `d1_smoke.sh` |
| Docs | `packages/aiplat-evaluation/docs/INSTALL.md` |
| healthz schema | `contracts/schemas/healthz.schema.json` |

## D2 cohost ops pack — done (local)

| Item | Path |
|------|------|
| Scope | `docs/D2_COHOST.md` · `SECURITY.md` · `PERF_BASELINE.md` |
| Baseline | `security/baseline.yaml` · `scripts/d2_admin_check.sh` |
| Upgrade / rollback | `d1_upgrade.sh` · `d1_rollback.sh --runtime` |
| Closeout | `scripts/d2_local_closeout.sh` · [`ops/EVALUATION_D2_LOCAL_CLOSEOUT.md`](../../ops/EVALUATION_D2_LOCAL_CLOSEOUT.md) |

`current_delivery` 仍为 **D1**（D1c）；`process_split_authorized=false`。

A3 process/DB split **forbidden** without ADR Accepted + `process_split_authorized`.

## A3 prep (Draft · not authorized)

| Item | Path |
|------|------|
| ADR | `reports/five-products/ADR-EVALUATION-A3.md` **Accepted（有条件）** |
| Chart skeleton | `packages/aiplat-evaluation/chart/` (`a3_process_split_authorized=false`) |
| Checklist / prep | `docs/a3/SPLIT_CHECKLIST.md` · `scripts/a3_prep_check.sh` |
| Local rehearsal | `scripts/a3_local_rehearsal.sh`（#4→🟨；非 live） |

## Next

- Live backup/restore + rollback-to-cohost drills → then authorize split
- Field/edge eval hosting not in scope
