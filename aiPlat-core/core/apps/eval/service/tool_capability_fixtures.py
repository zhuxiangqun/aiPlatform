"""Load A3/A4/A5/A9 fixture cases (v1.1 in-scope via mock/session/fixture; claim closed)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.session_runner import (
    group_session_cases,
    run_session_group,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter

FIXTURE_CAPS = (
    "tool_selection",
    "tool_args",
    "tool_result_use",
    "long_context",
)
SESSION_FIXTURE_CAP = "multi_turn_memory"


def _fixtures_root(seed_dir: Optional[Path] = None) -> Path:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    return root / "fixtures"


def load_tool_capability_fixture_cases(
    *,
    seed_dir: Optional[Path] = None,
    capability_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load fixtures/{cap}/cases.json arrays for tool caps."""
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


def load_session_fixture_cases(
    *, seed_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    path = _fixtures_root(seed_dir) / SESSION_FIXTURE_CAP / "cases.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"fixture must be array: {path}")
    return [dict(x) for x in raw if isinstance(x, dict)]


def run_tool_fixture_suite(
    *,
    seed_dir: Optional[Path] = None,
    capability_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute+judge each tool fixture case (scripted tool_calls). claim stays false."""
    adapter = get_subject_adapter("agent")
    cases = load_tool_capability_fixture_cases(
        seed_dir=seed_dir, capability_id=capability_id
    )
    results: List[Dict[str, Any]] = []
    passed = 0
    for case in cases:
        exe = adapter.execute(case)
        trace = {
            "tool_calls": exe.get("tool_calls")
            or (exe.get("harness") or {}).get("tool_calls")
            or [],
            "tool_results": exe.get("tool_results")
            or (exe.get("harness") or {}).get("tool_results")
            or [],
            "tool_backend": exe.get("tool_backend") or "mock",
            "answer": exe.get("answer") or case.get("scripted_answer") or "",
            "scripted_answer": exe.get("scripted_answer")
            or case.get("scripted_answer")
            or "",
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
    min_n = 5 if capability_id else 20
    return {
        "schema": "eval.tool_fixture_suite.v1",
        "ok": passed == len(cases) and len(cases) >= min_n,
        "n_cases": len(cases),
        "n_passed": passed,
        "claim_eligible": False,
        "v1_in_scope": True,  # v1.1 measurable (mock/fixture ≠ live/Certification)
        "results": results,
    }


def run_session_fixture_suite(
    *, seed_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Run A8 multi_turn_memory fixture groups via session runner."""
    cases = load_session_fixture_cases(seed_dir=seed_dir)
    groups = group_session_cases(cases)
    results: List[Dict[str, Any]] = []
    passed = 0
    for sg, items in sorted(groups.items()):
        rep = run_session_group(items)
        expect_fail = any(bool(c.get("expect_judge_fail")) for c in items)
        ok = (not bool(rep.get("ok"))) if expect_fail else bool(rep.get("ok"))
        if ok:
            passed += 1
        results.append(
            {
                "session_group": sg,
                "ok": ok,
                "expect_fail": expect_fail,
                "n_turns": rep.get("n_turns"),
                "errors": rep.get("errors") or [],
            }
        )
    return {
        "schema": "eval.session_fixture_suite.v1",
        "ok": passed == len(results) and len(cases) >= 5 and bool(results),
        "n_cases": len(cases),
        "n_groups": len(results),
        "n_passed_groups": passed,
        "claim_eligible": False,
        "v1_in_scope": True,  # v1.1 measurable (session runner ≠ Certification)
        "results": results,
    }
