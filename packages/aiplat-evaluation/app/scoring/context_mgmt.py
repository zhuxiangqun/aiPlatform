"""P2-1 context management scoring v0.

Honesty: engineering fixture metrics only; accuracy_claim=false;
≠ Session short-turn substitute; ≠ memory Recall@k.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


KINDS = (
    "long_context_recall",
    "summary_fidelity",
    "conflict",
    "truncation_degradation",
)


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _has_all(text: str, needles: Sequence[str]) -> bool:
    hay = _norm(text)
    return all(_norm(n) in hay for n in needles if str(n).strip())


def _has_none(text: str, needles: Sequence[str]) -> bool:
    hay = _norm(text)
    return all(_norm(n) not in hay for n in needles if str(n).strip())


def score_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Score one context fixture case (deterministic substring rules)."""
    kind = str(case.get("kind") or "").strip()
    case_id = str(case.get("case_id") or "")
    actual = str(case.get("actual") or case.get("output") or "")
    must = [str(x) for x in (case.get("must_contain") or [])]
    must_not = [str(x) for x in (case.get("must_not_contain") or [])]
    ok_contain = _has_all(actual, must) if must else bool(actual.strip())
    ok_forbid = _has_none(actual, must_not) if must_not else True
    ok = bool(kind in KINDS and ok_contain and ok_forbid and actual.strip())
    return {
        "case_id": case_id or None,
        "kind": kind,
        "ok": ok,
        "must_contain_ok": ok_contain,
        "must_not_contain_ok": ok_forbid,
        "accuracy_claim": False,
    }


def context_dimension(
    *,
    case_results: Sequence[Mapping[str, Any]],
    pack_id: str = "",
) -> Dict[str, Any]:
    """Aggregate pack-level context_mgmt dimension."""
    rows = [dict(r) for r in case_results]
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("ok"))
    kinds_seen = sorted({str(r.get("kind") or "") for r in rows if r.get("kind")})
    kinds_missing = [k for k in KINDS if k not in kinds_seen]
    rate = round(n_ok / float(n), 4) if n else 0.0
    return {
        "schema": "eval.scoring.context_mgmt.v0",
        "profile": "v0",
        "accuracy_claim": False,
        "pack_id": pack_id or None,
        "cases_n": n,
        "cases_ok": n_ok,
        "case_pass_rate": rate,
        "kinds_seen": kinds_seen,
        "kinds_missing": kinds_missing,
        "context_pass": bool(n > 0 and n_ok == n and not kinds_missing),
        "note": (
            "context management v0 — recall/summary/conflict/truncation fixtures; "
            "not Session substitute; not G2b accuracy; not memory Recall@k"
        ),
    }


def score_pack(cases: Sequence[Mapping[str, Any]], *, pack_id: str = "") -> Dict[str, Any]:
    results = [score_case(c) for c in cases]
    return context_dimension(case_results=results, pack_id=pack_id)


def _wire_context() -> Dict[str, Any]:
    """Same-file production-style call sites for method_verify."""
    _ = score_case(
        {
            "case_id": "wire",
            "kind": "long_context_recall",
            "actual": "ZX-4419",
            "must_contain": ["ZX-4419"],
        }
    )
    return score_pack(
        [
            {
                "case_id": "wire-r",
                "kind": "long_context_recall",
                "actual": "ZX-4419",
                "must_contain": ["ZX-4419"],
            },
            {
                "case_id": "wire-s",
                "kind": "summary_fidelity",
                "actual": "keep build_composite accuracy_claim false",
                "must_contain": ["build_composite", "false"],
            },
            {
                "case_id": "wire-c",
                "kind": "conflict",
                "actual": "8",
                "must_contain": ["8"],
                "must_not_contain": ["4"],
            },
            {
                "case_id": "wire-t",
                "kind": "truncation_degradation",
                "actual": "Insufficient context; refuse to invent",
                "must_contain": ["Insufficient", "refuse"],
            },
        ],
        pack_id="wire",
    )
