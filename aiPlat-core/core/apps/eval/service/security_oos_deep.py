"""OOS deep engineering packs + research refuse inventory.

Priority order (scheme follow-on):
  OOS-07 → OOS-04 → OOS-06 → OOS-05/T11 fixtures
  OOS-01/02/03 → research refuse-to-test (never text ASR covered)
  OOS-08/09 → out of security cert track

Honesty:
  - Fixture/catalog probes ≠ live attack execution
  - claimable always false; security_certification always false
  - T13 shallow ≠ OOS-06; T11 fixtures ≠ graduated covered
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from core.apps.eval.service.security_p5_extensions import evaluate_t11_deferred_gate
from core.apps.eval.service.security_s1_disclosure import OOS_LABELS

PACKS_SCHEMA = "eval.security_oos_deep_packs.v1"
STATUS_SCHEMA = "eval.security_oos_deep_status.v1"
EVAL_SCHEMA = "eval.security_oos_pack_eval.v1"

ENGINEERING_ORDER = ("OOS-07", "OOS-04", "OOS-06", "OOS-05")


class SecurityOosDeepError(ValueError):
    """Fail-closed OOS deep pack error."""


def default_oos_deep_packs_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
        / "oos_deep_packs.v1.yaml"
    )


def load_oos_deep_packs(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_oos_deep_packs_path()
    if not p.is_file():
        raise SecurityOosDeepError(f"oos_deep_packs_missing:{p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SecurityOosDeepError("oos_deep_packs_not_object")
    if str(raw.get("schema") or "") != PACKS_SCHEMA:
        raise SecurityOosDeepError(f"oos_deep_packs_schema_mismatch:{raw.get('schema')}")
    out = dict(raw)
    out["path"] = str(p)
    out["accuracy_claim"] = False
    out["security_certification"] = False
    out["claim_eligible"] = False
    return out


def list_engineering_oos_ids(packs: Optional[Mapping[str, Any]] = None) -> List[str]:
    g = dict(packs) if packs is not None else load_oos_deep_packs()
    eng = g.get("engineering_packs") if isinstance(g.get("engineering_packs"), Mapping) else {}
    ordered = [oid for oid in ENGINEERING_ORDER if oid in eng]
    for oid in eng:
        if oid not in ordered:
            ordered.append(str(oid))
    return ordered


def evaluate_oos_engineering_pack(
    oos_id: str,
    *,
    packs: Optional[Mapping[str, Any]] = None,
    probe_results: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate one engineering OOS pack. Missing results → incomplete (not covered)."""
    g = dict(packs) if packs is not None else load_oos_deep_packs()
    eng = g.get("engineering_packs") if isinstance(g.get("engineering_packs"), Mapping) else {}
    oid = str(oos_id)
    if oid not in eng or not isinstance(eng.get(oid), Mapping):
        raise SecurityOosDeepError(f"unknown_engineering_oos:{oid}")
    pack = dict(eng[oid])
    probes = [dict(x) for x in (pack.get("probes") or []) if isinstance(x, Mapping)]
    results = dict(probe_results or {})
    rows: List[Dict[str, Any]] = []
    complete = True
    pass_n = 0
    for p in probes:
        pid = str(p.get("id") or "")
        got = results.get(pid) if isinstance(results.get(pid), Mapping) else None
        if got is None:
            complete = False
            rows.append(
                {
                    "probe_id": pid,
                    "expect": p.get("expect"),
                    "status": "not_run",
                    "ok": None,
                }
            )
            continue
        ok = got.get("ok")
        if ok is True:
            pass_n += 1
        elif ok is not False:
            complete = False
        rows.append(
            {
                "probe_id": pid,
                "expect": p.get("expect"),
                "status": str(got.get("status") or ("pass" if ok is True else "fail")),
                "ok": ok,
                "detail": got.get("detail"),
            }
        )

    min_n = int(pack.get("min_n") or len(probes) or 0)
    n_run = sum(1 for r in rows if r.get("status") != "not_run")
    meets_min = n_run >= min_n and complete and pass_n == len(probes) and len(probes) > 0
    return {
        "schema": EVAL_SCHEMA,
        "ok": True,
        "oos_id": oid,
        "title": pack.get("title"),
        "mode": pack.get("mode") or "engineering_fixture",
        "related_threats": list(pack.get("related_threats") or []),
        "min_n": min_n,
        "n_probes": len(probes),
        "n_run": n_run,
        "n_pass": pass_n,
        "complete": complete,
        "fixture_ready": len(probes) >= min_n,
        "engineering_pass": bool(meets_min),
        "covered": False,  # hard lock — fixture pass ≠ OOS covered certification
        "claimable": False,
        "results": rows,
        "honesty": str(
            pack.get("honesty")
            or "Engineering fixture evaluation only; never OOS covered / certification."
        ),
        "accuracy_claim": False,
        "security_certification": False,
    }


def build_research_refuse_inventory(
    *, packs: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """OOS-01/02/03 refuse-to-test inventory (never scored as covered)."""
    g = dict(packs) if packs is not None else load_oos_deep_packs()
    research = g.get("research_refuse") if isinstance(g.get("research_refuse"), Mapping) else {}
    cards = []
    for oid, row in research.items():
        if not isinstance(row, Mapping):
            continue
        cards.append(
            {
                "oos_id": str(oid),
                "title": row.get("title") or OOS_LABELS.get(str(oid), str(oid)),
                "mode": row.get("mode") or "refuse_to_test_in_agent_exam",
                "reason": row.get("reason"),
                "claimable": False,
                "covered": False,
                "score_as_text_asr": False,
            }
        )
    excluded = g.get("track_excluded") if isinstance(g.get("track_excluded"), Mapping) else {}
    track_out = []
    for oid, row in excluded.items():
        if not isinstance(row, Mapping):
            continue
        track_out.append(
            {
                "oos_id": str(oid),
                "title": row.get("title") or OOS_LABELS.get(str(oid), str(oid)),
                "mode": row.get("mode") or "out_of_security_cert_track",
                "reason": row.get("reason"),
                "claimable": False,
            }
        )
    return {
        "schema": "eval.security_oos_research_refuse.v1",
        "ok": True,
        "research_refuse": cards,
        "track_excluded": track_out,
        "any_claimable": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Research refuse cards disclose non-testability in Agent exam. "
            "Never treat as covered via text ASR."
        ),
    }


def evaluate_oos05_t11_fixture_gate(
    *,
    packs: Optional[Mapping[str, Any]] = None,
    t11_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """OOS-05 fixtures feed T11 min_fixture_pack evidence; still not auto-graduate."""
    g = dict(packs) if packs is not None else load_oos_deep_packs()
    eng = g.get("engineering_packs") if isinstance(g.get("engineering_packs"), Mapping) else {}
    pack = dict(eng.get("OOS-05") or {})
    probes = [dict(x) for x in (pack.get("probes") or []) if isinstance(x, Mapping)]
    fixture_n = len(probes)
    min_n = int(pack.get("min_n") or 5)
    evidence = dict(t11_evidence or {})
    # Auto-fill fixture_count for T11 min_fixture_pack check when absent.
    if "fixture_count" not in evidence:
        evidence["fixture_count"] = fixture_n
    gate = evaluate_t11_deferred_gate(evidence=evidence)
    return {
        "ok": True,
        "oos_id": "OOS-05",
        "fixture_n": fixture_n,
        "min_n": min_n,
        "fixture_pack_ready": fixture_n >= min_n,
        "t11_gate": gate,
        "graduated": False,
        "covered": False,
        "claimable": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "OOS-05 fixture pack can satisfy T11 min_fixture_pack condition only. "
            "Graduate still needs runtime+session_trace+human authorize."
        ),
    }


def security_oos_deep_status(
    *,
    probe_results_by_oos: Optional[Mapping[str, Mapping[str, Mapping[str, Any]]]] = None,
    t11_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Facade-friendly OOS deep status across engineering + research cards."""
    packs = load_oos_deep_packs()
    by = dict(probe_results_by_oos or {})
    engineering = []
    for oid in list_engineering_oos_ids(packs):
        engineering.append(
            evaluate_oos_engineering_pack(
                oid,
                packs=packs,
                probe_results=by.get(oid) if isinstance(by.get(oid), Mapping) else None,
            )
        )
    research = build_research_refuse_inventory(packs=packs)
    t11 = evaluate_oos05_t11_fixture_gate(packs=packs, t11_evidence=t11_evidence)
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "OOS-DEEP",
        "order": list(ENGINEERING_ORDER),
        "engineering": engineering,
        "oos05_t11": t11,
        "research_refuse": research,
        "any_covered": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "OOS deep engineering fixtures + research refuse inventory. "
            "No OOS id becomes covered/certified in this slice."
        ),
    }
