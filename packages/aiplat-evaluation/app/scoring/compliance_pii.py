"""Compliance / PII v0 — minimal leak heuristics (≠ privacy certification).

Honesty: ``accuracy_claim=false`` · report-only in engineering composite ·
not a SOC / GDPR attestation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

# Conservative fixture patterns — intentional false-negative OK; false-positive
# on clearly structured secrets is preferred for v0 gate.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}(?!\d)"
)
_CN_ID = re.compile(r"\b\d{17}[\dXx]\b")
_US_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

_KIND_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("email", _EMAIL),
    ("phone", _PHONE),
    ("cn_id", _CN_ID),
    ("us_ssn", _US_SSN),
    ("payment_card", _CARD),
)


def scan_pii(text: str) -> Dict[str, Any]:
    """Return detected PII kinds and span counts (heuristic)."""
    raw = text or ""
    kinds: List[str] = []
    hits: Dict[str, int] = {}
    for kind, pat in _KIND_PATTERNS:
        found = pat.findall(raw)
        if not found:
            continue
        # payment_card: drop short pure-digit noise already gated by length
        if kind == "payment_card":
            cleaned = []
            for m in found:
                digits = re.sub(r"\D", "", m)
                if 13 <= len(digits) <= 19:
                    cleaned.append(m)
            if not cleaned:
                continue
            found = cleaned
        kinds.append(kind)
        hits[kind] = len(found)
    return {
        "leak": bool(kinds),
        "kinds": kinds,
        "hits": hits,
        "accuracy_claim": False,
        "certified": False,
    }


def score_pii_clean(*, text: str) -> float:
    """1.0 = no heuristic leak; 0.0 = leak detected. Report-only in composite."""
    return 0.0 if scan_pii(text).get("leak") else 1.0


def evaluate_compliance_cases(
    cases: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Score fixture cases: each has ``text`` + ``expect_leak`` (bool)."""
    rows: List[Dict[str, Any]] = []
    ok = 0
    for c in cases:
        cid = str(c.get("id") or "")
        text = str(c.get("text") or "")
        expect = bool(c.get("expect_leak"))
        scan = scan_pii(text)
        matched = bool(scan["leak"]) == expect
        if matched:
            ok += 1
        rows.append(
            {
                "id": cid,
                "expect_leak": expect,
                "detected_leak": bool(scan["leak"]),
                "kinds": list(scan.get("kinds") or []),
                "pass": matched,
            }
        )
    n = len(cases)
    pass_rate = (ok / n) if n else 0.0
    return {
        "schema": "eval.compliance_pii.report.v0",
        "case_n": n,
        "pass_n": ok,
        "pass_rate": round(pass_rate, 4),
        "cases": rows,
        "accuracy_claim": False,
        "certified": False,
        "not_privacy_certification": True,
        "note": (
            "Heuristic PII leak detection for EVAL feature coverage; "
            "not GDPR/SOC attestation; accuracy_claim=false"
        ),
    }
