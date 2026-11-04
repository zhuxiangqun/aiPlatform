"""EVAL preference pack status (facilitation) — never flips accuracy_claim.

Reads preference_pairs.v0.json + optional preference_aggregate under
packages/aiplat-evaluation/docs/a3/. UI/API only report facts; agreement/κ ≠ accuracy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _repo_root() -> Path:
    # aiPlat-core/core/apps/eval/service/preference.py → workspace root
    return Path(__file__).resolve().parents[5]


def _pairs_path() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "preference_pairs.v0.json"
    )


def _evidence_dir() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "evidence"
    )


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def preference_pack_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Facilitator-facing preference pack readiness (not an accuracy claim)."""
    pairs_path = _pairs_path()
    pack = _read_json(pairs_path) or {}
    pairs = pack.get("pairs") if isinstance(pack.get("pairs"), list) else []
    pairs_n = len(pairs)

    agg_path = _evidence_dir() / "preference_aggregate.v1.json"
    agg = _read_json(agg_path) or {}
    a = agg.get("annotator_a") if isinstance(agg.get("annotator_a"), dict) else {}
    b = agg.get("annotator_b") if isinstance(agg.get("annotator_b"), dict) else {}
    inter = (
        agg.get("inter_annotator")
        if isinstance(agg.get("inter_annotator"), dict)
        else {}
    )

    labeled_a = int(a.get("labeled_n") or 0) if isinstance(a.get("labeled_n"), (int, float)) else 0
    labeled_b = int(b.get("labeled_n") or 0) if isinstance(b.get("labeled_n"), (int, float)) else 0
    target = pairs_n or int(agg.get("pairs_n") or 0)
    pending_a = max(0, target - labeled_a) if target else 0
    pending_b = max(0, target - labeled_b) if target else 0
    dual_complete = (
        target > 0
        and labeled_a >= target
        and labeled_b >= target
        and bool(inter)
    )
    honesty = str(agg.get("honesty") or "")
    fixture_solo = "fixture" in honesty.lower() or (
        labeled_a >= target > 0 and labeled_b == 0
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "schema": str(pack.get("schema") or "eval.preference.pairs.v0"),
        "pairs_path": str(pairs_path) if pairs_path.is_file() else None,
        "pairs_n": pairs_n,
        "pack_ready": pairs_n >= 30,
        "labeled_a": labeled_a,
        "labeled_b": labeled_b,
        "pending_a": pending_a,
        "pending_b": pending_b,
        "dual_human_complete": dual_complete,
        "fixture_solo": fixture_solo,
        "agreement": inter.get("agreement"),
        "preference_kappa": inter.get("preference_kappa"),
        "kappa_kind": inter.get("kappa_kind") or "preference_pairwise",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "note": (
            "Preference pack status is facilitation-only. "
            "Agreement/κ ≠ accuracy; fixture solo ≠ human κ; "
            "accuracy_claim stays false."
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/PREFERENCE_V0.md",
        "aggregate_path": str(agg_path) if agg_path.is_file() else None,
    }
