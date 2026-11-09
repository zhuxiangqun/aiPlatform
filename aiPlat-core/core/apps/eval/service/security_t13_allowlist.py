"""SEC-P1c: T13 supply-chain allowlist pack + process_split boundary.

T13 (plugin/MCP/skill poison — shallow):
  workspace_execute + allowlist + signature + load_trace
  process_split_authorized is NEVER a prerequisite.

T13-escape (production skill process escape — L4):
  requires process_split_authorized; otherwise deferred/blocked.
  Completing T13 does NOT authorize T13-escape or flip process_split.

Coverage (non-isolation): unknown | exercised_fixture |
  exercised_workspace | claim_candidate (still accuracy_claim=false).

Never sets accuracy_claim / security_certification / claim_eligible /
process_split_authorized.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

PACK_SCHEMA = "eval.security_t13_allowlist_probes.v1"
RUN_SCHEMA = "eval.security_t13_allowlist_run.v1"
STATUS_SCHEMA = "eval.security_sec_p1c_status.v1"

COV_UNKNOWN = "unknown"
COV_FIXTURE = "exercised_fixture"
COV_WORKSPACE = "exercised_workspace"
COV_CLAIM_CANDIDATE = "claim_candidate"

_VALID_COV = frozenset(
    {COV_UNKNOWN, COV_FIXTURE, COV_WORKSPACE, COV_CLAIM_CANDIDATE}
)


class SecurityT13AllowlistError(ValueError):
    """Fail-closed T13 allowlist error."""


def default_security_seed_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
    )


def default_t13_probes_path() -> Path:
    return default_security_seed_dir() / "t13_allowlist_probes.v1.json"


def load_t13_allowlist_probes(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_t13_probes_path()
    if not p.is_file():
        raise SecurityT13AllowlistError(f"t13_probes_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SecurityT13AllowlistError("t13_probes_not_object")
    if str(raw.get("schema") or "") != PACK_SCHEMA:
        raise SecurityT13AllowlistError(
            f"t13_probes_schema_mismatch:{raw.get('schema')}"
        )
    if raw.get("process_split_required") is not False:
        raise SecurityT13AllowlistError("t13_must_set_process_split_required_false")
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise SecurityT13AllowlistError("t13_cases_not_array")
    min_n = int(raw.get("min_cases") or 10)
    t13_cases = [
        c
        for c in cases
        if isinstance(c, Mapping) and "T13" in [str(x) for x in (c.get("threat_ids") or [])]
    ]
    if len(t13_cases) < min_n:
        raise SecurityT13AllowlistError(
            f"t13_cases_below_min:{len(t13_cases)}<{min_n}"
        )
    kinds = {str(c.get("kind") or "") for c in t13_cases}
    if "negative_control" not in kinds:
        raise SecurityT13AllowlistError("t13_negative_control_required")
    if not any(bool(c.get("assert_process_split_not_required")) for c in t13_cases):
        raise SecurityT13AllowlistError("t13_boundary_assert_required")
    return dict(raw)


def _decide_allowlist(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Deterministic fixture oracle for allowlist/signature/load_trace."""
    tids = [str(x) for x in (case.get("threat_ids") or [])]
    art = case.get("artifact") if isinstance(case.get("artifact"), Mapping) else {}
    expect = str(case.get("expect") or "").strip().lower()

    # T13-escape: blocked without process_split_authorized (never flip it here)
    if "T13-escape" in tids or bool(case.get("require_process_split_authorized")):
        return {
            "decision": "deferred",
            "ok": expect == "deferred",
            "reason": "t13_escape_requires_process_split_authorized",
            "process_split_authorized": False,
            "load_trace": None,
        }

    signed = bool(art.get("signed"))
    allowlisted = bool(art.get("allowlisted"))
    sig_valid = art.get("signature_valid")
    if sig_valid is None:
        sig_valid = signed
    else:
        sig_valid = bool(sig_valid)
    ws_match = art.get("workspace_match")
    if ws_match is None:
        ws_match = True
    else:
        ws_match = bool(ws_match)
    missing_trace = bool(case.get("simulate_missing_trace"))
    require_trace = bool(case.get("require_load_trace", True))

    reasons: List[str] = []
    decision = "allow"
    if not signed:
        decision = "deny"
        reasons.append("unsigned")
    elif not sig_valid:
        decision = "deny"
        reasons.append("invalid_signature")
    elif not allowlisted:
        decision = "deny"
        reasons.append("not_allowlisted")
    elif not ws_match:
        decision = "deny"
        reasons.append("cross_workspace")
    elif require_trace and missing_trace:
        decision = "deny"
        reasons.append("missing_load_trace")

    load_trace = None
    if not missing_trace:
        load_trace = {
            "artifact_id": art.get("id"),
            "type": art.get("type"),
            "signed": signed,
            "signature_valid": sig_valid,
            "allowlisted": allowlisted,
            "workspace_match": ws_match,
            "decision": decision,
        }

    if bool(case.get("assert_process_split_not_required")):
        reasons.append("process_split_not_required_asserted")

    ok = decision == expect
    return {
        "decision": decision,
        "ok": ok,
        "expect": expect,
        "reasons": reasons,
        "process_split_authorized": False,
        "load_trace": load_trace,
    }


def run_t13_allowlist_probes(
    *,
    catalog: Optional[Mapping[str, Any]] = None,
    coverage_mode: str = COV_FIXTURE,
    process_split_authorized: bool = False,
) -> Dict[str, Any]:
    """Execute fixture allowlist probes. Never requires process_split for T13.

    ``process_split_authorized`` input is ignored for T13 cases (forced false).
    T13-escape cases remain deferred unless authorized — and this module never
    sets authorization true.
    """
    cat = dict(catalog) if catalog is not None else load_t13_allowlist_probes()
    cov = str(coverage_mode or COV_FIXTURE).strip()
    if cov not in _VALID_COV:
        raise SecurityT13AllowlistError(f"invalid_coverage_mode:{coverage_mode}")
    # Hard lock: this evaluator never grants process_split
    _ = bool(process_split_authorized)  # accepted but not used to unlock T13
    psa = False

    results: List[Dict[str, Any]] = []
    for case in cat.get("cases") or []:
        if not isinstance(case, Mapping):
            continue
        verdict = _decide_allowlist(case)
        # Even if caller claimed process_split_authorized, T13 path stays false;
        # T13-escape would need a different module / SEC-P5 path.
        if "T13-escape" in [str(x) for x in (case.get("threat_ids") or [])]:
            if process_split_authorized:
                # Still deferred here — escape live probes are out of SEC-P1c scope
                verdict = {
                    **verdict,
                    "decision": "deferred",
                    "ok": True,
                    "reason": "t13_escape_live_deferred_sec_p5",
                    "process_split_authorized": False,
                }
        row = {
            "case_id": case.get("case_id"),
            "threat_ids": list(case.get("threat_ids") or []),
            "kind": case.get("kind"),
            **verdict,
        }
        results.append(row)

    t13_rows = [r for r in results if "T13" in [str(x) for x in (r.get("threat_ids") or [])]]
    escape_rows = [
        r for r in results if "T13-escape" in [str(x) for x in (r.get("threat_ids") or [])]
    ]
    t13_ok = all(bool(r.get("ok")) for r in t13_rows) if t13_rows else False
    n_pass = sum(1 for r in t13_rows if r.get("ok"))
    n_fail = len(t13_rows) - n_pass

    # claim_candidate only if fixture/workspace exercised AND all T13 pass —
    # still never opens accuracy_claim
    if t13_ok and cov in {COV_FIXTURE, COV_WORKSPACE, COV_CLAIM_CANDIDATE}:
        coverage = cov if cov != COV_UNKNOWN else COV_FIXTURE
        if cov == COV_CLAIM_CANDIDATE:
            coverage = COV_CLAIM_CANDIDATE
    elif t13_rows:
        coverage = cov if cov in {COV_FIXTURE, COV_WORKSPACE} else COV_FIXTURE
    else:
        coverage = COV_UNKNOWN

    return {
        "schema": RUN_SCHEMA,
        "ok": True,
        "threat_id": "T13",
        "coverage": coverage,
        "n_t13": len(t13_rows),
        "n_t13_pass": n_pass,
        "n_t13_fail": n_fail,
        "t13_all_pass": t13_ok,
        "n_t13_escape": len(escape_rows),
        "results": results,
        "process_split_required": False,
        "process_split_authorized": psa,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "T13 allowlist fixture run. process_split not required. "
            "claim_candidate ≠ accuracy_claim. T13-escape remains deferred."
        ),
    }


def assert_t13_process_split_boundary(
    *,
    run: Optional[Mapping[str, Any]] = None,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Verify T13 pack/run never treats process_split as supply-chain前置."""
    cat = dict(catalog) if catalog is not None else load_t13_allowlist_probes()
    errors: List[str] = []
    if cat.get("process_split_required") is not False:
        errors.append("catalog_process_split_required_not_false")
    if run is not None:
        if run.get("process_split_required") is not False:
            errors.append("run_process_split_required_not_false")
        if run.get("process_split_authorized") is True:
            errors.append("run_must_not_authorize_process_split")
    # Escape cases must declare require_process_split_authorized
    for c in cat.get("cases") or []:
        if not isinstance(c, Mapping):
            continue
        tids = [str(x) for x in (c.get("threat_ids") or [])]
        if "T13" in tids and bool(c.get("require_process_split_authorized")):
            errors.append(f"t13_case_must_not_require_process_split:{c.get('case_id')}")
        if "T13-escape" in tids and not bool(c.get("require_process_split_authorized")):
            errors.append(
                f"t13_escape_must_require_process_split:{c.get('case_id')}"
            )
    return {
        "schema": "eval.security_t13_process_split_boundary.v1",
        "ok": not errors,
        "errors": errors,
        "process_split_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "C17: T13 supply-chain tests must not use process_split as前置; "
            "process_split_authorized only for T13-escape"
        ),
    }


def evaluate_t13_coverage(
    run: Mapping[str, Any],
    *,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Map run → coverage status. claim_candidate still claim-closed."""
    cov = str(run.get("coverage") or COV_UNKNOWN)
    if not bool(run.get("t13_all_pass")):
        cov = COV_FIXTURE if cov != COV_UNKNOWN else COV_UNKNOWN
        if run.get("n_t13", 0):
            cov = COV_FIXTURE
    # Promote to claim_candidate only with human review + all pass — still no claim
    if (
        bool(run.get("t13_all_pass"))
        and human_review
        and str(human_reviewer or "").strip()
        and cov in {COV_FIXTURE, COV_WORKSPACE, COV_CLAIM_CANDIDATE}
    ):
        cov = COV_CLAIM_CANDIDATE
    return {
        "schema": "eval.security_t13_coverage.v1",
        "coverage": cov,
        "t13_all_pass": bool(run.get("t13_all_pass")),
        "human_review": bool(human_review and str(human_reviewer or "").strip()),
        "human_reviewer": str(human_reviewer or "") if human_review else "",
        "process_split_authorized": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "l5_declare_allowed": False,
        "honesty": (
            "claim_candidate means engineering bar + human review only; "
            "accuracy_claim stays false; ≠ T13-escape / process_split"
        ),
    }


def security_sec_p1c_status(
    *,
    coverage_mode: str = COV_FIXTURE,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Facade-friendly SEC-P1c status card."""
    catalog = load_t13_allowlist_probes()
    run = run_t13_allowlist_probes(catalog=catalog, coverage_mode=coverage_mode)
    boundary = assert_t13_process_split_boundary(run=run, catalog=catalog)
    coverage = evaluate_t13_coverage(
        run, human_review=human_review, human_reviewer=human_reviewer
    )
    return {
        "schema": STATUS_SCHEMA,
        "ok": bool(boundary.get("ok")) and bool(run.get("ok")),
        "slice": "SEC-P1c",
        "catalog": {
            "version": catalog.get("version"),
            "n_cases": len(catalog.get("cases") or []),
            "min_cases": catalog.get("min_cases"),
            "process_split_required": catalog.get("process_split_required"),
        },
        "run": run,
        "boundary": boundary,
        "coverage": coverage,
        "process_split_authorized": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "SEC-P1c T13 allowlist pack + process_split boundary. "
            "T13 ≠ T13-escape. accuracy_claim=false."
        ),
    }
