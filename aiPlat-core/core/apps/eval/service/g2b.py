"""EVAL G2b pack status (facilitation) — never flips accuracy_claim.

Reads committed task pack + optional evidence aggregates under
packages/aiplat-evaluation/docs/a3/. Dual-human labels for 31–100 stay pending
until humans return sheets; UI/API only report facts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _repo_root() -> Path:
    # aiPlat-core/core/apps/eval/service/g2b.py → workspace root
    return Path(__file__).resolve().parents[5]


def _pack_path() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "g2b_tasks.v0.json"
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


def g2b_pack_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Facilitator-facing pack readiness (local files; not an accuracy claim)."""
    pack_path = _pack_path()
    pack = _read_json(pack_path) or {}
    tasks = pack.get("tasks") if isinstance(pack.get("tasks"), list) else []
    target_n = int(pack.get("target_n") or 0) or len(tasks)
    task_n = len(tasks)

    ev = _evidence_dir()
    kappa = _read_json(ev / "g2b_kappa_aggregate.v1.json") or {}
    acc = _read_json(ev / "g2b_accuracy_aggregate.v1.json") or {}

    kappa_n = len(kappa.get("task_ids") or []) if isinstance(kappa.get("task_ids"), list) else 0
    if not kappa_n and isinstance(kappa.get("n"), (int, float)):
        kappa_n = int(kappa["n"])
    acc_n = int(acc.get("n") or 0) if isinstance(acc.get("n"), (int, float)) else 0

    closeout_n = max(kappa_n, acc_n)
    pending_dual = max(0, target_n - closeout_n)
    pack_ready = task_n >= target_n and target_n > 0
    dual_human_complete = pending_dual == 0 and closeout_n >= target_n

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "schema": str(pack.get("schema") or "eval.g2b.task_pack.v0"),
        "pack_path": str(pack_path) if pack_path.is_file() else None,
        "task_count": task_n,
        "target_n": target_n,
        "pack_ready": pack_ready,
        "closeout_n": closeout_n,
        "kappa_n": kappa_n,
        "accuracy_aggregate_n": acc_n,
        "pending_dual_human": pending_dual,
        "dual_human_complete": dual_human_complete,
        "kappa_kind": kappa.get("kappa_kind") or "inter_annotator",
        "kappa": kappa.get("kappa"),
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "note": (
            "G2b pack status is facilitation-only. Pack n=100 ≠ closeout; "
            "dual-human labels for unfinished ids still required; "
            "accuracy_claim stays false until attestation."
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/G2B_N100.md",
        "families": _family_counts(tasks),
    }


def _family_counts(tasks: list) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        fam = str(t.get("family") or "unknown")
        out[fam] = out.get(fam, 0) + 1
    return out
