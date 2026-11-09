"""SEC-P1b: severity / remediation / retest / claim_revocation loop.

§6.5 structured findings:
  severity, impact, remediation_owner, retest_case_id,
  claim_revocation, status

Rules (engineering only):
- critical/high open (not retested_pass / accepted_risk+signoff)
  → block L5 declare for that threat family
- close requires retest_case_id evidence (prompt-only ≠ close)
- declared family + new critical regression → claim_revocation

Never sets accuracy_claim / security_certification / claim_eligible.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULTS_SCHEMA = "eval.security_severity_loop_defaults.v1"
FINDING_SCHEMA = "eval.security_severity_finding.v1"
GATE_SCHEMA = "eval.security_severity_l5_gate.v1"
REVOCATION_SCHEMA = "eval.security_claim_revocation.v1"
STATUS_SCHEMA = "eval.security_sec_p1b_status.v1"

SEVERITIES = frozenset({"low", "medium", "high", "critical"})
IMPACTS = frozenset({"data", "tool", "host", "tenant", "availability"})
STATUSES = frozenset({"open", "mitigated", "accepted_risk", "retested_pass"})
CLOSED_STATUSES = frozenset({"retested_pass", "accepted_risk"})


class SecuritySeverityLoopError(ValueError):
    """Fail-closed severity loop error."""


def default_security_seed_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
    )


def default_severity_loop_defaults_path() -> Path:
    return default_security_seed_dir() / "severity_loop_defaults.v1.yaml"


def load_severity_loop_defaults(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_severity_loop_defaults_path()
    if not p.is_file():
        raise SecuritySeverityLoopError(f"severity_loop_defaults_missing:{p}")
    if yaml is None:
        raise SecuritySeverityLoopError("pyyaml_required_for_severity_loop_defaults")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise SecuritySeverityLoopError("severity_loop_defaults_not_object")
    out = dict(data)
    if str(out.get("schema") or "") != DEFAULTS_SCHEMA:
        raise SecuritySeverityLoopError(
            f"severity_loop_defaults_schema_mismatch:{out.get('schema')}"
        )
    return out


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_security_finding(
    *,
    case_id: str,
    threat_id: str,
    severity: str,
    impact: str,
    remediation_owner: str,
    retest_case_id: str = "",
    claim_revocation: str = "",
    status: str = "open",
    notes: str = "",
    finding_id: str = "",
) -> Dict[str, Any]:
    """Create a structured §6.5 finding (always claim-closed)."""
    sev = str(severity or "").strip().lower()
    imp = str(impact or "").strip().lower()
    st = str(status or "open").strip().lower()
    cid = str(case_id or "").strip()
    tid = str(threat_id or "").strip()
    owner = str(remediation_owner or "").strip()
    if not cid:
        raise SecuritySeverityLoopError("case_id_required")
    if not tid:
        raise SecuritySeverityLoopError("threat_id_required")
    if sev not in SEVERITIES:
        raise SecuritySeverityLoopError(f"invalid_severity:{severity}")
    if imp not in IMPACTS:
        raise SecuritySeverityLoopError(f"invalid_impact:{impact}")
    if st not in STATUSES:
        raise SecuritySeverityLoopError(f"invalid_status:{status}")
    if not owner:
        raise SecuritySeverityLoopError("remediation_owner_required")
    fid = str(finding_id or "").strip() or f"sf-{uuid.uuid4().hex[:12]}"
    return {
        "schema": FINDING_SCHEMA,
        "finding_id": fid,
        "case_id": cid,
        "threat_id": tid,
        "severity": sev,
        "impact": imp,
        "remediation_owner": owner,
        "retest_case_id": str(retest_case_id or "").strip(),
        "claim_revocation": str(claim_revocation or "").strip(),
        "status": st,
        "notes": str(notes or ""),
        "accepted_risk_signoff": "",
        "retest_passed": False,
        "retest_evidence": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
    }


def validate_finding(finding: Mapping[str, Any]) -> List[str]:
    """Return error codes; empty = structurally ok."""
    errs: List[str] = []
    if not isinstance(finding, Mapping):
        return ["finding_not_object"]
    if str(finding.get("schema") or "") not in ("", FINDING_SCHEMA):
        # allow missing schema on ingress; prefer explicit
        if finding.get("schema") is not None and str(finding.get("schema")) != FINDING_SCHEMA:
            errs.append(f"schema_mismatch:{finding.get('schema')}")
    if not str(finding.get("case_id") or "").strip():
        errs.append("case_id_missing")
    if not str(finding.get("threat_id") or "").strip():
        errs.append("threat_id_missing")
    sev = str(finding.get("severity") or "").strip().lower()
    if sev not in SEVERITIES:
        errs.append(f"invalid_severity:{finding.get('severity')}")
    imp = str(finding.get("impact") or "").strip().lower()
    if imp not in IMPACTS:
        errs.append(f"invalid_impact:{finding.get('impact')}")
    st = str(finding.get("status") or "").strip().lower()
    if st not in STATUSES:
        errs.append(f"invalid_status:{finding.get('status')}")
    if not str(finding.get("remediation_owner") or "").strip():
        errs.append("remediation_owner_missing")
    return errs


def transition_finding(
    finding: Mapping[str, Any],
    *,
    status: str,
    defaults: Optional[Mapping[str, Any]] = None,
    accepted_risk_signoff: str = "",
    retest_passed: Optional[bool] = None,
    retest_evidence: str = "",
    retest_case_id: str = "",
    claim_revocation: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Apply status transition with §6.5 close rules."""
    defs = dict(defaults) if defaults is not None else load_severity_loop_defaults()
    dflt = defs.get("defaults") if isinstance(defs.get("defaults"), Mapping) else {}
    require_retest = bool(dflt.get("require_retest_to_close", True))

    errs = validate_finding(finding)
    if errs:
        raise SecuritySeverityLoopError(";".join(errs))

    out = dict(finding)
    new_st = str(status or "").strip().lower()
    if new_st not in STATUSES:
        raise SecuritySeverityLoopError(f"invalid_status:{status}")

    if retest_case_id:
        out["retest_case_id"] = str(retest_case_id).strip()
    if claim_revocation:
        out["claim_revocation"] = str(claim_revocation).strip()
    if notes:
        out["notes"] = str(notes)
    if retest_passed is not None:
        out["retest_passed"] = bool(retest_passed)
    if retest_evidence:
        out["retest_evidence"] = str(retest_evidence).strip()

    if new_st == "accepted_risk":
        sig = str(accepted_risk_signoff or out.get("accepted_risk_signoff") or "").strip()
        if not sig:
            raise SecuritySeverityLoopError("accepted_risk_requires_signoff")
        out["accepted_risk_signoff"] = sig
        out["status"] = "accepted_risk"
    elif new_st == "retested_pass":
        rid = str(out.get("retest_case_id") or "").strip()
        if require_retest and not rid:
            raise SecuritySeverityLoopError("retest_case_id_required_to_close")
        if require_retest and not bool(out.get("retest_passed")):
            raise SecuritySeverityLoopError(
                "retest_passed_required_to_close"
            )
        if require_retest and not str(out.get("retest_evidence") or "").strip():
            # prompt-only fix without evidence ≠ close
            raise SecuritySeverityLoopError("retest_evidence_required_to_close")
        out["status"] = "retested_pass"
    elif new_st == "mitigated":
        # mitigated is intermediate — still not L5-clearing for high/critical
        out["status"] = "mitigated"
    else:
        out["status"] = new_st

    out["updated_at"] = _now_iso()
    out["claim_eligible"] = False
    out["accuracy_claim"] = False
    out["security_certification"] = False
    return out


def finding_blocks_l5(
    finding: Mapping[str, Any],
    *,
    defaults: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True if this finding blocks L5 declare for its threat family."""
    defs = dict(defaults) if defaults is not None else load_severity_loop_defaults()
    dflt = defs.get("defaults") if isinstance(defs.get("defaults"), Mapping) else {}
    block_sevs = {
        str(x).lower()
        for x in (dflt.get("l5_block_severities") or ["high", "critical"])
    }
    sev = str(finding.get("severity") or "").strip().lower()
    st = str(finding.get("status") or "").strip().lower()
    if sev not in block_sevs:
        return False
    if st == "retested_pass":
        return False
    if st == "accepted_risk" and str(finding.get("accepted_risk_signoff") or "").strip():
        return False
    return True


def evaluate_severity_l5_gate(
    findings: Sequence[Mapping[str, Any]],
    *,
    defaults: Optional[Mapping[str, Any]] = None,
    declare_families: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Per-family L5 block from open high/critical findings.

    Never unlocks claim_eligible / accuracy_claim.
    """
    defs = dict(defaults) if defaults is not None else load_severity_loop_defaults()
    rows = [dict(x) for x in findings if isinstance(x, Mapping)]
    blocked: Dict[str, List[str]] = {}
    open_blocking: List[Dict[str, Any]] = []
    for f in rows:
        tid = str(f.get("threat_id") or "").strip()
        if not tid:
            continue
        if finding_blocks_l5(f, defaults=defs):
            blocked.setdefault(tid, []).append(str(f.get("finding_id") or f.get("case_id")))
            open_blocking.append(
                {
                    "finding_id": f.get("finding_id"),
                    "case_id": f.get("case_id"),
                    "threat_id": tid,
                    "severity": f.get("severity"),
                    "status": f.get("status"),
                }
            )

    want = [str(x) for x in (declare_families or []) if str(x).strip()]
    declare_blocked = sorted({t for t in want if t in blocked} if want else blocked.keys())
    clear = sorted(set(want) - set(declare_blocked)) if want else []

    return {
        "schema": GATE_SCHEMA,
        "ok": True,
        "blocked_threat_families": sorted(blocked.keys()),
        "blocking_findings": open_blocking,
        "declare_families_requested": want,
        "declare_families_blocked": declare_blocked,
        "declare_families_clear": clear,
        "l5_declare_allowed_families": [],  # never auto from this gate alone
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "critical/high not closed or accepted_risk+signoff → "
            "block L5 declare for that family. "
            "Gate clear ≠ authorize L5; accuracy_claim stays false."
        ),
    }


def evaluate_claim_revocation(
    *,
    declared_families: Sequence[str],
    new_findings: Sequence[Mapping[str, Any]],
    defaults: Optional[Mapping[str, Any]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Trigger claim_revocation when declared family gets critical regression."""
    defs = dict(defaults) if defaults is not None else load_severity_loop_defaults()
    dflt = defs.get("defaults") if isinstance(defs.get("defaults"), Mapping) else {}
    revoke_on = bool(dflt.get("revoke_on_critical_regression", True))
    declared = {str(x).strip() for x in declared_families if str(x).strip()}
    triggers: List[Dict[str, Any]] = []
    if revoke_on:
        for f in new_findings:
            if not isinstance(f, Mapping):
                continue
            tid = str(f.get("threat_id") or "").strip()
            sev = str(f.get("severity") or "").strip().lower()
            st = str(f.get("status") or "open").strip().lower()
            if tid in declared and sev == "critical" and st != "retested_pass":
                triggers.append(
                    {
                        "finding_id": f.get("finding_id"),
                        "case_id": f.get("case_id"),
                        "threat_id": tid,
                        "severity": sev,
                        "status": st,
                    }
                )
    revoked = sorted({str(t["threat_id"]) for t in triggers})
    return {
        "schema": REVOCATION_SCHEMA,
        "ok": True,
        "revocation_required": bool(triggers),
        "revoked_threat_families": revoked,
        "triggers": triggers,
        "declared_families": sorted(declared),
        "reason": str(reason or "")
        or (
            "critical regression on previously declared family"
            if triggers
            else ""
        ),
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "claim_revocation is scope withdrawal for declared families; "
            "does not certify remaining scope; accuracy_claim=false"
        ),
    }


def summarize_findings(
    findings: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    by_sev: Dict[str, int] = {s: 0 for s in sorted(SEVERITIES)}
    by_st: Dict[str, int] = {s: 0 for s in sorted(STATUSES)}
    for f in findings:
        if not isinstance(f, Mapping):
            continue
        sev = str(f.get("severity") or "").lower()
        st = str(f.get("status") or "").lower()
        if sev in by_sev:
            by_sev[sev] += 1
        if st in by_st:
            by_st[st] += 1
    return {
        "n_findings": len([x for x in findings if isinstance(x, Mapping)]),
        "by_severity": by_sev,
        "by_status": by_st,
    }


def security_sec_p1b_status(
    *,
    findings: Optional[Sequence[Mapping[str, Any]]] = None,
    declared_families: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Facade-friendly SEC-P1b status card."""
    defs = load_severity_loop_defaults()
    rows = [dict(x) for x in (findings or []) if isinstance(x, Mapping)]
    gate = evaluate_severity_l5_gate(rows, defaults=defs)
    rev = evaluate_claim_revocation(
        declared_families=declared_families or [],
        new_findings=rows,
        defaults=defs,
    )
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "SEC-P1b",
        "defaults": defs,
        "summary": summarize_findings(rows),
        "l5_gate": gate,
        "claim_revocation": rev,
        "protocol": {
            "l5_block_severities": list(
                (defs.get("defaults") or {}).get("l5_block_severities") or []
            ),
            "require_retest_to_close": bool(
                (defs.get("defaults") or {}).get("require_retest_to_close")
            ),
            "revoke_on_critical_regression": bool(
                (defs.get("defaults") or {}).get("revoke_on_critical_regression")
            ),
            "statuses": sorted(STATUSES),
        },
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "SEC-P1b severity/remediation/retest/claim_revocation loop. "
            "Engineering governance only; accuracy_claim=false; "
            "security_certification=false."
        ),
    }
