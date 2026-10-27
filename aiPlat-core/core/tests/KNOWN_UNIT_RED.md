# core/tests/unit — known red surface (expand-green track)

Baseline after #469 (`66177bc`). PR CI stays focused; nightly collect is hard-fail,
full run informational (`not integration and not slow`).

## Snapshot (local, 2026-10-27)

| Metric | Value |
|--------|------:|
| `pytest core/tests --collect-only` | 3177 / 0 error |
| `core/tests/unit` (maxfail=40) | **40 failed**, 1204 passed, 11 skipped (~5m) |
| Estimated remaining reds | ≫40 (run stopped at maxfail) |

## Failure clusters (first 40)

| Count | Path / theme |
|------:|--------------|
| 10 | `test_harness/test_integration.py` (Harness API drift) |
| 4 | `test_harness/test_graphs/test_planning.py` |
| 3 | `test_apps/test_execution_quality_review.py` |
| 2 | hooks security_scan / architecture_health / adapter_model_injection |
| 1 each | loop defaults, langgraph duration, approval/coding gates, document converters, … |

Do **not** deselect these in nightly yet — keep informational visibility. Fix or
xfail with ticket only when expanding PR green into that package.

## Week track (PR execute expand)

Already green in PR (#468/#469):

- `test_harness/test_observability.py`
- `tool_correctness/test_code_graph.py`
- `apps/fde/test_slice_five_products.py`

**Week 1 (+):**

- `unit/test_agents/` (37 passed)
- `unit/test_utils/` (8 passed)
- `unit/test_harness/test_eval_verdict.py`
- `unit/test_harness/test_completion_receipt.py`
- `unit/test_harness/test_circuit_half_open.py`

**Week 2 (+):**

- `unit/test_api/` (100 passed) — fixed ROLE appendix collapse eating
  `build_sop_role_appendix` body; engine-only skill fixture uses rich SOP.

**Not yet (still red or partial):**

- `test_harness/test_execution/test_loop.py` — 1 fail (`test_loop_config_defaults`)
- `test_harness/test_integration.py` / planning graphs — API drift cluster

## Process

1. Pick a green package → add to `.github/workflows/ci.yml` execute list (+ COLLECT if new).
2. Prefer fixing ≤3 cheap fails to unlock a package over mass deselect.
3. Re-run `pytest core/tests/unit --maxfail=40` periodically; update this table.
