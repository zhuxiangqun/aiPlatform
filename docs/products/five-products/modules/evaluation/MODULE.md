---
doc_type: Report
doc_id: MODULE_9B2AB7
last_reviewed: 2026-11-15
status: active
authority: supporting
---
# MODULE.md — Evaluation Service

> Status: **A2 + D1 Thin (D1c/cohost) + D2 ops pack** · A3 **Accepted（有条件）** · Owner: platform · Deploy unit: **Central**  
> **文档入口**：先读 [`README.md`](./README.md)（现行权威 vs 历史收口）。生命周期：[`../../../../../reports/products/five-products/ops/EVAL_DOCS_LIFECYCLE.md`](../../../../../reports/products/five-products/ops/EVAL_DOCS_LIFECYCLE.md)。

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
| Eval Protocol v0 | `packages/aiplat-evaluation/contracts/schemas/eval_protocol.schema.json`（模块内为 shim） |
| validate（SSOT） | `python3 packages/aiplat-evaluation/contracts/validate_sample.py` |
| validate（legacy shim） | `python3 docs/.../evaluation/contracts/validate_sample.py` — **已修复**（`parents[6]` → repo root） |
| docs gate | `python3 packages/aiplat-evaluation/scripts/check_eval_module_docs.py` |

完整契约清单见 [`module.yaml`](./module.yaml) `contracts`（6 个 schema，SSOT 均在 package）。

## SLO / disable behavior

- When disabled: host skips eval routes/jobs; pipelines that need eval degrade with explicit skip, no crash

## CODEOWNERS

与仓库 [`.github/CODEOWNERS`](../../../../../.github/CODEOWNERS) 对齐（以仓库文件为准）：

- `/packages/aiplat-evaluation/` → `@zhuxiangqun`
- `/docs/products/five-products/modules/evaluation/` → `@zhuxiangqun`

（平台侧 `aiPlat-platform/apps/eval/` 无单独 CODEOWNERS 条目；日常变更仍走产品 owner 评审。）

## Wiring (A1)

> **契约目标**：下列端点的响应应包含 `eval_protocol`（服务层已 `attach_eval_protocol`）。  
> **HTTP 层（2026-11-15）**：`common_schemas` 已 `extra="allow"`；Item 端点统一 `{"data": …}`；store 列表改为 `ItemResponse`。回归：`aiPlat-platform/tests/test_eval_response_models.py`。

| Path | Behavior（契约） | 当前状态 |
|------|----------|----------|
| `POST …/runs/{id}/evaluate` | response includes `eval_protocol` | 已修复（StatusResponse 保留额外字段） |
| `POST …/runs/{id}/evaluate/auto` | response includes `eval_protocol` | 已修复 |
| `GET …/runs/{id}/evaluation/latest` | response includes `eval_protocol` | 已修复（`{"data": …}`） |
| `POST …/skill-evals/suites/{id}/run` | response includes `eval_protocol` | 已接线（`data` 嵌套） |
| `GET …/skill-evals/runs/{id}` | response includes `eval_protocol` | 已修复（`{"data": …}`） |
| `POST …/code-review-gold/evaluate` (+ reevaluate) | `eval_protocol` | 已修复（顶层协议字段保留） |
| `POST …/kb-eval/run` | `eval_protocol` | 已修复 |
| `POST …/prompts/eval/runs` (+ GET run) | `eval_protocol` | 已修复 |
| `POST …/arena/run` | `eval_protocol` | 已核实（`arena_wiring` 直接返回 `Dict`，无 `response_model`；协议字段靠裸 dict 保留） |
| Adapter | `core.harness.evaluation.eval_protocol` via CoreFacade | 服务层已接线 |
| `GET /api/core/eval/healthz` | `product_id=evaluation` | 已接线 |

## D1 (Thin, co-hosted) — done

| Item | Path |
|------|------|
| Package | `packages/aiplat-evaluation` |
| Install / smoke | `scripts/d1_install.sh` / `d1_smoke.sh` |
| Docs | `packages/aiplat-evaluation/docs/INSTALL.md` |
| healthz schema | `packages/aiplat-evaluation/contracts/schemas/healthz.schema.json`（模块内为 shim） |

## D2 cohost ops pack — done (local)

| Item | Path |
|------|------|
| Scope | `docs/D2_COHOST.md` · `SECURITY.md` · `PERF_BASELINE.md` |
| Baseline | `security/baseline.yaml` · `scripts/d2_admin_check.sh` |
| Upgrade / rollback | `d1_upgrade.sh` · `d1_rollback.sh --runtime` |
| Closeout | `scripts/d2_local_closeout.sh` · [`ops/EVALUATION_D2_LOCAL_CLOSEOUT.md`](../../../../../reports/products/five-products/ops/EVALUATION_D2_LOCAL_CLOSEOUT.md) |

`current_delivery` 仍为 **D1**（D1c；与 [`module.yaml`](./module.yaml) / `capabilities.manifest.yaml` 一致）；D2 ops pack **本地完成 ≠ 独立交付升级**。`process_split_authorized=false`。

A3 process/DB split **forbidden** without ADR Accepted + `process_split_authorized`。

## A3 prep (Accepted 有条件 · not authorized)

| Item | Path |
|------|------|
| ADR | `docs/decisions/products/five-products/ADR-EVALUATION-A3.md` **Accepted（有条件）**（`module.yaml` `adr_for_a3` 已指向） |
| Chart skeleton | `packages/aiplat-evaluation/chart/` (`a3_process_split_authorized=false`) |
| Checklist / prep | `docs/a3/SPLIT_CHECKLIST.md` · `scripts/a3_prep_check.sh` |
| Local rehearsal | `scripts/a3_local_rehearsal.sh`（#4→🟨；非 live） |

## EVAL_V1 E7

- Charter E7 **PASS** — [`ops/EVAL_V1_E7_CLOSEOUT.md`](../../../../../reports/products/five-products/ops/EVAL_V1_E7_CLOSEOUT.md)
- D3 local UAT：`scripts/d3_local_acceptance.sh`（environment=local；不 authorize）

## Next

- **P2 staging**：见 [`P2_STAGING_ROADMAP.md`](../../../../../packages/aiplat-evaluation/docs/a3/P2_STAGING_ROADMAP.md) — 阻塞在独立 staging host；`ready_to_authorize=false`
- Field/edge eval hosting not in scope
- P3 生产在线评测（trace 采样）在 P2 授权前不立项为发布门禁
