"""Evidence Envelope — force honest findings (no fake confirmed).

Every finding/conclusion/gate decision should carry:
  status, confidence, evidence[], limitations, next_check

Gate rules (merge / duty / autoreview):
  - confirmed requires confidence=measured AND non-empty evidence
  - block (duty) requires non-empty limitations
  - derived → watch at most (not sole block); speculative → backlog only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

STATUSES = frozenset({"confirmed", "suspected", "unverified", "blocked"})
CONFIDENCES = frozenset({"measured", "derived", "speculative"})
EVIDENCE_TYPES = frozenset({
    "file_line",
    "command",
    "tool_result",
    "test_result",
    "log",
    "jsonl",
})

# Prefer high-signal evidence when compacting (anti inflation / formalism).
_EVIDENCE_TYPE_RANK = {
    "test_result": 0,
    "command": 1,
    "file_line": 2,
    "jsonl": 3,
    "tool_result": 4,
    "log": 5,
}
_DEFAULT_EVIDENCE_CAP = 8

# release / duty impact
_STATUS_RANK = {"confirmed": 3, "blocked": 2, "suspected": 1, "unverified": 0}


@dataclass
class EnvelopeValidation:
    ok: bool
    errors: List[str] = field(default_factory=list)
    demotions: List[str] = field(default_factory=list)
    envelope: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "demotions": list(self.demotions),
            "envelope": dict(self.envelope),
        }


def empty_envelope(
    *,
    status: str = "unverified",
    confidence: str = "speculative",
    limitations: Optional[Sequence[str]] = None,
    next_check: str = "",
) -> Dict[str, Any]:
    return {
        "status": status if status in STATUSES else "unverified",
        "confidence": confidence if confidence in CONFIDENCES else "speculative",
        "evidence": [],
        "limitations": list(limitations or []),
        "next_check": str(next_check or ""),
    }


def evidence_item(
    *,
    type: str,
    ref: str = "",
    run_id: str = "",
    hash: str = "",
    snippet: str = "",
) -> Dict[str, Any]:
    t = str(type or "").strip()
    if t not in EVIDENCE_TYPES:
        t = "tool_result"
    return {
        "type": t,
        "ref": str(ref or "")[:500],
        "run_id": str(run_id or "")[:128],
        "hash": str(hash or "")[:128],
        "snippet": str(snippet or "")[:400],
    }


def compact_evidence(
    items: Sequence[Mapping[str, Any]],
    *,
    max_items: int = _DEFAULT_EVIDENCE_CAP,
) -> List[Dict[str, Any]]:
    """Dedupe by (type, ref, hash) and keep highest-signal samples only.

    Caps list length so envelopes cannot bury reviewers in low-value logs.
    """
    cap = max(1, min(int(max_items or _DEFAULT_EVIDENCE_CAP), 32))
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        normalized.append(
            evidence_item(
                type=str(item.get("type") or "tool_result"),
                ref=str(item.get("ref") or item.get("path") or ""),
                run_id=str(item.get("run_id") or ""),
                hash=str(item.get("hash") or ""),
                snippet=str(item.get("snippet") or item.get("detail") or ""),
            )
        )
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for ev in normalized:
        key = (ev.get("type"), ev.get("ref"), ev.get("hash"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)
    unique.sort(
        key=lambda e: (
            _EVIDENCE_TYPE_RANK.get(str(e.get("type")), 9),
            0 if e.get("hash") else 1,
            0 if e.get("ref") else 1,
        )
    )
    return unique[:cap]


def _normalize_evidence(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return compact_evidence(raw, max_items=_DEFAULT_EVIDENCE_CAP)


def _normalize_limitations(raw: Any) -> List[str]:
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()[:300]]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw[:16]:
        s = str(x or "").strip()
        if s:
            out.append(s[:300])
    return out


def normalize_envelope(raw: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Coerce a mapping into a canonical envelope (does not enforce gate rules)."""
    src = dict(raw or {})
    status = str(src.get("status") or "unverified").strip().lower()
    confidence = str(src.get("confidence") or "speculative").strip().lower()
    if status not in STATUSES:
        status = "unverified"
    if confidence not in CONFIDENCES:
        confidence = "speculative"
    return {
        "status": status,
        "confidence": confidence,
        "evidence": _normalize_evidence(src.get("evidence")),
        "limitations": _normalize_limitations(src.get("limitations")),
        "next_check": str(src.get("next_check") or "")[:400],
    }


def validate_envelope(
    raw: Optional[Mapping[str, Any]] = None,
    *,
    demote: bool = True,
    require_limitations_for_block: bool = True,
    mode: str = "",
) -> EnvelopeValidation:
    """Validate + optionally demote illegal confirmed/block claims.

    Rules:
      - confirmed ⇒ measured + non-empty evidence (else demote → suspected)
      - duty block claim (status=blocked) ⇒ non-empty limitations
      - speculative cannot be confirmed/blocked

    ``mode``:
      - ``demote`` (default when demote=True): rewrite illegal claims; ``ok`` True after demote
      - ``strict`` (when demote=False): report errors; do not rewrite
      - ``reject``: rewrite for safe display, but ``ok`` stays False (anti-formalism)
    """
    m = (mode or "").strip().lower()
    if m not in ("demote", "reject", "strict"):
        m = "demote" if demote else "strict"
    rewrite = m in ("demote", "reject")

    env = normalize_envelope(raw)
    errors: List[str] = []
    demotions: List[str] = []

    if env["status"] == "confirmed":
        if env["confidence"] != "measured":
            errors.append("confirmed_requires_measured")
        if not env["evidence"]:
            errors.append("confirmed_requires_evidence")
        if errors and rewrite:
            env["status"] = "suspected"
            if env["confidence"] == "measured" and not env["evidence"]:
                env["confidence"] = "derived"
            demotions.append("confirmed→suspected")
            if m == "demote":
                errors = []

    if env["status"] == "blocked" and require_limitations_for_block:
        if not env["limitations"]:
            errors.append("blocked_requires_limitations")
            if rewrite:
                env["status"] = "suspected"
                demotions.append("blocked→suspected(no_limitations)")
                if m == "demote":
                    errors = [e for e in errors if e != "blocked_requires_limitations"]

    if env["confidence"] == "speculative" and env["status"] in ("confirmed", "blocked"):
        prev = env["status"]
        errors.append("speculative_cannot_block_or_confirm")
        if rewrite:
            env["status"] = "unverified"
            demotions.append(f"{prev}→unverified(speculative)")
            if m == "demote":
                errors = [e for e in errors if e != "speculative_cannot_block_or_confirm"]

    # Reject mode: any demotion from an illegal claim ⇒ integrity failure.
    if m == "reject" and demotions:
        ok = False
        if not errors:
            errors = ["envelope_integrity_rejected"]
    else:
        ok = len(errors) == 0
    return EnvelopeValidation(ok=ok, errors=errors, demotions=demotions, envelope=env)


def assert_envelope_integrity(raw: Optional[Mapping[str, Any]] = None) -> EnvelopeValidation:
    """Hard gate: illegal confirmed/block claims fail (still returns demoted envelope)."""
    return validate_envelope(raw, mode="reject")


def allow_release_block(envelope: Mapping[str, Any]) -> Tuple[bool, str]:
    """Whether this finding alone may block release (duty board block).

    derived → False (watch/HITL); speculative → False; confirmed measured → True.
    """
    v = validate_envelope(envelope, demote=True)
    env = v.envelope
    if not env.get("limitations"):
        return False, "block_requires_limitations"
    if env.get("status") == "blocked" and env.get("confidence") == "measured":
        return True, "blocked_measured"
    if (
        env.get("status") == "confirmed"
        and env.get("confidence") == "measured"
        and env.get("evidence")
    ):
        return True, "confirmed_measured"
    if env.get("confidence") == "derived":
        return False, "derived_watch_only"
    if env.get("confidence") == "speculative":
        return False, "speculative_backlog_only"
    return False, "insufficient_envelope"


def envelope_from_review_issue(
    *,
    file: str = "",
    line: int = 0,
    severity: str = "P2",
    description: str = "",
    engine: str = "",
    run_id: str = "",
) -> Dict[str, Any]:
    """Build a derived envelope for static LLM review findings (never auto-confirmed)."""
    evidence: List[Dict[str, Any]] = []
    if file:
        evidence.append(
            evidence_item(
                type="file_line",
                ref=f"{file}:{int(line or 0)}",
                run_id=run_id,
                snippet=(description or "")[:200],
            )
        )
    limitations = [
        "static LLM autoreview; runtime behavior not verified",
        "not a substitute for SAST / unit tests / measured gates",
    ]
    if engine:
        limitations.append(f"engine={engine}")
    status = "suspected" if evidence else "unverified"
    next_check = (
        "repro with test or command evidence to raise confidence to measured"
        if evidence
        else "attach file:line or tool_result evidence"
    )
    return normalize_envelope(
        {
            "status": status,
            "confidence": "derived" if evidence else "speculative",
            "evidence": evidence,
            "limitations": limitations,
            "next_check": next_check,
        }
    )


def attach_envelopes_to_issues(
    issues: Sequence[MutableMapping[str, Any]],
    *,
    run_id: str = "",
    reject_fake: bool = True,
) -> List[Dict[str, Any]]:
    """Ensure each issue dict has a validated evidence envelope (mutates in place).

    When ``reject_fake`` and the *caller-supplied* envelope illegally claimed
    confirmed/blocked, mark ``envelope_integrity_rejected`` (anti-formalism).
    Autogenerated derived envelopes from review issues are never integrity-rejected.
    """
    out: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, MutableMapping):
            continue
        raw = issue.get("evidence_envelope") or issue.get("envelope")
        supplied = isinstance(raw, Mapping) and bool(raw)
        integrity_rejected = False
        integrity_errors: List[str] = []
        if supplied:
            if reject_fake:
                hard = assert_envelope_integrity(raw)
                integrity_rejected = not hard.ok
                integrity_errors = list(hard.errors)
                env = hard.envelope
                v = hard
            else:
                v = validate_envelope(raw, demote=True)
                env = v.envelope
        else:
            env = envelope_from_review_issue(
                file=str(issue.get("file") or ""),
                line=int(issue.get("line") or 0),
                severity=str(issue.get("severity") or "P2"),
                description=str(issue.get("description") or ""),
                engine=str(issue.get("engine") or ""),
                run_id=run_id,
            )
            v = validate_envelope(env, demote=True)
            env = v.envelope
        # Strip illegal confirmed claims that slipped past
        if env.get("status") == "confirmed" and (
            env.get("confidence") != "measured" or not env.get("evidence")
        ):
            env["status"] = "suspected"
            env["confidence"] = "derived" if env.get("evidence") else "speculative"
        issue["evidence_envelope"] = env
        issue["envelope_integrity_rejected"] = bool(integrity_rejected)
        if integrity_errors:
            issue["envelope_integrity_errors"] = integrity_errors
        confirmed_ok = (
            env.get("status") == "confirmed"
            and env.get("confidence") == "measured"
            and bool(env.get("evidence"))
        )
        # Safe demoted/autogen envelopes are display-ok; fake supplied claims fail integrity.
        if integrity_rejected:
            issue["envelope_ok"] = False
        else:
            issue["envelope_ok"] = env.get("status") != "confirmed" or confirmed_ok
        out.append(dict(issue))
    return out


def check_issues_envelope_integrity(
    issues: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Report-level integrity: any fake confirmed/blocked claim ⇒ not ok."""
    rejected: List[Dict[str, Any]] = []
    for issue in issues or []:
        if not isinstance(issue, Mapping):
            continue
        if issue.get("envelope_integrity_rejected"):
            rejected.append(
                {
                    "ref": str(issue.get("file") or issue.get("id") or "")[:200],
                    "errors": list(issue.get("envelope_integrity_errors") or []),
                }
            )
            continue
        raw = issue.get("evidence_envelope") or issue.get("envelope")
        if not isinstance(raw, Mapping) or not raw:
            continue
        # Only re-check if caller marked confirmed/blocked without going through attach.
        st = str(raw.get("status") or "").lower()
        if st not in ("confirmed", "blocked"):
            continue
        hard = assert_envelope_integrity(raw)
        if not hard.ok:
            rejected.append(
                {
                    "ref": str(issue.get("file") or issue.get("id") or "")[:200],
                    "errors": list(hard.errors),
                }
            )
    return {
        "ok": len(rejected) == 0,
        "rejected_count": len(rejected),
        "rejected": rejected[:20],
    }


def summarize_envelopes(issues: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate envelope posture for duty board / report footer (no fake green)."""
    by_status: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}
    missing = 0
    integrity_rejected = 0
    for issue in issues:
        if isinstance(issue, Mapping) and issue.get("envelope_integrity_rejected"):
            integrity_rejected += 1
        env = issue.get("evidence_envelope") if isinstance(issue, Mapping) else None
        if not isinstance(env, Mapping) or not env:
            missing += 1
            continue
        st = str(env.get("status") or "unverified")
        cf = str(env.get("confidence") or "speculative")
        by_status[st] = by_status.get(st, 0) + 1
        by_confidence[cf] = by_confidence.get(cf, 0) + 1
    integrity = check_issues_envelope_integrity(list(issues))
    return {
        "issue_count": len(list(issues)),
        "missing_envelope": missing,
        "by_status": by_status,
        "by_confidence": by_confidence,
        "confirmed_count": int(by_status.get("confirmed") or 0),
        "suspected_count": int(by_status.get("suspected") or 0),
        "integrity_ok": bool(integrity.get("ok")),
        "integrity_rejected_count": int(
            integrity_rejected or integrity.get("rejected_count") or 0
        ),
        "evidence_cap": _DEFAULT_EVIDENCE_CAP,
    }


def envelope_for_gold_block(
    *,
    reason: str,
    p0_miss_rate: Any = None,
    regressing: bool = False,
    written_at: str = "",
    report_ref: str = "code_review_gold_reports",
) -> Dict[str, Any]:
    """Measured envelope for duty-board gold BLOCK (JSONL evidence + limitations)."""
    snippet = (
        f"{reason}; p0_miss_rate={p0_miss_rate}; regressing={regressing}"
        f"{('; @' + written_at) if written_at else ''}"
    )[:400]
    return normalize_envelope(
        {
            "status": "blocked",
            "confidence": "measured",
            "evidence": [
                evidence_item(
                    type="jsonl",
                    ref=str(report_ref or "code_review_gold_reports")[:500],
                    snippet=snippet,
                )
            ],
            "limitations": [
                "gold eval JSONL only (match-only or live); not full SAST/security audit",
                "thresholds from duty_board.yaml; thin gold sets may under-report misses",
            ],
            "next_check": (
                "run Gold match-only --persist; re-check p0_miss_rate and trend_summary"
            ),
        }
    )


def envelope_for_exemption_debt_block(
    *,
    reason: str,
    expired_count: int = 0,
    invalid_count: int = 0,
    over_cap: bool = False,
    active_count: int = 0,
    max_active: Optional[int] = None,
    config_ref: str = "physical_merge_gates.yaml",
) -> Dict[str, Any]:
    """Measured envelope for duty-board exemption-debt BLOCK (YAML ledger + limitations)."""
    snippet = (
        f"{reason}; expired={expired_count}; invalid={invalid_count}; "
        f"over_cap={over_cap}; active={active_count}"
        + (f"/{max_active}" if max_active is not None else "")
    )[:400]
    return normalize_envelope(
        {
            "status": "blocked",
            "confidence": "measured",
            "evidence": [
                evidence_item(
                    type="file_line",
                    ref=str(config_ref or "physical_merge_gates.yaml")[:500],
                    snippet=snippet,
                )
            ],
            "limitations": [
                "exemption ledger from physical_merge_gates.yaml only; not runtime PolicyGate",
                "owner/reason/expires validity is structural — does not prove fix landed",
            ],
            "next_check": (
                "renew owner+expires, remove expired rows, or lower active below max_active_exemptions"
            ),
        }
    )


def envelope_for_gate_meta_block(
    *,
    reason: str,
    exemption_rate: Optional[float] = None,
    skip_rate: Optional[float] = None,
    appeal_rate: Optional[float] = None,
    n_runs: int = 0,
    n_skips: int = 0,
    n_appeals: int = 0,
    window_days: float = 30.0,
    jsonl_ref: str = "org/gate_meta/runs.jsonl",
) -> Dict[str, Any]:
    """Measured envelope for gate-meta calibration BLOCK (JSONL rates + limitations)."""
    snippet = (
        f"{reason}; exemption_rate={exemption_rate}; skip_rate={skip_rate}; "
        f"appeal_rate={appeal_rate}; n_runs={n_runs}; n_skips={n_skips}; "
        f"n_appeals={n_appeals}; window_days={window_days}"
    )[:400]
    return normalize_envelope(
        {
            "status": "blocked",
            "confidence": "measured",
            "evidence": [
                evidence_item(
                    type="file_line",
                    ref=str(jsonl_ref or "org/gate_meta/runs.jsonl")[:500],
                    snippet=snippet,
                )
            ],
            "limitations": [
                "rates from local gate_meta JSONL only — not remote CI fleet",
                "high exemption/skip/appeal implies miscalibration, not a single bad PR",
            ],
            "next_check": (
                "tune physical_merge_gates.yaml thresholds / shape rules; "
                "retire unjustified SKIP_*; refine rules with appeal codes"
            ),
        }
    )


def envelope_for_repo_health_block(
    *,
    reason: str,
    py_loc: Optional[int] = None,
    god_files: Optional[int] = None,
    multi_base: Optional[int] = None,
    high_fanout: Optional[int] = None,
    dep_entries: Optional[int] = None,
    loc_growth_pct: Optional[float] = None,
    n_snapshots: int = 0,
    jsonl_ref: str = "org/repo_health/snapshots.jsonl",
) -> Dict[str, Any]:
    """Measured envelope for post-merge repo-health BLOCK (full-tree JSONL + limitations)."""
    snippet = (
        f"{reason}; loc={py_loc}; god={god_files}; multi_base={multi_base}; "
        f"fanout={high_fanout}; deps={dep_entries}; loc_growth_pct={loc_growth_pct}; "
        f"n_snapshots={n_snapshots}"
    )[:400]
    return normalize_envelope(
        {
            "status": "blocked",
            "confidence": "measured",
            "evidence": [
                evidence_item(
                    type="file_line",
                    ref=str(jsonl_ref or "org/repo_health/snapshots.jsonl")[:500],
                    snippet=snippet,
                )
            ],
            "limitations": [
                "metrics from local repo_health JSONL only — not CI fleet aggregate",
                "absolute thresholds catch boiling-frog bloat; merge gates still own per-PR diffs",
            ],
            "next_check": (
                "run scripts/scan_repo_health.py weekly; split god files / cut fan-out / "
                "retire unused deps; retune duty_board.yaml bands if false-positive"
            ),
        }
    )


def gate_duty_status_with_envelopes(
    status: str,
    envelopes: Sequence[Mapping[str, Any]],
) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """Enforce envelope release rules on duty status.

    - block requires ≥1 envelope with allow_release_block=True
    - otherwise demote block → watch (derived/speculative cannot sole-block)
    Returns (status, extra_reasons, rows[{envelope, allow_block, why}]).
    """
    rows: List[Dict[str, Any]] = []
    for raw in envelopes:
        if not isinstance(raw, Mapping):
            continue
        ok, why = allow_release_block(raw)
        v = validate_envelope(raw, demote=True)
        rows.append(
            {
                "envelope": v.envelope,
                "allow_block": bool(ok),
                "why": why,
            }
        )
    extras: List[str] = []
    st = str(status or "unavailable")
    if st == "block":
        if not any(r.get("allow_block") for r in rows):
            st = "watch"
            extras.append("block_demoted_no_envelope_allow_release_block")
    return st, extras, rows


def fold_findings_for_duty(
    findings: Sequence[Any],
    *,
    run_id: str = "",
) -> Dict[str, Any]:
    """Attach/validate envelopes on finding dicts; return duty-board fold posture.

    - measured + allow_release_block → status_hint=block (+ envelope_measured_block)
    - any other findings → watch at most (derived/speculative never sole-block)
    """
    issues: List[Dict[str, Any]] = []
    for raw in findings or []:
        if isinstance(raw, Mapping):
            issues.append(dict(raw))
    attached = attach_envelopes_to_issues(issues, run_id=run_id or "")
    summary = summarize_envelopes(attached)
    envelopes: List[Dict[str, Any]] = []
    reasons: List[str] = []
    release_ok = 0
    for issue in attached:
        env = issue.get("evidence_envelope")
        if not isinstance(env, Mapping):
            continue
        envelopes.append(dict(env))
        ok, why = allow_release_block(env)
        if ok:
            release_ok += 1
            reasons.append(f"envelope_measured_block:{why}")
    summary["release_block_ok"] = release_ok
    summary["allow_block_count"] = release_ok
    if release_ok > 0:
        status_hint = "block"
    elif attached:
        status_hint = "watch"
        if not reasons:
            reasons.append("envelope_derived_or_speculative_watch_only")
    else:
        status_hint = "go"
    return {
        "status_hint": status_hint,
        "reasons": reasons,
        "issues": attached,
        "summary": summary,
        "envelopes": envelopes,
    }
