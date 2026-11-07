"""EVAL scorecard honesty status — never flips accuracy_claim / authorize.

Reads packages/aiplat-evaluation/docs/a3/scorecard_v1.json + evidence_manifest.
UI/API only report declared axes and attestation facts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _a3_dir() -> Path:
    return _repo_root() / "packages" / "aiplat-evaluation" / "docs" / "a3"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _axis_summary(axes: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for axis_id, raw in axes.items():
        if not isinstance(raw, dict):
            continue
        gaps = raw.get("gaps") if isinstance(raw.get("gaps"), list) else []
        out.append(
            {
                "id": axis_id,
                "score": raw.get("score"),
                "max": raw.get("max"),
                "full_score_eligible": bool(raw.get("full_score_eligible")),
                "gaps_n": len(gaps),
                "gaps": [str(g) for g in gaps[:8]],
            }
        )
    return out


def scorecard_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Facilitator-facing scorecard honesty snapshot (not an accuracy claim)."""
    sc_path = _a3_dir() / "scorecard_v1.json"
    man_path = _a3_dir() / "evidence" / "evidence_manifest.v1.json"
    sc = _read_json(sc_path) or {}
    man = _read_json(man_path) or {}
    axes = sc.get("axes") if isinstance(sc.get("axes"), dict) else {}
    dims = sc.get("dimensions") if isinstance(sc.get("dimensions"), list) else []
    attest = (
        man.get("dual_human_attestation")
        if isinstance(man.get("dual_human_attestation"), dict)
        else {}
    )
    method = man.get("method") if isinstance(man.get("method"), dict) else {}
    g2b_acc = method.get("g2b_accuracy") if isinstance(method.get("g2b_accuracy"), dict) else {}

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "schema": str(sc.get("schema") or "eval.scorecard.v1"),
        "scorecard_path": str(sc_path) if sc_path.is_file() else None,
        "manifest_path": str(man_path) if man_path.is_file() else None,
        "recorded_at": sc.get("recorded_at"),
        "accuracy_claim": False,
        "process_split_authorized": False,
        "not_production_authorization": True,
        "dual_human_attestation": str(attest.get("status") or "unknown"),
        "axes": _axis_summary(axes),
        "dimensions_n": len(dims),
        "dimensions_evidence_ok": sum(
            1 for d in dims if isinstance(d, dict) and d.get("evidence_ok")
        ),
        "g2b_closeout_n": g2b_acc.get("n"),
        "g2b_target_n": g2b_acc.get("target_n"),
        "g2b_pass_rate": g2b_acc.get("pass_rate"),
        "honesty": str(
            sc.get("honesty")
            or "Scores relative to SCORE_SCOPE_V1 only; accuracy_claim=false."
        ),
        "note": (
            "Scorecard status is honesty/facilitation-only. "
            "Feature 5 ≠ accuracy; local 5 ≠ process_split_authorized; "
            "G2b n=100 closeout recorded; pass_rate below protocol → accuracy_claim=false."
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/SCORECARD_V1.md",
    }
