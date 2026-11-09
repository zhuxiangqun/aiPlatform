"""P1-2 starter: judge calibration session + dual-blind / arbiter workflow.

Builds on SEC-P1a ``security_judge_calib`` / CERT-PREP G2b-S:
  - persist pairs + failure queue
  - dual reviewers A/B + arbiter on disagreement
  - failure samples require human review before engineering bar
  - never flips accuracy_claim / security_certification
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.apps.eval.service.security_judge_calib import (
    build_judge_version_manifest,
    evaluate_security_judge_calibration,
    load_judge_calib_defaults,
)

SESSION_SCHEMA = "eval.security_p1_2_judge_session.v1"


class SecurityP12SessionError(ValueError):
    """Fail-closed P1-2 session error."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_session_path() -> Path:
    override = (os.getenv("AIPLAT_JUDGE_CALIB_SESSION_PATH") or "").strip()
    if override:
        return Path(override)
    home = os.getenv("AIPLAT_HOME") or str(Path.home() / ".aiplat")
    return Path(home) / "eval" / "security_judge_calib_session.json"


def empty_session(
    *,
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    judge_model: str = "judge-llm",
    subject_model: str = "subject-llm",
) -> Dict[str, Any]:
    manifest = build_judge_version_manifest(
        judge_id=judge_id,
        judge_version=judge_version,
        judge_model=judge_model,
        subject_model=subject_model,
        prompt_hash="p1-2-starter",
    )
    return {
        "schema": SESSION_SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "manifest": manifest,
        "pairs": [],
        "dual_reviews": {},  # case_id → {reviewer_a, reviewer_b, arbiter?, agreed}
        "status": "open",
        "accuracy_claim": False,
        "security_certification": False,
    }


def load_session(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_session_path()
    if not p.is_file():
        return empty_session()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SecurityP12SessionError("session_not_object")
    raw.setdefault("schema", SESSION_SCHEMA)
    raw["accuracy_claim"] = False
    raw["security_certification"] = False
    return raw


def save_session(session: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    p = Path(path) if path else default_session_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    out = dict(session)
    out["updated_at"] = _now()
    out["accuracy_claim"] = False
    out["security_certification"] = False
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def record_judge_gold_pair(
    session: Dict[str, Any],
    *,
    case_id: str,
    gold: bool,
    judge: bool,
    notes: str = "",
) -> Dict[str, Any]:
    cid = str(case_id or "").strip()
    if not cid:
        raise SecurityP12SessionError("case_id_required")
    pairs = [p for p in (session.get("pairs") or []) if str(p.get("case_id")) != cid]
    pairs.append(
        {
            "case_id": cid,
            "gold": bool(gold),
            "judge": bool(judge),
            "notes": notes,
            "recorded_at": _now(),
        }
    )
    session["pairs"] = pairs
    # Auto-queue disagreements for dual human review
    if bool(gold) != bool(judge):
        reviews = dict(session.get("dual_reviews") or {})
        reviews.setdefault(
            cid,
            {
                "reason": "gold_judge_disagree",
                "reviewer_a": None,
                "reviewer_b": None,
                "arbiter": None,
                "agreed": False,
            },
        )
        session["dual_reviews"] = reviews
    return session


def submit_dual_review(
    session: Dict[str, Any],
    *,
    case_id: str,
    reviewer: str,
    slot: str,
    label: bool,
) -> Dict[str, Any]:
    """slot = a|b|arbiter. Arbiter required when A≠B."""
    cid = str(case_id or "").strip()
    slot_n = str(slot or "").strip().lower()
    if slot_n not in ("a", "b", "arbiter"):
        raise SecurityP12SessionError("slot_must_be_a_b_or_arbiter")
    reviews = dict(session.get("dual_reviews") or {})
    row = dict(reviews.get(cid) or {"reviewer_a": None, "reviewer_b": None, "arbiter": None})
    entry = {"reviewer": str(reviewer), "label": bool(label), "at": _now()}
    if slot_n == "a":
        row["reviewer_a"] = entry
    elif slot_n == "b":
        row["reviewer_b"] = entry
    else:
        row["arbiter"] = entry
    a = row.get("reviewer_a") or {}
    b = row.get("reviewer_b") or {}
    if a and b:
        if bool(a.get("label")) == bool(b.get("label")):
            row["agreed"] = True
            row["final_label"] = bool(a.get("label"))
        elif row.get("arbiter"):
            row["agreed"] = True
            row["final_label"] = bool((row.get("arbiter") or {}).get("label"))
        else:
            row["agreed"] = False
            row["needs_arbiter"] = True
    reviews[cid] = row
    session["dual_reviews"] = reviews
    return session


def failure_case_ids(session: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for p in session.get("pairs") or []:
        if not isinstance(p, Mapping):
            continue
        if bool(p.get("gold")) != bool(p.get("judge")):
            out.append(str(p.get("case_id")))
    return out


def dual_human_completed(session: Mapping[str, Any]) -> bool:
    fails = failure_case_ids(session)
    if not fails:
        return True
    reviews = session.get("dual_reviews") or {}
    for cid in fails:
        row = reviews.get(cid) if isinstance(reviews, Mapping) else None
        if not isinstance(row, Mapping) or not row.get("agreed"):
            return False
    return True


def evaluate_p1_2_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Run engineering calibration gate over session pairs + dual-review state."""
    fails = failure_case_ids(session)
    dual_done = dual_human_completed(session)
    manifest = dict(session.get("manifest") or {})
    manifest["dual_human_completed"] = dual_done
    report = evaluate_security_judge_calibration(
        pairs=list(session.get("pairs") or []),
        manifest=manifest,
        frozen_manifest=dict(session.get("manifest") or {}),
        failure_case_ids=fails,
    )
    pending = [c for c in fails if not ((session.get("dual_reviews") or {}).get(c) or {}).get("agreed")]
    status = "calibrated_engineering" if report.get("meets_engineering_bar") else "in_progress"
    if pending:
        status = "awaiting_dual_review"
    session["status"] = status
    session["last_evaluation"] = {
        "at": _now(),
        "meets_engineering_bar": report.get("meets_engineering_bar"),
        "asr_status": report.get("asr_status"),
        "pending_dual_review": pending,
    }
    return {
        "schema": SESSION_SCHEMA,
        "session_status": status,
        "calibration": report,
        "pending_dual_review": pending,
        "failure_case_ids": fails,
        "dual_human_completed": dual_done,
        "n_pairs": len(session.get("pairs") or []),
        "l5_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "P1-2 starter: disagreement → dual reviewers; A≠B → arbiter. "
            "Engineering bar ≠ certification."
        ),
    }


def security_p1_2_status(*, path: Optional[Path] = None) -> Dict[str, Any]:
    session = load_session(path)
    return evaluate_p1_2_session(session)
