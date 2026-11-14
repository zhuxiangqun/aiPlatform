"""Code Review 能力 Case Bank：策展种子（draft，claim=false）。

职责
----
从 ``workspace_seeds/eval/code_review_capability/`` 加载 pack/cases/profile，
经 CodeReviewSubjectAdapter 校验/smoke。

非目标
------
- 不做 live host 准确性宣称
- 不开放 claim / certification
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.apps.eval.service.capability_id_map import (
    resolve_capability_id,
    resolve_capability_ids,
)
from core.apps.eval.service.subject_adapter import (
    CODE_REVIEW_V1_CAPS,
    get_subject_adapter,
)

PACK_SCHEMA = "eval.case_pack.v1"
PACK_ID = "code_review.capability"
PACK_VERSION = "0.2.0"
PROFILE_ID_SMOKE = "code_review.smoke.v1"
PROFILE_ID_REGRESSION = "code_review.regression.v1"
_PURPOSE_OK = frozenset({"purpose_ok", "reviewed", "approved", "frozen"})


class CodeReviewCapabilityBankError(ValueError):
    """Seed bank load / validate failure (fail closed)."""


def default_seed_dir() -> Path:
    """返回本 Case Bank 默认种子目录路径。"""
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "code_review_capability"
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CodeReviewCapabilityBankError(f"seed missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CodeReviewCapabilityBankError(f"seed JSON invalid: {path}: {exc}") from exc


def load_pack_meta(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """读取并返回 ``pack.meta.json``。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta = _read_json(root / "pack.meta.json")
    if not isinstance(meta, Mapping):
        raise CodeReviewCapabilityBankError("pack.meta.json must be an object")
    return dict(meta)


def build_code_review_capability_cases(
    *, seed_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """加载并规范化全部 code_review capability case。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise CodeReviewCapabilityBankError(f"cases dir missing: {cases_dir}")
    out: List[Dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        raw = _read_json(path)
        if not isinstance(raw, list):
            raise CodeReviewCapabilityBankError(f"cases file must be a list: {path}")
        for row in raw:
            if not isinstance(row, Mapping):
                raise CodeReviewCapabilityBankError(f"case must be object in {path}")
            case = dict(row)
            case["capabilities"] = resolve_capability_ids(
                list(case.get("capabilities") or []), fail_closed=True
            )
            case.setdefault("applies_to", {"subject_kinds": ["code_review"]})
            case.setdefault("pack", PACK_ID)
            out.append(case)
    return out


def validate_code_review_capability_bank(
    *, seed_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """校验 pack 元数据与全部 case（经 SubjectAdapter）。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta = load_pack_meta(seed_dir=root)
    adapter = get_subject_adapter("code_review")
    cases = build_code_review_capability_cases(seed_dir=root)
    errors: List[str] = []
    if str(meta.get("pack_id") or "") != PACK_ID:
        errors.append(f"pack_id_mismatch:{meta.get('pack_id')}")
    if meta.get("claim_eligible") is not False:
        errors.append("claim_eligible_must_be_false")
    subjects = list(meta.get("subject_kinds") or meta.get("object_types") or [])
    if "code_review" not in subjects:
        errors.append("subject_kinds_missing_code_review")
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


def code_review_smoke_profile(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """加载 smoke 评测 profile，并强制 ``claim_eligible=False``。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    raw = _read_json(root / "profile.code_review.smoke.v1.json")
    if not isinstance(raw, Mapping):
        raise CodeReviewCapabilityBankError("smoke profile must be an object")
    out = dict(raw)
    out["claim_eligible"] = False
    return out


def code_review_regression_profile(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    """加载回归 profile，校验 ``profile_id`` 与 ``quotas``。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    path = root / "profile.code_review.regression.v1.json"
    raw = _read_json(path)
    if not isinstance(raw, Mapping):
        raise CodeReviewCapabilityBankError("regression profile must be an object")
    out = dict(raw)
    out["claim_eligible"] = False
    if str(out.get("profile_id") or "") != PROFILE_ID_REGRESSION:
        raise CodeReviewCapabilityBankError(
            f"profile_id_mismatch:{out.get('profile_id')}"
        )
    quotas = out.get("quotas") if isinstance(out.get("quotas"), Mapping) else {}
    if not quotas:
        raise CodeReviewCapabilityBankError("regression profile.quotas required")
    return out


def code_review_regression_status(
    *,
    seed_dir: Optional[Path] = None,
    draft_sample_limit: int = 5,
) -> Dict[str, Any]:
    """诚实快照：回归配额与库存计数对比（claim 保持 false）。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
            draft_sample_limit: 每个 capability 最多收录的 draft case_id 样本数。
        """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    meta = load_pack_meta(seed_dir=root)
    profile = code_review_regression_profile(seed_dir=root)
    cases = build_code_review_capability_cases(seed_dir=root)
    quotas_raw = profile.get("quotas") if isinstance(profile.get("quotas"), Mapping) else {}
    quotas: Dict[str, int] = {}
    for k, v in quotas_raw.items():
        cid = resolve_capability_id(str(k), fail_closed=True)
        quotas[cid] = int(v)

    counts: Counter = Counter()
    review_counts: Counter = Counter()
    draft_by_cap: Dict[str, List[str]] = defaultdict(list)
    draft_counts: Counter = Counter()
    sample_lim = max(0, int(draft_sample_limit or 0))
    for c in cases:
        caps = list(c.get("capabilities") or [])
        try:
            cap = resolve_capability_id(str(caps[0]), fail_closed=True) if caps else ""
        except Exception:
            cap = str(caps[0]).strip() if caps else ""
        if not cap:
            cap = "(unknown)"
        counts[cap] += 1
        rev = c.get("review") if isinstance(c.get("review"), dict) else {}
        st = str((rev or {}).get("status") or "draft").strip().lower() or "draft"
        review_counts[st] += 1
        if st not in _PURPOSE_OK:
            draft_counts[cap] += 1
            cid = str(c.get("case_id") or "")
            if cid and len(draft_by_cap[cap]) < sample_lim:
                draft_by_cap[cap].append(cid)

    gaps: List[Dict[str, Any]] = []
    for cap, need in sorted(quotas.items()):
        have = int(counts.get(cap, 0))
        if have < need:
            gaps.append({"capability_id": cap, "quota": need, "have": have})
    missing_caps = sorted(set(CODE_REVIEW_V1_CAPS) - set(quotas.keys()))
    purpose_ok_n = (
        int(review_counts.get("purpose_ok", 0))
        + int(review_counts.get("reviewed", 0))
        + int(review_counts.get("approved", 0))
        + int(review_counts.get("frozen", 0))
    )
    draft_checklist = [
        {
            "capability_id": cap,
            "draft_count": int(draft_counts[cap]),
            "sample_case_ids": list(draft_by_cap.get(cap) or []),
        }
        for cap in sorted(draft_counts.keys())
    ]
    quota_ok = not gaps and not missing_caps
    pack_frozen = str(meta.get("status") or "").strip().lower() == "frozen"
    profile_complete = bool(quota_ok and purpose_ok_n == len(cases) and pack_frozen)
    return {
        "schema": "eval.code_review_regression_status.v1",
        "ok": True,
        "profile_id": PROFILE_ID_REGRESSION,
        "pack_id": PACK_ID,
        "pack_version": str(meta.get("version") or PACK_VERSION),
        "pack_status": str(meta.get("status") or "draft"),
        "quota_inventory_ok": quota_ok,
        "profile_complete": profile_complete,
        "case_count": len(cases),
        "quotas": quotas,
        "counts_by_capability": dict(sorted(counts.items())),
        "gaps": gaps,
        "missing_profile_capabilities": missing_caps,
        "review_status_counts": dict(sorted(review_counts.items())),
        "purpose_ok_or_better": purpose_ok_n,
        "draft_pending": int(sum(draft_counts.values())),
        "draft_by_capability": draft_checklist,
        "next_action": (
            "claim/Certification remain closed; workspace promote optional"
            if profile_complete
            else (
            "Expand/review code_review.capability cases → human purpose_ok/freeze; "
            "fixture gold set ≠ live autoreview accuracy"
            )
        ),
        "review_links": {
            "case_packs_tab": "/eval?tab=case-packs",
            "typed_plan_tab": "/eval?tab=typed-plan",
            "tool_regression_tab": "/eval?tab=tool-regression",
        },
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "Code Review regression quotas are inventory-only; "
            + ("seed pack.meta frozen + purpose_ok; " if pack_frozen else "human purpose_ok/freeze still required for profile_complete; ") +
            "fixture findings/gold ≠ live autoreview; claim/cert stay false."
        ),
    }


def run_code_review_capability_smoke(
    *, seed_dir: Optional[Path] = None, limit: int = 20
) -> Dict[str, Any]:
    """跑 code_review capability smoke（fixture）；永不解锁 claim。

        Args:
            seed_dir: 种子根目录；``None`` 时用 ``default_seed_dir()``。
        """
    adapter = get_subject_adapter("code_review")
    cases = build_code_review_capability_cases(seed_dir=seed_dir)[: max(0, int(limit))]
    rows: List[Dict[str, Any]] = []
    passed = 0
    for case in cases:
        result = adapter.execute(case)
        judgment = adapter.judge(case, result)
        normalized = adapter.normalize(case, result, judgment)
        ok = bool(normalized.get("passed"))
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
            "Fixture code_review_gold-style smoke ≠ live autoreview E2E ≠ accuracy."
        ),
    }
