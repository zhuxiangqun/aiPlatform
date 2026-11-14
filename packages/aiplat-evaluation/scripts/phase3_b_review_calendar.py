#!/usr/bin/env python3
"""Phase 3 prep — Tier B suite + review calendar draft.

Buckets A_candidate/B/C for a draft calendar. Does not authorize Tier A
expansion or claim platform coverage complete.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
TIER = EVID / "tier_matrix_v0.json"
OUT_JSON = META / "phase3_b_review_calendar.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_B_REVIEW_CALENDAR.md"
COV_JSON = META / "phase3_coverage_report_skeleton.v0.json"
COV_MD = ROOT / "docs/a3/PHASE3_COVERAGE_REPORT_SKELETON.md"
PHASE3 = ROOT / "docs/a3/PHASE3_PREP.md"


def _now() -> str:
    """+08:00 timestamp.

    Returns:
        Timestamp string.
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _bucket(sym: str) -> str:
    """Assign a Tier B review bucket.

    Args:
        sym: Symbol name.

    Returns:
        Bucket id.
    """
    s = str(sym)
    if s.endswith("SubjectAdapter") or s.endswith("Adapter"):
        return "B1_subject_adapters"
    if "smoke" in s.lower() or s.endswith("_smoke") or "Smoke" in s:
        return "B2_smoke"
    if "regression" in s.lower() or s.endswith("_profile") or s.endswith("_status"):
        return "B3_regression_profiles"
    if s.startswith("eval_"):
        return "B4_eval_facade"
    if s[0].isupper():
        return "B5_types_errors"
    return "B6_other"


BUCKET_CADENCE = {
    "B1_subject_adapters": {"cadence": "quarterly", "owner_role": "eval_owner"},
    "B2_smoke": {"cadence": "monthly", "owner_role": "eval_owner"},
    "B3_regression_profiles": {"cadence": "monthly", "owner_role": "module_owner"},
    "B4_eval_facade": {"cadence": "quarterly", "owner_role": "platform"},
    "B5_types_errors": {"cadence": "semi_annual", "owner_role": "eval_owner"},
    "B6_other": {"cadence": "semi_annual", "owner_role": "eval_owner"},
}


def main() -> int:
    """Write B calendar + A/B/C coverage skeleton.

    Returns:
        Exit code.
    """
    if not TIER.is_file():
        print("missing tier_matrix", file=sys.stderr)
        return 1
    tier = json.loads(TIER.read_text(encoding="utf-8"))
    tiers = tier.get("tiers") if isinstance(tier.get("tiers"), dict) else {}
    a = list(tiers.get("A_candidate") or [])
    b = list(tiers.get("B") or [])
    c = list(tiers.get("C") or [])
    now = _now()
    META.mkdir(parents=True, exist_ok=True)

    buckets: Dict[str, List[str]] = {k: [] for k in BUCKET_CADENCE}
    for sym in b:
        buckets[_bucket(str(sym))].append(str(sym))

    waves = []
    for bid, meta in BUCKET_CADENCE.items():
        waves.append(
            {
                "bucket_id": bid,
                "cadence": meta["cadence"],
                "owner_role": meta["owner_role"],
                "n": len(buckets[bid]),
                "symbols_sample": buckets[bid][:8],
                "suite_hook": "pending_suite_attach",
                "next_review": "TBD",
            }
        )

    cal = {
        "schema": "eval.phase3.b_review_calendar.v0",
        "recorded_at": now,
        "source": "docs/a3/evidence/tier_matrix_v0.json",
        "tier_b_n": len(b),
        "waves": waves,
        "buckets": {k: {"n": len(v), "symbols": v} for k, v in buckets.items()},
        "tier_a_expansion_authorized": False,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "honesty": (
            "Draft calendar only. Suite hooks pending. "
            "≠ Tier A authorize ≠ coverage complete."
        ),
    }
    OUT_JSON.write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cov = {
        "schema": "eval.phase3.coverage_report_skeleton.v0",
        "recorded_at": now,
        "columns": ["tier", "n", "with_suite", "with_gate", "exempt", "unauthorized_claim"],
        "rows": [
            {
                "tier": "A_candidate",
                "n": len(a),
                "with_suite": None,
                "with_gate": None,
                "exempt": 0,
                "unauthorized_claim": False,
                "note": "META families green; gate authorize false",
            },
            {
                "tier": "B",
                "n": len(b),
                "with_suite": None,
                "with_gate": None,
                "exempt": 0,
                "unauthorized_claim": False,
                "note": "calendar draft only",
            },
            {
                "tier": "C",
                "n": len(c),
                "with_suite": None,
                "with_gate": None,
                "exempt": 0,
                "unauthorized_claim": False,
                "note": "register-only; must not crowd A slots",
            },
        ],
        "forbid_single_coverage_percent": True,
        "tier_a_expansion_authorized": False,
        "accuracy_claim": False,
        "honesty": (
            "Skeleton only — null suite/gate counts until measured. "
            "Never collapse A/B/C into one coverage%."
        ),
    }
    COV_JSON.write_text(json.dumps(cov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    wave_rows = [
        "| bucket | n | cadence | owner_role | suite_hook |",
        "|---|---:|---|---|---|",
    ]
    for w in waves:
        wave_rows.append(
            f"| `{w['bucket_id']}` | {w['n']} | {w['cadence']} | "
            f"{w['owner_role']} | {w['suite_hook']} |"
        )
    OUT_MD.write_text(
        "\n".join(
            [
                "---",
                "doc_type: Reference",
                "---",
                "",
                "# Phase 3 · Tier B 复核日历（草稿）",
                "",
                f"> 机器：[`evidence/meta_eval/phase3_b_review_calendar.v0.json`](./evidence/meta_eval/phase3_b_review_calendar.v0.json) · 时点 {now}",
                f"> Tier B n=**{len(b)}** · **诚实锁**：草稿 ≠ 覆盖完成 ≠ Tier A 授权",
                "",
                "## Waves",
                "",
                *wave_rows,
                "",
                "## 复跑",
                "",
                "```bash",
                "python3 packages/aiplat-evaluation/scripts/phase3_b_review_calendar.py",
                "```",
                "",
                "## 关联",
                "",
                "- [`PHASE3_PREP.md`](./PHASE3_PREP.md)",
                "- [`PHASE3_COVERAGE_REPORT_SKELETON.md`](./PHASE3_COVERAGE_REPORT_SKELETON.md)",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cov_rows = [
        "| tier | n | with_suite | with_gate | exempt | unauthorized_claim |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in cov["rows"]:
        cov_rows.append(
            f"| {r['tier']} | {r['n']} | {r['with_suite']} | {r['with_gate']} | "
            f"{r['exempt']} | {r['unauthorized_claim']} |"
        )
    COV_MD.write_text(
        "\n".join(
            [
                "---",
                "doc_type: Reference",
                "---",
                "",
                "# Phase 3 · 覆盖率报表骨架（A/B/C 分列）",
                "",
                f"> 机器：[`evidence/meta_eval/phase3_coverage_report_skeleton.v0.json`](./evidence/meta_eval/phase3_coverage_report_skeleton.v0.json) · 时点 {now}",
                "> **禁止**单一「覆盖%」；`with_suite`/`with_gate` 现为 null（待实测）",
                "",
                *cov_rows,
                "",
                "## 诚实锁",
                "",
                "- `tier_a_expansion_authorized=false`",
                "- `forbid_single_coverage_percent=true`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if PHASE3.is_file():
        text = PHASE3.read_text(encoding="utf-8")
        text = text.replace(
            "2. B 轨挂 suite + 复核日历草稿  \n"
            "3. 覆盖率报表骨架按 A/B/C 分列（禁止单一覆盖%）  ",
            "2. ✅ B 轨复核日历草稿 → [`PHASE3_B_REVIEW_CALENDAR.md`](./PHASE3_B_REVIEW_CALENDAR.md)  \n"
            "3. ✅ 覆盖率报表骨架 A/B/C → [`PHASE3_COVERAGE_REPORT_SKELETON.md`](./PHASE3_COVERAGE_REPORT_SKELETON.md)  ",
        )
        PHASE3.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "tier_b_n": len(b),
                "waves": {w["bucket_id"]: w["n"] for w in waves},
                "tier_a_expansion_authorized": False,
                "calendar": str(OUT_JSON.relative_to(ROOT)),
                "coverage": str(COV_JSON.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
