"""Load T1 out-of-scope A3/A4 fixture cases (not in V1 bank until G6)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.subject_adapter import get_subject_adapter

FIXTURE_CAPS = ("tool_selection", "tool_args")


def _fixtures_root(seed_dir: Optional[Path] = None) -> Path:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    return root / "fixtures"


def load_tool_capability_fixture_cases(
    *,
    seed_dir: Optional[Path] = None,
    capability_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load fixtures/tool_selection/*.json and fixtures/tool_args/*.json arrays."""
    root = _fixtures_root(seed_dir)
    caps = [capability_id] if capability_id else list(FIXTURE_CAPS)
    rows: List[Dict[str, Any]] = []
    for cap in caps:
        path = root / cap / "cases.json"
        if not path.is_file():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"fixture must be array: {path}")
        for item in raw:
            if isinstance(item, dict):
                rows.append(dict(item))
    rows.sort(key=lambda c: str(c.get("case_id") or ""))
    return rows


def run_tool_fixture_suite(
    *,
    seed_dir: Optional[Path] = None,
    capability_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute+judge each fixture case (scripted tool_calls). claim stays false."""
    adapter = get_subject_adapter("agent")
    cases = load_tool_capability_fixture_cases(
        seed_dir=seed_dir, capability_id=capability_id
    )
    results: List[Dict[str, Any]] = []
    passed = 0
    for case in cases:
        exe = adapter.execute(case)
        # Judge from harness trace even when execute status=error (negatives).
        trace = {
            "tool_calls": exe.get("tool_calls")
            or (exe.get("harness") or {}).get("tool_calls")
            or [],
            "tool_results": exe.get("tool_results")
            or (exe.get("harness") or {}).get("tool_results")
            or [],
            "tool_backend": exe.get("tool_backend") or "mock",
        }
        judgment = adapter.judge(case, trace)
        norm = adapter.normalize(case, exe, judgment)
        expect_fail = bool(case.get("expect_judge_fail"))
        judge_passed = bool(judgment.get("passed"))
        if expect_fail:
            ok = not judge_passed
        else:
            ok = judge_passed and str(exe.get("status")) == "ok"
        if ok:
            passed += 1
        results.append(
            {
                "case_id": case.get("case_id"),
                "ok": ok,
                "expect_judge_fail": expect_fail,
                "execute_status": exe.get("status"),
                "judge_passed": judge_passed,
                "errors": norm.get("errors") or judgment.get("errors") or [],
            }
        )
    return {
        "schema": "eval.tool_fixture_suite.v1",
        "ok": passed == len(cases) and len(cases) >= 10,
        "n_cases": len(cases),
        "n_passed": passed,
        "claim_eligible": False,
        "v1_in_scope": False,
        "results": results,
    }
