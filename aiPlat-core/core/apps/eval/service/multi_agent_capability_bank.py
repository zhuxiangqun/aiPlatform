"""Multi-Agent capability Case Bank — curated seeds (draft, claim=false).

Mirrors tool/session_capability layout under workspace_seeds/eval/multi_agent_capability/.
Validation / smoke go through MultiAgentSubjectAdapter; oracle is fixture handoff
path (+ optional final). Live multi_agent runtime stays M2 deferred.
Not first-class OBJECT_TYPES.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.apps.eval.service.capability_id_map import resolve_capability_ids
from core.apps.eval.service.subject_adapter import get_subject_adapter

PACK_SCHEMA = "eval.case_pack.v1"
PACK_ID = "multi_agent.capability"
PACK_VERSION = "0.1.0"
PROFILE_ID_SMOKE = "multi_agent.smoke.v1"


class MultiAgentCapabilityBankError(ValueError):
    """Seed bank load / validate failure (fail closed)."""


def default_seed_dir() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "multi_agent_capability"
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MultiAgentCapabilityBankError(f"seed missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MultiAgentCapabilityBankError(f"seed JSON invalid: {path}: {exc}") from exc


def load_pack_meta(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta = _read_json(root / "pack.meta.json")
    if not isinstance(meta, Mapping):
        raise MultiAgentCapabilityBankError("pack.meta.json must be an object")
    return dict(meta)


def build_multi_agent_capability_cases(
    *, seed_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise MultiAgentCapabilityBankError(f"cases dir missing: {cases_dir}")
    out: List[Dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        raw = _read_json(path)
        if not isinstance(raw, list):
            raise MultiAgentCapabilityBankError(f"cases file must be a list: {path}")
        for row in raw:
            if not isinstance(row, Mapping):
                raise MultiAgentCapabilityBankError(f"case must be object in {path}")
            case = dict(row)
            case["capabilities"] = resolve_capability_ids(
                list(case.get("capabilities") or []), fail_closed=True
            )
            case.setdefault("applies_to", {"subject_kinds": ["multi_agent"]})
            case.setdefault("pack", PACK_ID)
            out.append(case)
    return out


def validate_multi_agent_capability_bank(
    *, seed_dir: Optional[Path] = None
) -> Dict[str, Any]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta = load_pack_meta(seed_dir=root)
    adapter = get_subject_adapter("multi_agent")
    cases = build_multi_agent_capability_cases(seed_dir=root)
    errors: List[str] = []
    if str(meta.get("pack_id") or "") != PACK_ID:
        errors.append(f"pack_id_mismatch:{meta.get('pack_id')}")
    if meta.get("claim_eligible") is not False:
        errors.append("claim_eligible_must_be_false")
    subjects = list(meta.get("subject_kinds") or meta.get("object_types") or [])
    if "multi_agent" not in subjects:
        errors.append("subject_kinds_missing_multi_agent")
    for case in cases:
        for e in adapter.validate_case(case):
            errors.append(f"{case.get('case_id')}:{e}")
    return {
        "ok": not errors,
        "pack_id": PACK_ID,
        "version": str(meta.get("version") or PACK_VERSION),
        "case_count": len(cases),
        "errors": errors,
        "claim_eligible": False,
        "security_certification": False,
        "seed_dir": str(root),
    }


def multi_agent_smoke_profile(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    raw = _read_json(root / "profile.multi_agent.smoke.v1.json")
    if not isinstance(raw, Mapping):
        raise MultiAgentCapabilityBankError("smoke profile must be an object")
    out = dict(raw)
    out["claim_eligible"] = False
    return out


def run_multi_agent_capability_smoke(
    *, seed_dir: Optional[Path] = None, limit: int = 20
) -> Dict[str, Any]:
    adapter = get_subject_adapter("multi_agent")
    cases = build_multi_agent_capability_cases(seed_dir=seed_dir)[: max(0, int(limit))]
    rows: List[Dict[str, Any]] = []
    passed = 0
    for case in cases:
        result = adapter.execute(case)
        judgment = adapter.judge(case, result)
        normalized = adapter.normalize(case, result, judgment)
        ok = bool(normalized.get("passed")) and str(result.get("status")) == "ok"
        if ok:
            passed += 1
        rows.append(
            {
                "case_id": case.get("case_id"),
                "passed": ok,
                "errors": normalized.get("errors") or [],
                "claim_eligible": False,
            }
        )
    return {
        "ok": passed == len(cases) and len(cases) > 0,
        "passed": passed,
        "total": len(cases),
        "rows": rows,
        "claim_eligible": False,
        "security_certification": False,
        "honesty": (
            "Fixture handoff-path smoke ≠ live multi_agent runtime (M2 deferred) ≠ accuracy."
        ),
    }
