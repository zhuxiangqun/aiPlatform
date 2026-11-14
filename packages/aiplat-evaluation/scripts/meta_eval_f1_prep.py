#!/usr/bin/env python3
"""META_EVAL F1 prep — holdout declaration, contamination scan, gold sample, judge pack pin.

Does not invent judge↔human agreement/ECE. Does not authorize Tier A.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
TASKS = ROOT / "docs/a3/g2b_tasks.v0.json"
GOLD = EVID / "g2b_adjudicated_gold.v1.json"
PREF = ROOT / "docs/a3/fixtures/calibration/pref_annotator_a.v0.json"
FREEZE = EVID / "g2b_freeze_record.v1.json"


def _sha256(path: Path) -> str:
    """File sha256 hex.

    Args:
        path: File path.

    Returns:
        Hex digest.
    """
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _now() -> str:
    """Local +08:00 timestamp.

    Returns:
        ISO-like timestamp string.
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _tokens(text: str) -> Set[str]:
    """Lowercase alphanumeric tokens length≥3.

    Args:
        text: Raw text.

    Returns:
        Token set.
    """
    return {t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]{3,}", text.lower())}


def write_holdout() -> Path:
    """Declare F1/G2b-linked holdout isolation rules (on the books).

    Returns:
        Output path.
    """
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    ids = [str(t.get("id")) for t in (tasks.get("tasks") or []) if t.get("id")]
    # Deterministic split by sorted id: 70% dev / 15% val / 15% holdout
    ordered = sorted(ids)
    n = len(ordered)
    n_dev = int(n * 0.70)
    n_val = int(n * 0.15)
    split = {
        "dev": ordered[:n_dev],
        "val": ordered[n_dev : n_dev + n_val],
        "holdout": ordered[n_dev + n_val :],
    }
    out = {
        "schema": "eval.meta_eval.f1_holdout_isolation.v0",
        "family_id": "F1",
        "recorded_at": _now(),
        "pack": "g2b_tasks.v0",
        "pack_sha256": _sha256(TASKS),
        "policy": {
            "splits": ["dev", "val", "holdout"],
            "ratios_forbidden_on_holdout": True,
            "ci_runs": ["dev", "val"],
            "reveal": "pre_release_once",
            "ratio": {"dev": 0.70, "val": 0.15, "holdout": 0.15},
        },
        "counts": {k: len(v) for k, v in split.items()},
        "holdout_task_ids": split["holdout"],
        "freeze_ref": "docs/a3/evidence/g2b_freeze_record.v1.json",
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Rules declared for META_EVAL holdout isolation. "
            "Holdout not revealed for scoring. ≠ Tier A authorize."
        ),
    }
    path = META / "f1_holdout_isolation.v0.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_contamination() -> Path:
    """Token-overlap advisory between G2b prompts and preference fixture.

    Returns:
        Output path.
    """
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    pref_text = PREF.read_text(encoding="utf-8") if PREF.is_file() else ""
    pref_tok = _tokens(pref_text)
    overlaps: List[Dict[str, Any]] = []
    for t in tasks.get("tasks") or []:
        tid = str(t.get("id") or "")
        blob = f"{t.get('prompt') or ''} {t.get('rubric') or ''}"
        tok = _tokens(blob)
        inter = sorted(tok & pref_tok)
        # Ignore ultra-common short noise already filtered by len≥3; still cap report
        if len(inter) >= 8:
            overlaps.append(
                {
                    "task_id": tid,
                    "overlap_n": len(inter),
                    "sample_tokens": inter[:12],
                }
            )
    overlaps.sort(key=lambda r: -int(r["overlap_n"]))
    # Advisory threshold: many heavy overlaps → advisory flag (never hard fail)
    advisory = len(overlaps) > 10
    out = {
        "schema": "eval.meta_eval.f1_contamination.v0",
        "family_id": "F1",
        "recorded_at": _now(),
        "method": "token_overlap_vs_preference_fixture",
        "sources": {
            "tasks": "docs/a3/g2b_tasks.v0.json",
            "tasks_sha256": _sha256(TASKS),
            "contrast": "docs/a3/fixtures/calibration/pref_annotator_a.v0.json",
            "contrast_sha256": _sha256(PREF) if PREF.is_file() else None,
        },
        "heavy_overlap_tasks_n": len(overlaps),
        "heavy_overlap_sample": overlaps[:20],
        "over_threshold": advisory,
        "disposition": "advisory_only" if advisory else "clear_advisory",
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Contamination scan ran (heuristic token overlap). "
            "R11: over-threshold → advisory only; not Tier A hard block claim."
        ),
    }
    path = META / "f1_contamination.v0.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_gold_sample() -> Path:
    """Seeded gold re-audit sample worksheet (pending human).

    Returns:
        Output path.
    """
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    labels = list(gold.get("labels") or [])
    seed = 20261114
    rng = random.Random(seed)
    sample_n = min(20, len(labels))
    sample = rng.sample(labels, sample_n) if labels else []
    out = {
        "schema": "eval.meta_eval.f1_gold_audit_sample.v0",
        "family_id": "F1",
        "recorded_at": _now(),
        "seed": seed,
        "sample_n": sample_n,
        "population_n": len(labels),
        "gold_source": "docs/a3/evidence/g2b_adjudicated_gold.v1.json",
        "gold_sha256": _sha256(GOLD),
        "threshold_sample_error_rate_max": 0.05,
        "sample": [
            {
                "task_id": row.get("task_id"),
                "gold_pass": row.get("gold_pass"),
                "reaudit_pass": None,
                "reaudit_ok": None,
            }
            for row in sample
        ],
        "status": "pending_human_reaudit",
        "sample_error_rate": None,
        "green": False,
        "accuracy_claim": False,
        "honesty": (
            "Sample drawn; human re-audit of gold required before green. "
            "Do not fill reaudit_* automatically."
        ),
    }
    path = META / "f1_gold_audit_sample.v0.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_judge_pack_pin() -> Path:
    """Pin judge-calibration pack fingerprint; ratings still empty.

    Returns:
        Output path.
    """
    freeze = (
        json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.is_file() else {}
    )
    out = {
        "schema": "eval.meta_eval.f1_judge_pack_pin.v0",
        "family_id": "F1",
        "recorded_at": _now(),
        "pack": "g2b_tasks.v0",
        "pack_sha256": _sha256(TASKS),
        "seed": 20261114,
        "freeze_ref": "docs/a3/evidence/g2b_freeze_record.v1.json",
        "freeze_status": freeze.get("status"),
        "api_hooks": [
            "open_capability_judge_calibration",
            "evaluate_judge_calibration_gate",
            "cohen_kappa_binary",
        ],
        "ratings_path": None,
        "agreement": None,
        "kappa": None,
        "ece": None,
        "status": "pending_ratings",
        "green": False,
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Pack pinned. Fill ratings then compute agreement/κ/ECE; "
            "do not reuse G2b IAA as judge calibration."
        ),
    }
    path = META / "f1_judge_pack_pin.v0.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    """Generate F1 prep artifacts under evidence/meta_eval/.

    Returns:
        0 on success.
    """
    META.mkdir(parents=True, exist_ok=True)
    if not TASKS.is_file() or not GOLD.is_file():
        print("missing g2b tasks or gold", file=sys.stderr)
        return 1
    paths = [
        write_holdout(),
        write_contamination(),
        write_gold_sample(),
        write_judge_pack_pin(),
    ]
    print(
        json.dumps(
            {
                "ok": True,
                "wrote": [str(p.relative_to(ROOT)) for p in paths],
                "accuracy_claim": False,
                "tier_a_claim_authorized": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
