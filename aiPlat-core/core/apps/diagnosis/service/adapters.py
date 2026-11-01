"""Read-only evidence adapters (aiPlat / Pi / FDE / Evaluation) + fixture pack."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_FIXTURE_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[5] / "packages" / "aiplat-diagnosis" / "fixtures",
    Path(__file__).resolve().parents[4] / "packages" / "aiplat-diagnosis" / "fixtures",
)


def fixture_root() -> Path:
    for p in _FIXTURE_ROOT_CANDIDATES:
        if p.is_dir():
            return p
    # workspace root relative to cwd
    cwd = Path.cwd() / "packages" / "aiplat-diagnosis" / "fixtures"
    return cwd


def resolve_fixture_id(subject_ref: str) -> Optional[str]:
    s = (subject_ref or "").strip()
    if not s:
        return None
    for prefix in ("fixture:", "dx.fixture:", "case:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.startswith("dx."):
        return s
    # allow bare seed id without prefix
    root = fixture_root()
    if (root / s).is_dir():
        return s
    return None


def load_fixture(case_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    d = fixture_root() / case_id
    if not d.is_dir():
        raise FileNotFoundError(f"fixture_not_found:{case_id}")
    evidence = json.loads((d / "evidence.json").read_text(encoding="utf-8"))
    expected = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    return evidence, expected


def collect_from_fixture(case_id: str) -> Dict[str, Any]:
    evidence_doc, expected = load_fixture(case_id)
    refs = list(evidence_doc.get("evidence") or [])
    return {
        "source": "fixture",
        "fixture_id": case_id,
        "evidence": refs,
        "payload": evidence_doc.get("payload") or {},
        "expected": expected,
        "adapters": {
            "aiplat": "read_only",
            "pi": "read_only",
            "fde": "read_only",
            "evaluation": "read_only",
        },
    }


def collect_live_stubs(
    *,
    scenario: str,
    subject_ref: str,
    baseline_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only stub refs when no fixture pack match — never invents root cause."""
    captured = "1970-01-01T00:00:00+00:00"
    refs: List[Dict[str, Any]] = [
        {
            "id": "e-aiplat-subject",
            "source": "aiplat",
            "kind": "run",
            "ref": f"aiplat://subject/{subject_ref}",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "aiplat", "note": "live collect stub; no source write"},
        },
        {
            "id": "e-pi-health",
            "source": "pi",
            "kind": "healthz",
            "ref": "pi://healthz",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "pi"},
        },
        {
            "id": "e-fde",
            "source": "fde",
            "kind": "fde_evidence",
            "ref": f"fde://subject/{subject_ref}",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "fde"},
        },
        {
            "id": "e-eval",
            "source": "evaluation",
            "kind": "eval_report" if scenario == "version_regression" else "other",
            "ref": f"evaluation://subject/{subject_ref}",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {
                "adapter": "evaluation",
                "baseline_ref": baseline_ref,
            },
        },
    ]
    return {
        "source": "live_stub",
        "fixture_id": None,
        "evidence": refs,
        "payload": {"note": "adapters returned refs only; insufficient for confirmed root cause"},
        "expected": {
            "gold_root_cause": "insufficient_evidence",
            "expect_unknown": True,
            "expect_stale": False,
        },
        "adapters": {
            "aiplat": "read_only",
            "pi": "read_only",
            "fde": "read_only",
            "evaluation": "read_only",
        },
    }


def collect_evidence(
    *,
    scenario: str,
    subject_ref: str,
    baseline_ref: Optional[str] = None,
) -> Dict[str, Any]:
    fid = resolve_fixture_id(subject_ref)
    if fid:
        return collect_from_fixture(fid)
    return collect_live_stubs(
        scenario=scenario, subject_ref=subject_ref, baseline_ref=baseline_ref
    )
