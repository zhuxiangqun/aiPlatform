"""Cross-Subject Suite Profile discovery (ADR P2 follow-on).

Loads smoke/regression (and agent benchmark) profiles from Subject seed banks
so Case Pack UI / compile_plan can select beyond agent-only. claim stays false.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

from core.apps.eval.service.capability_case_bank import (
    PROFILE_SCHEMA,
    agent_benchmark_profile,
    agent_regression_profile,
    agent_smoke_profile,
    build_agent_capability_cases,
)
from core.apps.eval.service.target_contract import OBJECT_TYPES

SUBJECT_SUITE_SCHEMA = "eval.subject_suite_profiles.v1"


class SubjectSuiteProfileError(ValueError):
    """Subject suite profile resolve / load failure."""


def _seeds_root() -> Path:
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "eval"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SubjectSuiteProfileError(f"profile missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SubjectSuiteProfileError(f"profile JSON invalid: {path}: {exc}") from exc


def normalize_suite_profile(
    raw: Mapping[str, Any],
    *,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """Normalize seed profile → compile-ready Suite Profile (claim closed)."""
    out = dict(raw or {})
    out.setdefault("schema", PROFILE_SCHEMA)
    kind = str(subject_kind or "").strip().lower()
    if not kind:
        kind = str(out.get("object_type") or "").strip().lower()
    if not kind:
        sk = out.get("subject_kinds")
        if isinstance(sk, (list, tuple)) and sk:
            kind = str(sk[0]).strip().lower()
    if not kind:
        ots = out.get("object_types")
        if isinstance(ots, (list, tuple)) and ots:
            kind = str(ots[0]).strip().lower()
    if not kind:
        pid = str(out.get("profile_id") or "")
        kind = pid.split(".", 1)[0].strip().lower() if "." in pid else ""

    if not out.get("quotas") and isinstance(out.get("capability_quota"), Mapping):
        out["quotas"] = dict(out["capability_quota"])
    out["claim_eligible"] = False
    if kind:
        out["subject_kind"] = kind
        out.setdefault("object_type", kind if kind in OBJECT_TYPES else "")
        if kind in OBJECT_TYPES:
            out.setdefault("object_types", [kind])
        else:
            out.setdefault("subject_kinds", [kind])
            out.setdefault("object_type_member", False)
        if kind in OBJECT_TYPES:
            out["object_type_member"] = True
    out.setdefault("strategy", "stratified")
    out.setdefault("on_insufficient", "error")
    if "holdout" not in out:
        out["holdout"] = {"enabled": False, "exclude_from_tuning": True}
    return out


def _subject_profile_paths(kind: str) -> List[Path]:
    root = _seeds_root() / f"{kind}_capability"
    if not root.is_dir():
        return []
    return sorted(root.glob("profile.*.json"))


def load_subject_suite_profile(
    *,
    subject_kind: str,
    profile_path: Path,
) -> Dict[str, Any]:
    raw = _read_json(profile_path)
    if not isinstance(raw, Mapping):
        raise SubjectSuiteProfileError(f"{profile_path} must be an object")
    return normalize_suite_profile(raw, subject_kind=subject_kind)


def list_subject_suite_profiles(*, include_agent: bool = True) -> List[Dict[str, Any]]:
    """All seed Suite Profiles across promotable Subjects (+ agent built-ins)."""
    from core.apps.eval.service.subject_capability_promote import (
        list_promotable_subject_kinds,
    )

    rows: List[Dict[str, Any]] = []
    seen: set = set()

    if include_agent:
        for loader in (
            agent_smoke_profile,
            agent_regression_profile,
            agent_benchmark_profile,
        ):
            p = normalize_suite_profile(loader(), subject_kind="agent")
            pid = str(p.get("profile_id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                rows.append(p)

    for kind in list_promotable_subject_kinds():
        if kind == "agent":
            continue
        for path in _subject_profile_paths(kind):
            try:
                p = load_subject_suite_profile(subject_kind=kind, profile_path=path)
            except SubjectSuiteProfileError as exc:
                logger.debug(
                    "skip unreadable subject suite profile %s: %s", path, exc
                )
                continue
            pid = str(p.get("profile_id") or "")
            if not pid or pid in seen:
                continue
            if not isinstance(p.get("quotas"), Mapping) or not p.get("quotas"):
                continue
            seen.add(pid)
            rows.append(p)

    rows.sort(key=lambda r: str(r.get("profile_id") or ""))
    return rows


def get_subject_suite_profile(profile_id: str) -> Dict[str, Any]:
    """Resolve any Subject/agent Suite Profile by id (fail closed)."""
    pid = str(profile_id or "").strip()
    if not pid:
        raise SubjectSuiteProfileError("profile_id required")
    for p in list_subject_suite_profiles(include_agent=True):
        if str(p.get("profile_id") or "") == pid:
            return dict(p)
    raise SubjectSuiteProfileError(f"unknown suite profile_id={pid!r}")


def resolve_subject_kind_from_profile(profile: Mapping[str, Any]) -> str:
    kind = str(profile.get("subject_kind") or "").strip().lower()
    if kind:
        return kind
    ot = str(profile.get("object_type") or "").strip().lower()
    if ot:
        return ot
    sk = profile.get("subject_kinds")
    if isinstance(sk, (list, tuple)) and sk:
        return str(sk[0]).strip().lower()
    pid = str(profile.get("profile_id") or "")
    if "." in pid:
        return pid.split(".", 1)[0].strip().lower()
    return "agent"


def load_cases_for_suite_profile(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Load seed cases matching the profile's Subject bank."""
    kind = resolve_subject_kind_from_profile(profile)
    if kind == "agent":
        return list(build_agent_capability_cases())

    from core.apps.eval.service.subject_capability_promote import _bank_specs

    spec = _bank_specs().get(kind)
    if spec is None:
        raise SubjectSuiteProfileError(f"no_case_bank_for_subject:{kind}")
    return list(spec["build"]())


def subject_suite_profile_inventory() -> Dict[str, Any]:
    """Honesty snapshot: discoverable profiles by Subject (claim closed)."""
    profiles = list_subject_suite_profiles(include_agent=True)
    by_kind: Dict[str, int] = {}
    for p in profiles:
        k = resolve_subject_kind_from_profile(p) or "?"
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "schema": SUBJECT_SUITE_SCHEMA,
        "ok": len(profiles) > 0,
        "profile_count": len(profiles),
        "subject_kind_count": len(by_kind),
        "by_subject_kind": dict(sorted(by_kind.items())),
        "profile_ids": [str(p.get("profile_id") or "") for p in profiles],
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "Subject Suite Profiles are seed discovery only; "
            "compile → sample_manifest; claim stays closed."
        ),
        "next_action": (
            "Pick profile_id → compile-suite-profile → run exam; "
            "content_purpose_ok still required before promote freeze."
        ),
    }
