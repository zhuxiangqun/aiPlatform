"""T0 in-scope contract readiness — validate Frozen fixtures (not execute)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.long_context_fixture_schema import (
    FIXTURE_SCHEMA,
    validate_long_context_fixture,
)
from core.apps.eval.service.mock_tools.catalog_load import load_mock_tool_catalog
from core.apps.eval.service.session_case_schema import (
    SESSION_SCHEMA,
    validate_session_case_fields,
)
from core.apps.eval.service.tool_eval_runtime_map import (
    RUNTIME_MAP_SCHEMA,
    tool_eval_runtime_map_document,
    validate_tool_backend_runtime,
)

CONTRACTS_SCHEMA = "eval.agent.inscope_contracts.t0"


def evaluate_t0_inscope_contracts(
    *, seed_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Validate T0 sample fixtures + runtime map (read-only; does not mutate frozensets)."""
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    try:
        catalog = load_mock_tool_catalog(
            path=root / "fixtures" / "mock_tools" / "catalog.sample.json"
        )
        checks.append(
            {
                "id": "mock_tool_catalog",
                "ok": True,
                "detail": f"tools={len(catalog.get('tools') or [])}",
            }
        )
    except Exception as exc:
        checks.append({"id": "mock_tool_catalog", "ok": False, "detail": str(exc)})
        blockers.append("mock_tool_catalog_invalid")

    session_path = root / "fixtures" / "session" / "session_case.sample.json"
    try:
        session_case = json.loads(session_path.read_text(encoding="utf-8"))
        serr = validate_session_case_fields(session_case)
        ok = not serr
        checks.append(
            {
                "id": "session_case_sample",
                "ok": ok,
                "detail": ",".join(serr) if serr else SESSION_SCHEMA,
            }
        )
        if not ok:
            blockers.append("session_case_sample_invalid")
    except Exception as exc:
        checks.append({"id": "session_case_sample", "ok": False, "detail": str(exc)})
        blockers.append("session_case_sample_missing")

    lc_path = root / "fixtures" / "long_context" / "fixture.sample.json"
    try:
        fixture = json.loads(lc_path.read_text(encoding="utf-8"))
        lerr = validate_long_context_fixture(fixture)
        ok = not lerr
        checks.append(
            {
                "id": "long_context_fixture_sample",
                "ok": ok,
                "detail": ",".join(lerr) if lerr else FIXTURE_SCHEMA,
            }
        )
        if not ok:
            blockers.append("long_context_fixture_invalid")
    except Exception as exc:
        checks.append(
            {"id": "long_context_fixture_sample", "ok": False, "detail": str(exc)}
        )
        blockers.append("long_context_fixture_missing")

    pair_errs = validate_tool_backend_runtime(
        tool_backend="mock", runtime_tier="workspace_execute"
    )
    live_mismatch = validate_tool_backend_runtime(
        tool_backend="mock", runtime_tier="pi"
    )
    map_ok = not pair_errs and bool(live_mismatch)
    checks.append(
        {
            "id": "tool_runtime_map",
            "ok": map_ok,
            "detail": RUNTIME_MAP_SCHEMA if map_ok else "map_rules_failed",
        }
    )
    if not map_ok:
        blockers.append("tool_runtime_map_invalid")

    return {
        "schema": CONTRACTS_SCHEMA,
        "ok": not blockers,
        "checks": checks,
        "blockers": blockers,
        "runtime_map": tool_eval_runtime_map_document(),
        "v1_in_scope_unchanged": True,
        "note": "T0 contracts only; A3-A5/A8/A9 remain unknown until G6",
    }
