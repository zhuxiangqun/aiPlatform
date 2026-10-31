# MODULE.md — Ontology Service

> Status: **A2 + D1 Thin (co-hosted)** · A3 **Accepted（有条件）** · Owner: platform · Deploy unit: **Central**

## Scope

- Digital asset inventory: connectors (docs / repos / code / Wiki), entity/relation extract, graph, LLM Wiki
- v1: **read-only inventory** (document-first); not “all asset types”
- Query API for entities / relations / subgraph / wiki pages

See [`ONTOLOGY_API.md`](./ONTOLOGY_API.md).

## Non-goals

- Agent lifecycle or general Runtime
- FDE project facts or Evaluation scoring
- Write-heavy enterprise MDM in v1
- A3 split without ADR

## Public API

- Ontology API v0 envelope: entity / relation / graph / wiki / asset
- As-is home: `aiPlat-core/core/harness/knowledge` (+ knowledge_pipeline); extract later
- Consumers via **CoreFacade** only (no harness internal imports from platform apps)

## Data owned

- Graph index, asset metadata, wiki pages, domain ontology YAML under `$AIPLAT_HOME/ontologies`
- Cross-domain edges via registry — not FDE/Eval tables

## Dependencies

- Shared kernel: Ontology API schema, Identity for ACL
- **Forbidden**: FDE / Evaluation / Pi internals; DomainRouter must stay config-driven

## Deploy unit

- **Central** (default); optional Field read-only cache later
- A3 → `a3_adr_required: true`

## Contracts (A1)

| Schema | Path |
|--------|------|
| healthz | `contracts/schemas/healthz.schema.json` |
| Ontology API v0 | `contracts/schemas/ontology_api.schema.json` |
| validate | `python3 contracts/validate_sample.py` |

## SLO / disable behavior

- When disabled: retrieval/wiki paths return empty or 503; Agent runtime continues without graph enrichment

## CODEOWNERS

- `aiPlat-core/core/harness/knowledge*/ @platform`
- Ontology seeds: workspace `ontologies/` `@platform`

## Wiring (A1)

| Path | Behavior |
|------|----------|
| `GET …/wiki/query-structured` | response includes `ontology_api` |
| `GET …/wiki/pages` | response includes `ontology_api` |
| `GET …/wiki/engine/graph-stats/{domain_id}` | response includes `ontology_api` |
| `CoreFacade.wiki_*_api` / `get_graph_health_api` | attach envelope helpers |
| Adapter | `core.harness.knowledge.ontology_api` via CoreFacade |
| `GET /api/core/ontology/healthz` | `product_id=ontology` |

## D1 (Thin, co-hosted) — done

| Item | Path |
|------|------|
| Package | `packages/aiplat-ontology` |
| Install / smoke | `scripts/d1_install.sh` / `d1_smoke.sh` |
| Docs | `packages/aiplat-ontology/docs/INSTALL.md` |

A3 process split **forbidden** without ADR Accepted + `process_split_authorized`.

## A3 prep (Draft · not authorized)

| Item | Path |
|------|------|
| ADR | `reports/five-products/ADR-ONTOLOGY-A3.md` **Accepted（有条件）** |
| Chart skeleton | `packages/aiplat-ontology/chart/` (`a3_process_split_authorized=false`) |
| Checklist / prep | `docs/a3/SPLIT_CHECKLIST.md` · `scripts/a3_prep_check.sh` |
| Local rehearsal | `scripts/a3_local_rehearsal.sh`（#3/#5→🟨；非 live） |

## Next

- Live migration / dual-write / rollback drills → then authorize split
