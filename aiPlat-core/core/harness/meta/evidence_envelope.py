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


def _normalize_evidence(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:32]:
        if not isinstance(item, Mapping):
            continue
        out.append(
            evidence_item(
                type=str(item.get("type") or "tool_result"),
                ref=str(item.get("ref") or item.get("path") or ""),
                run_id=str(item.get("run_id") or ""),
                hash=str(item.get("hash") or ""),
                snippet=str(item.get("snippet") or item.get("detail") or ""),
            )
        )
    return out


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
) -> EnvelopeValidation:
    """Validate + optionally demote illegal confirmed/block claims.

    Rules:
      - confirmed ⇒ measured + non-empty evidence (else demote → suspected)
      - duty block claim (status=blocked) ⇒ non-empty limitations
      - speculative cannot be confirmed/blocked
    """
    env = normalize_envelope(raw)
    errors: List[str] = []
    demotions: List[str] = []

    if env["status"] == "confirmed":
        if env["confidence"] != "measured":
            errors.append("confirmed_requires_measured")
        if not env["evidence"]:
            errors.append("confirmed_requires_evidence")
        if errors and demote:
            env["status"] = "suspected"
            if env["confidence"] == "measured" and not env["evidence"]:
                env["confidence"] = "derived"
            demotions.append("confirmed→suspected")
            errors = []

    if env["status"] == "blocked" and require_limitations_for_block:
        if not env["limitations"]:
            errors.append("blocked_requires_limitations")
            if demote:
                env["status"] = "suspected"
                demotions.append("blocked→suspected(no_limitations)")
                errors = [e for e in errors if e != "blocked_requires_limitations"]

    if env["confidence"] == "speculative" and env["status"] in ("confirmed", "blocked"):
        prev = env["status"]
        errors.append("speculative_cannot_block_or_confirm")
        if demote:
            env["status"] = "unverified"
            demotions.append(f"{prev}→unverified(speculative)")
            errors = [e for e in errors if e != "speculative_cannot_block_or_confirm"]

    ok = len(errors) == 0
    return EnvelopeValidation(ok=ok, errors=errors, demotions=demotions, envelope=env)


def allow_release_block(envelope: Mapping[str, Any]) -> Tuple[bool, str]:
    """Whether this finding alone may block release (duty board block).

    derived → False (watch/HITL); speculative → False; confirmed measured → True.
    """
    v = validate_envelope(envelope, demote=True)
    env = v.envelope
    if env.get("status") == "blocked" and env.get("limitations") and env.get("confidence") == "measured":
        return True, "blocked_measured"
    if env.get("status") == "confirmed" and env.get("confidence") == "measured" and env.get("evidence"):
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
) -> List[Dict[str, Any]]:
    """Ensure each issue dict has a validated evidence envelope (mutates in place)."""
    out: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, MutableMapping):
            continue
        raw = issue.get("evidence_envelope") or issue.get("envelope")
        if isinstance(raw, Mapping) and raw:
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
        confirmed_ok = (
            env.get("status") == "confirmed"
            and env.get("confidence") == "measured"
            and bool(env.get("evidence"))
        )
        issue["envelope_ok"] = bool(v.ok) and (
            env.get("status") != "confirmed" or confirmed_ok
        )
        out.append(dict(issue))
    return out


def summarize_envelopes(issues: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate envelope posture for duty board / report footer (no fake green)."""
    by_status: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}
    demoted = 0
    missing = 0
    for issue in issues:
        env = issue.get("evidence_envelope") if isinstance(issue, Mapping) else None
        if not isinstance(env, Mapping) or not env:
            missing += 1
            continue
        st = str(env.get("status") or "unverified")
        cf = str(env.get("confidence") or "speculative")
        by_status[st] = by_status.get(st, 0) + 1
        by_confidence[cf] = by_confidence.get(cf, 0) + 1
        if st == "suspected" and cf == "derived":
            demoted += 0  # informational only
    return {
        "issue_count": len(list(issues)),
        "missing_envelope": missing,
        "by_status": by_status,
        "by_confidence": by_confidence,
        "confirmed_count": int(by_status.get("confirmed") or 0),
        "suspected_count": int(by_status.get("suspected") or 0),
    }
