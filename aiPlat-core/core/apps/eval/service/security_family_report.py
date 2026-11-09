"""SEC-P0a: threat-family catalog + per-family report schema (engineering).

Honesty:
- L1 must not host T05-exec / T06 / T07 / T08 / T12.
- Macro ASR across families is not_for_claim.
- Never sets accuracy_claim / security_certification.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPORT_SCHEMA = "eval.security_family_report.v1"
CATALOG_SCHEMA = "eval.security_threat_family_catalog.v1"


class SecurityFamilyReportError(ValueError):
    """Fail-closed security family catalog / report error."""


def default_security_seed_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
    )


def default_catalog_path() -> Path:
    return default_security_seed_dir() / "threat_family_catalog.v1.yaml"


def default_l3_deferred_path() -> Path:
    return default_security_seed_dir() / "l3_exec_deferred.v1.json"


def load_threat_family_catalog(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_catalog_path()
    if not p.is_file():
        raise SecurityFamilyReportError(f"catalog_missing:{p}")
    raw = p.read_text(encoding="utf-8")
    if yaml is None:
        raise SecurityFamilyReportError("pyyaml_required_for_threat_catalog")
    data = yaml.safe_load(raw)
    if not isinstance(data, Mapping):
        raise SecurityFamilyReportError("catalog_not_object")
    out = dict(data)
    if str(out.get("schema") or "") != CATALOG_SCHEMA:
        raise SecurityFamilyReportError(
            f"catalog_schema_mismatch:{out.get('schema')}"
        )
    return out


def l1_allowed_threats(catalog: Optional[Mapping[str, Any]] = None) -> List[str]:
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    return [str(x) for x in (cat.get("l1_allowed") or [])]


def l1_forbidden_threats(catalog: Optional[Mapping[str, Any]] = None) -> List[str]:
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    return [str(x) for x in (cat.get("l1_forbidden") or [])]


def family_min_n(family_id: str, catalog: Optional[Mapping[str, Any]] = None) -> Optional[int]:
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    row = fams.get(family_id) if isinstance(fams, Mapping) else None
    if not isinstance(row, Mapping):
        return None
    n = row.get("min_n_l5")
    if n is None:
        return None
    try:
        return int(n)
    except (TypeError, ValueError):
        return None


def validate_case_threat_ids(
    case: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
    require_l1_layer: bool = False,
) -> List[str]:
    """Return error codes; empty = ok."""
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    errs: List[str] = []
    tids = case.get("threat_ids")
    if not isinstance(tids, list) or not tids:
        errs.append("threat_ids_missing")
        return errs
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    forbidden = set(l1_forbidden_threats(cat))
    allowed_l1 = set(l1_allowed_threats(cat))
    layer = str(case.get("eval_layer") or "").strip().upper()
    for tid in tids:
        sid = str(tid)
        if sid not in fams:
            errs.append(f"unknown_threat_id:{sid}")
            continue
        if require_l1_layer or layer == "L1":
            if sid in forbidden:
                errs.append(f"l1_forbidden_threat:{sid}")
            elif sid not in allowed_l1:
                errs.append(f"l1_not_allowed_threat:{sid}")
    # Explicit anti-false-green: T05-exec never on L1 file
    if "T05-exec" in {str(x) for x in tids} and layer in {"", "L1"}:
        errs.append("t05_exec_requires_l3")
    return errs


def validate_l1_safety_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    rows: List[Dict[str, Any]] = []
    ok = True
    for case in cases:
        errs = validate_case_threat_ids(case, catalog=cat, require_l1_layer=True)
        cid = str(case.get("case_id") or "")
        if errs:
            ok = False
        rows.append({"case_id": cid, "threat_ids": list(case.get("threat_ids") or []), "errors": errs})
    return {
        "schema": "eval.security_l1_case_validate.v1",
        "ok": ok,
        "n_cases": len(cases),
        "rows": rows,
        "l1_allowed": l1_allowed_threats(cat),
        "l1_forbidden": l1_forbidden_threats(cat),
        "honesty": (
            "L1 validates text-layer threat_ids only; "
            "passing ≠ T05-exec / tool execution safety"
        ),
        "accuracy_claim": False,
        "security_certification": False,
    }


def empty_family_bucket(family_id: str, catalog: Mapping[str, Any]) -> Dict[str, Any]:
    fams = catalog.get("families") if isinstance(catalog.get("families"), Mapping) else {}
    meta = fams.get(family_id) if isinstance(fams, Mapping) else {}
    meta = meta if isinstance(meta, Mapping) else {}
    min_n = family_min_n(family_id, catalog)
    return {
        "threat_id": family_id,
        "name": meta.get("name"),
        "metric": meta.get("metric"),
        "n": 0,
        "successes": 0,
        "rate": None,
        "wilson_ci95": None,
        "min_n_l5": min_n,
        "status": "report_only",  # P0c will flip when n/CI gate lands
        "claim_eligible": False,
        "note": meta.get("note") or meta.get("status"),
    }


def build_security_family_report(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    catalog: Optional[Mapping[str, Any]] = None,
    subject: Optional[Mapping[str, Any]] = None,
    pack_id: str = "agent.safety.l1",
    eval_layer: str = "L1",
) -> Dict[str, Any]:
    """Aggregate per-family rates. Macro ASR marked not_for_claim.

    ``by_case`` values: {threat_ids: [...], ok: bool, status?: str}
    Missing families → n=0 report_only.
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    buckets: Dict[str, Dict[str, Any]] = {
        str(fid): empty_family_bucket(str(fid), cat) for fid in fams
    }

    total_ok = 0
    total_n = 0
    for _cid, row in (by_case or {}).items():
        if not isinstance(row, Mapping):
            continue
        tids = [str(t) for t in (row.get("threat_ids") or [])]
        if not tids:
            continue
        ok = bool(row.get("ok"))
        for tid in tids:
            if tid not in buckets:
                buckets[tid] = empty_family_bucket(tid, cat)
                buckets[tid]["note"] = "unknown_family_in_results"
            b = buckets[tid]
            b["n"] = int(b["n"]) + 1
            if ok:
                b["successes"] = int(b["successes"]) + 1
            total_n += 1
            if ok:
                total_ok += 1

    for b in buckets.values():
        apply_family_sample_gate(b)

    gate = summarize_family_gates(buckets)
    untested = sorted(fid for fid, b in buckets.items() if int(b["n"]) == 0)
    oos = [str(x) for x in (cat.get("out_of_scope") or [])]
    deferred = []
    for fid, meta in fams.items():
        if isinstance(meta, Mapping) and str(meta.get("status") or "").startswith("deferred"):
            deferred.append(str(fid))

    macro = (float(total_ok) / float(total_n)) if total_n else None
    return {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "eval_layer": eval_layer,
        "pack_id": pack_id,
        "subject": dict(subject) if subject else {},
        "families": buckets,
        "family_gates": gate,
        "macro_asr": macro,
        "macro_asr_not_for_claim": True,
        "untested_threat_families": untested,
        "deferred_threat_families": sorted(deferred),
        "out_of_scope": oos,
        "below_min_n_families": list(gate.get("below_min_n_families") or []),
        "engineering_ready_families": list(gate.get("engineering_ready_families") or []),
        "l5_declare_allowed_families": [],  # never auto; needs authorize + signoff elsewhere
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Per-family n/CI + report_only gate (SEC-P0c). Macro ASR dashboard-only. "
            "engineering_ready ≠ L5 declare ≠ certification. "
            "L1 pass ≠ T05-exec. admit ≠ isolation_covered."
        ),
    }


def apply_family_sample_gate(bucket: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate one family bucket: wilson CI + status report_only|engineering_ready|untested.

    Never sets claim_eligible / accuracy_claim true.
    """
    from core.apps.eval.service.mode_intersection_rank import wilson_score_ci

    n = int(bucket.get("n") or 0)
    successes = int(bucket.get("successes") or 0)
    min_n = bucket.get("min_n_l5")
    try:
        min_n_i = int(min_n) if min_n is not None else None
    except (TypeError, ValueError):
        min_n_i = None

    if n <= 0:
        bucket["rate"] = None
        bucket["wilson_ci95"] = None
        bucket["status"] = "untested"
        bucket["meets_min_n"] = False
        bucket["claim_eligible"] = False
        return bucket

    rate = float(successes) / float(n)
    lo, hi = wilson_score_ci(successes, n)
    bucket["rate"] = rate
    bucket["wilson_ci95"] = [lo, hi]
    meets = min_n_i is not None and n >= min_n_i
    bucket["meets_min_n"] = bool(meets)
    # Enough n → engineering_ready (still report_only for claims).
    if meets:
        bucket["status"] = "engineering_ready"
    else:
        bucket["status"] = "report_only"
    bucket["claim_eligible"] = False
    return bucket


def summarize_family_gates(buckets: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    below: List[str] = []
    ready: List[str] = []
    untested: List[str] = []
    report_only: List[str] = []
    for fid, b in buckets.items():
        st = str(b.get("status") or "")
        if st == "untested":
            untested.append(str(fid))
        elif st == "engineering_ready":
            ready.append(str(fid))
        elif st == "report_only":
            report_only.append(str(fid))
            below.append(str(fid))
        n = int(b.get("n") or 0)
        min_n = b.get("min_n_l5")
        if n > 0 and min_n is not None and n < int(min_n) and str(fid) not in below:
            below.append(str(fid))
    return {
        "schema": "eval.security_family_gates.v1",
        "below_min_n_families": sorted(set(below)),
        "engineering_ready_families": sorted(ready),
        "report_only_families": sorted(set(report_only)),
        "untested_families": sorted(untested),
        "l5_declare_allowed_families": [],
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Per-threat-family min_n gate. "
            "engineering_ready means n>=min_n_l5 only; "
            "does not unlock L5 declare or accuracy_claim."
        ),
    }


def evaluate_security_family_gates(
    report: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recompute / expose family gates from an existing family report."""
    fams = report.get("families") if isinstance(report.get("families"), Mapping) else {}
    buckets = {k: dict(v) for k, v in fams.items() if isinstance(v, Mapping)}
    for b in buckets.values():
        apply_family_sample_gate(b)
    gate = summarize_family_gates(buckets)
    gate["families"] = buckets
    gate["macro_asr_not_for_claim"] = True
    return gate


def security_sec_p0c_status(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """SEC-P0c snapshot: family report with min_n/CI gates applied."""
    report = build_security_family_report(by_case=by_case or {}, eval_layer="L1")
    return {
        "schema": "eval.security_sec_p0c_status.v1",
        "ok": True,
        "slice": "SEC-P0c",
        "family_report": report,
        "family_gates": report.get("family_gates"),
        "below_min_n_families": report.get("below_min_n_families"),
        "engineering_ready_families": report.get("engineering_ready_families"),
        "macro_asr_not_for_claim": True,
        "l5_declare_allowed_families": [],
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
    }


def load_l1_safety_cases_from_seed(
    *, seed_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    root = (
        Path(seed_dir)
        if seed_dir
        else Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
    )
    path = root / "cases" / "safety.json"
    if not path.is_file():
        raise SecurityFamilyReportError(f"safety_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SecurityFamilyReportError("safety_cases_not_array")
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def security_l1_p0a_status() -> Dict[str, Any]:
    """Facade-friendly SEC-P0a status: catalog + L1 validate + empty family report."""
    cat = load_threat_family_catalog()
    cases = load_l1_safety_cases_from_seed()
    validation = validate_l1_safety_cases(cases, catalog=cat)
    # Build report from case annotations only (no run results → untested rates)
    by_case = {
        str(c.get("case_id")): {
            "threat_ids": list(c.get("threat_ids") or []),
            "ok": True,  # annotation presence only — not a scored run
        }
        for c in cases
    }
    # For status card: show annotated coverage n, but mark as annotation_only
    report = build_security_family_report(
        by_case=by_case, catalog=cat, eval_layer="L1", pack_id="agent.safety.l1"
    )
    report["annotation_only"] = True
    report["honesty"] = (
        "SEC-P0a annotation coverage (threat_ids present). "
        "Not a scored live security run. accuracy_claim=false."
    )
    # Re-tag: annotation n is not attack success
    for b in report["families"].values():
        if int(b["n"]) > 0:
            b["status"] = "annotated_l1"
            b["rate"] = None
            b["note"] = (str(b.get("note") or "") + "; annotation_only").strip("; ")

    l3 = {}
    lp = default_l3_deferred_path()
    if lp.is_file():
        l3 = json.loads(lp.read_text(encoding="utf-8"))

    return {
        "schema": "eval.security_sec_p0a_status.v1",
        "ok": bool(validation.get("ok")),
        "slice": "SEC-P0a",
        "validation": validation,
        "family_report": report,
        "l3_exec_deferred": {
            "path": str(lp),
            "status": l3.get("status"),
            "threat_families": l3.get("threat_families"),
            "n_cases": len(l3.get("cases") or []),
        },
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
    }
