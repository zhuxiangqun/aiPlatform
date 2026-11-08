"""Agent capability Case Bank — load curated seeds (draft, claim=false).

Content authority lives under workspace_seeds/eval/agent_capability/:
  - cases/{capability}.json   ← edit / extend here
  - pack.meta.json
  - profile.agent.*.json
Derived combined pack (pack.agent.capability.v*.json) is assembled by
``write_agent_capability_seeds`` for promote / human review convenience.

Python is loader + validate + Profile resolve + promote — not the question editor.
Authority: CAPABILITY_ID_MAP_V1 + CASE_TEST_PURPOSE_SCHEMA_V1 + Suite Profile v1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_factory import CaseFactoryError, validate_case_dict
from core.apps.eval.service.case_pack_hash import compute_case_hash
from core.apps.eval.service.capability_id_map import (
    V1_IN_SCOPE,
    resolve_capability_ids,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter

PACK_SCHEMA = "eval.case_pack.v1"
PACK_ID = "agent.capability"
PACK_VERSION = "0.1.0"
PROFILE_ID = "agent.regression.v1"
PROFILE_ID_SMOKE = "agent.smoke.v1"
PROFILE_ID_BENCHMARK = "agent.benchmark.v1"
PROFILE_SCHEMA = "eval.suite_profile.v1"

_PROFILE_FILES = {
    PROFILE_ID_SMOKE: "profile.agent.smoke.v1.json",
    PROFILE_ID: "profile.agent.regression.v1.json",
    PROFILE_ID_BENCHMARK: "profile.agent.benchmark.v1.json",
}


class CapabilityCaseBankError(ValueError):
    """Seed bank load / assemble failure (fail closed)."""


def default_seed_dir() -> Path:
    # .../aiPlat-core/core/apps/eval/service/this.py → parents[4]=aiPlat-core
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CapabilityCaseBankError(f"seed missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityCaseBankError(f"seed JSON invalid: {path}: {exc}") from exc


def load_pack_meta(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load pack.meta.json (pack-level fields without cases)."""
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta_path = root / "pack.meta.json"
    if meta_path.is_file():
        raw = _read_json(meta_path)
        if not isinstance(raw, Mapping):
            raise CapabilityCaseBankError("pack.meta.json must be an object")
        return dict(raw)
    # Fallback: derive meta from combined pack if present (migration).
    pack_path = root / f"pack.{PACK_ID}.v{PACK_VERSION}.json"
    if pack_path.is_file():
        doc = _read_json(pack_path)
        if not isinstance(doc, Mapping):
            raise CapabilityCaseBankError("combined pack must be an object")
        out = {k: v for k, v in doc.items() if k != "cases"}
        out.setdefault("notes", "derived from combined pack (prefer pack.meta.json)")
        return out
    raise CapabilityCaseBankError(
        f"neither pack.meta.json nor combined pack found under {root}"
    )


def _normalize_case(raw: Mapping[str, Any]) -> Dict[str, Any]:
    case = dict(raw)
    caps = resolve_capability_ids(list(case.get("capabilities") or []), fail_closed=True)
    if not caps:
        raise CapabilityCaseBankError(
            f"case {case.get('case_id')!r} missing capabilities"
        )
    if caps[0] not in V1_IN_SCOPE:
        raise CapabilityCaseBankError(
            f"case {case.get('case_id')!r} out-of-scope capability {caps[0]!r}"
        )
    case["capabilities"] = caps
    case["category"] = caps[0]
    req = dict(case.get("requires") or {})
    req["capabilities"] = caps
    case["requires"] = req
    # Content is authority; refresh hash so editors need not hand-maintain it.
    case["hash"] = compute_case_hash(case)
    return case


def load_agent_capability_cases(
    *,
    seed_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load curated cases from cases/*.json (preferred) or combined pack.

    Prefer per-capability files under ``cases/`` — that is the edit surface.
    Combined ``pack.*.json`` is only a fallback for older checkouts.
    """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    cases_dir = root / "cases"
    rows: List[Dict[str, Any]] = []

    if cases_dir.is_dir():
        paths = sorted(cases_dir.glob("*.json"))
        if not paths:
            raise CapabilityCaseBankError(f"no case files under {cases_dir}")
        for path in paths:
            payload = _read_json(path)
            if not isinstance(payload, list):
                raise CapabilityCaseBankError(
                    f"{path.name} must be a JSON array of cases"
                )
            for item in payload:
                if not isinstance(item, Mapping):
                    raise CapabilityCaseBankError(
                        f"{path.name} contains non-object case"
                    )
                rows.append(_normalize_case(item))
    else:
        pack_path = root / f"pack.{PACK_ID}.v{PACK_VERSION}.json"
        doc = _read_json(pack_path)
        if not isinstance(doc, Mapping):
            raise CapabilityCaseBankError("combined pack must be an object")
        for item in list(doc.get("cases") or []):
            if not isinstance(item, Mapping):
                raise CapabilityCaseBankError("combined pack cases must be objects")
            rows.append(_normalize_case(item))

    # Stable order: capability then case_id (deterministic compiles).
    rows.sort(
        key=lambda c: (
            str((c.get("capabilities") or [""])[0]),
            str(c.get("case_id") or ""),
        )
    )

    seen: set = set()
    for c in rows:
        cid = str(c.get("case_id") or "")
        if not cid:
            raise CapabilityCaseBankError("case missing case_id")
        if cid in seen:
            raise CapabilityCaseBankError(f"duplicate case_id={cid!r}")
        seen.add(cid)

    if len(rows) < 1:
        raise CapabilityCaseBankError("capability bank is empty")
    return rows


def build_agent_capability_cases() -> List[Dict[str, Any]]:
    """Compat alias: load seed bank (content not defined in Python)."""
    return load_agent_capability_cases()


def _load_profile_file(profile_id: str, *, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    fname = _PROFILE_FILES.get(profile_id)
    if not fname:
        raise CapabilityCaseBankError(f"unknown suite profile_id={profile_id!r}")
    path = root / fname
    raw = _read_json(path)
    if not isinstance(raw, Mapping):
        raise CapabilityCaseBankError(f"{fname} must be an object")
    out = dict(raw)
    out.setdefault("schema", PROFILE_SCHEMA)
    out.setdefault("profile_id", profile_id)
    out.setdefault("pack_id", PACK_ID)
    out.setdefault("pack_version", PACK_VERSION)
    out["claim_eligible"] = False
    return out


def agent_regression_profile() -> Dict[str, Any]:
    """Suite Profile v1 for agent.regression (loaded from seed JSON)."""
    return _load_profile_file(PROFILE_ID)


def agent_smoke_profile() -> Dict[str, Any]:
    """Suite Profile v1 smoke (loaded from seed JSON)."""
    return _load_profile_file(PROFILE_ID_SMOKE)


def agent_benchmark_profile() -> Dict[str, Any]:
    """Suite Profile v1 benchmark (loaded from seed JSON)."""
    return _load_profile_file(PROFILE_ID_BENCHMARK)


def list_suite_profiles() -> List[Dict[str, Any]]:
    """Built-in Suite Profiles (smoke / regression / benchmark)."""
    return [
        agent_smoke_profile(),
        agent_regression_profile(),
        agent_benchmark_profile(),
    ]


def get_suite_profile(profile_id: str) -> Dict[str, Any]:
    """Resolve built-in profile by id (fail closed on unknown)."""
    pid = str(profile_id or "").strip()
    for p in list_suite_profiles():
        if str(p.get("profile_id") or "") == pid:
            return dict(p)
    if not pid or pid == PROFILE_ID:
        return agent_regression_profile()
    raise ValueError(f"unknown suite profile_id={pid!r}")


def validate_capability_case(case: Mapping[str, Any]) -> List[str]:
    """Factory fields + AgentSubjectAdapter purpose/capability checks."""
    errors: List[str] = []
    try:
        validate_case_dict(case)
    except CaseFactoryError as exc:
        errors.append(f"factory:{exc}")
    errors.extend(get_subject_adapter("agent").validate_case(case))
    caps = resolve_capability_ids(list(case.get("capabilities") or []), fail_closed=False)
    for c in caps:
        if c not in V1_IN_SCOPE:
            errors.append(f"out_of_scope_capability:{c}")
    return errors


def validate_agent_capability_bank(
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    rows = list(cases) if cases is not None else build_agent_capability_cases()
    per_case: List[Dict[str, Any]] = []
    bad = 0
    for c in rows:
        errs = validate_capability_case(c)
        if errs:
            bad += 1
        per_case.append(
            {
                "case_id": str(c.get("case_id") or ""),
                "ok": not errs,
                "errors": errs,
            }
        )
    meta = load_pack_meta()
    return {
        "ok": bad == 0,
        "pack_id": str(meta.get("pack_id") or PACK_ID),
        "pack_version": str(meta.get("version") or PACK_VERSION),
        "case_count": len(rows),
        "invalid_count": bad,
        "cases": per_case,
        "claim_eligible": False,
        "review_status": "draft",
        "content_authority": "workspace_seeds/eval/agent_capability/cases",
    }


def build_agent_capability_pack_document() -> Dict[str, Any]:
    """Assemble pack document from meta + loaded cases (for export/promote)."""
    meta = load_pack_meta()
    cases = build_agent_capability_cases()
    return {
        "schema": str(meta.get("schema") or PACK_SCHEMA),
        "pack_id": str(meta.get("pack_id") or PACK_ID),
        "version": str(meta.get("version") or PACK_VERSION),
        "kind": str(meta.get("kind") or "curated"),
        "status": str(meta.get("status") or "draft"),
        "claim_eligible": False,
        "scope": str(meta.get("scope") or "global"),
        "object_types": list(meta.get("object_types") or ["agent"]),
        "cases": cases,
        "profile": agent_regression_profile(),
        "notes": str(
            meta.get("notes")
            or (
                "Assembled from cases/*.json; draft; not claim_eligible; "
                "A3–A5/A8/A9 out of scope"
            )
        ),
    }


def write_agent_capability_seeds(*, seed_dir: Optional[Path] = None) -> Dict[str, str]:
    """Rebuild *derived* combined pack from cases/ + ensure profile files exist.

    Does not invent case content. Edit ``cases/*.json`` then call this to
    refresh ``pack.agent.capability.v*.json`` for review / promote mirrors.
    """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    root.mkdir(parents=True, exist_ok=True)
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise CapabilityCaseBankError(
            f"cannot assemble derived pack: missing {cases_dir} (content authority)"
        )

    pack = build_agent_capability_pack_document()
    pack_path = root / f"pack.{PACK_ID}.v{PACK_VERSION}.json"
    pack_path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Keep profile JSON as authority; rewrite only if missing (bootstrap).
    written: Dict[str, str] = {"pack": str(pack_path)}
    for pid, fname in _PROFILE_FILES.items():
        path = root / fname
        if not path.is_file():
            # Should not happen in repo; fail closed rather than invent quotas.
            raise CapabilityCaseBankError(f"profile seed missing: {path}")
        written[pid] = str(path)

    meta_path = root / "pack.meta.json"
    if not meta_path.is_file():
        raise CapabilityCaseBankError(f"pack.meta.json missing: {meta_path}")
    written["meta"] = str(meta_path)
    return written


def _stamp_purpose_ok(cases: Sequence[Mapping[str, Any]], *, reviewer: str) -> List[Dict[str, Any]]:
    """Stamp mechanical+owner review purpose_ok (claim still closed)."""
    out: List[Dict[str, Any]] = []
    for raw in cases:
        c = dict(raw)
        review = dict(c.get("review") or {})
        review.update(
            {
                "status": "purpose_ok",
                "decision": "purpose_ok",
                "reviewer": str(reviewer or "owner"),
                "notes": "P1 ordered promote: mechanical validate + owner sign-off path",
            }
        )
        c["review"] = review
        out.append(c)
    return out


def promote_agent_capability_bank(
    *,
    workspace_id: str,
    reviewer: str = "",
    frozen_by: str = "",
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Validate seed bank → draft → enqueue → approve → freeze (claim=false).

    Uses workspace registry (same path as Case Pack factory). Does not open
    accuracy_claim. Idempotent if already frozen.
    """
    from core.apps.eval.service.case_factory import publish_draft_workspace_pack
    from core.apps.eval.service.case_freeze import CaseFreezeError, freeze_workspace_pack
    from core.apps.eval.service.case_pack_registry import PackRegistryError, get_pack_version
    from core.apps.eval.service.case_review_queue import (
        CaseReviewError,
        enqueue_pack_for_review,
        submit_review_decision,
    )

    wid = str(workspace_id or "").strip()
    if not wid:
        raise ValueError("workspace_id required")
    pid = str(pack_id or PACK_ID).strip() or PACK_ID
    ver = str(version or PACK_VERSION).strip() or PACK_VERSION
    who = str(reviewer or frozen_by or "owner").strip() or "owner"
    caller = str(caller_workspace_id or wid).strip() or wid

    report = validate_agent_capability_bank()
    if not report.get("ok"):
        raise ValueError(
            f"capability bank invalid: invalid_count={report.get('invalid_count')}"
        )
    cases = _stamp_purpose_ok(build_agent_capability_cases(), reviewer=who)

    # Already frozen? return noop.
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
        )
        if (
            str(cur.get("kind") or "").lower() == "frozen"
            and str(cur.get("status") or "").lower() == "active"
        ):
            return {
                "ok": True,
                "noop": True,
                "pack_id": pid,
                "version": ver,
                "kind": "frozen",
                "status": "active",
                "n_cases": report.get("case_count"),
                "claim_eligible": False,
                "accuracy_claim": False,
                "profile_id": PROFILE_ID,
                "honesty": "already frozen; claim_eligible=false",
            }
    except PackRegistryError:
        # noqa: pack not registered yet — continue to draft publish
        cur = None

    draft = publish_draft_workspace_pack(
        pack_id=pid,
        version=ver,
        cases=cases,
        workspace_id=wid,
        caller_workspace_id=caller,
        object_types=["agent"],
        kind="curated",
    )
    enqueue_pack_for_review(
        pack_id=pid,
        version=ver,
        workspace_id=wid,
        caller_workspace_id=caller,
        notes=str(notes or "P1 capability bank promote"),
    )
    submit_review_decision(
        pack_id=pid,
        version=ver,
        workspace_id=wid,
        decision="approve",
        reviewer=who,
        notes="purpose_ok (ordered P1 closeout)",
        caller_workspace_id=caller,
    )
    try:
        frozen = freeze_workspace_pack(
            pack_id=pid,
            version=ver,
            workspace_id=wid,
            caller_workspace_id=caller,
            frozen_by=str(frozen_by or who),
            notes=str(notes or "P1 agent.capability freeze"),
        )
    except (CaseFreezeError, CaseReviewError) as exc:
        raise ValueError(str(exc)) from exc

    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "kind": frozen.get("kind"),
        "status": frozen.get("status"),
        "pack_hash": frozen.get("pack_hash"),
        "n_cases": frozen.get("n_cases") or len(cases),
        "draft_hash": draft.get("pack_hash"),
        "profile_id": PROFILE_ID,
        "claim_eligible": False,
        "accuracy_claim": False,
        "reviewer": who,
        "honesty": (
            "frozen curated bank from seed cases/*.json; claim_eligible=false; "
            "accuracy_claim closed; purpose_ok stamped before freeze"
        ),
    }
