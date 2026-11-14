#!/usr/bin/env python3
"""Phase 3 prep — inventory A_candidate symbols (gold/gate/evidence/gaps).

Does not authorize Tier A expansion. Regenerates machine + human inventory.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
TIER = EVID / "tier_matrix_v0.json"
OUT_JSON = META / "phase3_a_candidate_inventory.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_A_CANDIDATE_INVENTORY.md"
PHASE3 = ROOT / "docs/a3/PHASE3_PREP.md"

FAMILY: Dict[str, str] = {
    "assert_t13_process_split_boundary": "F3",
    "build_g2b_s_dual_review_workflow": "F3",
    "eval_assert_t13_process_split_boundary": "F3",
    "build_judge_calib_evidence_pack": "F4",
    "build_release_scorecard": "F4",
    "cohen_kappa_binary": "F1",
    "wilson_score_ci": "F1",
    "evaluate_judge_calibration_gate": "F1",
    "eval_judge_calibration_gate": "F1",
    "open_capability_judge_calibration": "F1",
    "eval_open_capability_judge_calibration": "F1",
    "judge_calibration_gate_for_ticket": "F1",
    "load_judge_calib_defaults": "F2",
    "eval_load_security_judge_calib_defaults": "F2",
    "evaluate_security_family_gates": "F2",
    "eval_evaluate_security_family_gates": "F2",
    "evaluate_security_judge_calibration": "F2",
    "eval_evaluate_security_judge_calibration": "F2",
    "eval_evaluate_security_severity_l5_gate": "F2",
}

EVIDENCE: Dict[str, List[str]] = {
    "F1": [
        "docs/a3/evidence/meta_eval/f1_judge_family_status.v0.json",
        "docs/a3/evidence/meta_eval/f1_judge_ratings.human_judge.v0.json",
        "docs/a3/evidence/g2b_kappa_aggregate.v1.json",
    ],
    "F2": [
        "docs/a3/evidence/meta_eval/f2_security_family_status.v0.json",
        "docs/a3/evidence/meta_eval/f2_security_judge_ratings.human_judge.v0.json",
        "docs/a3/evidence/meta_eval/f2_security_dual_human.worksheet.v0.json",
        "docs/a3/evidence/s1_prod_model_aggregate.v1.json",
    ],
    "F3": [
        "docs/a3/evidence/meta_eval/f3_process_split_boundary_status.v0.json",
        "docs/a3/evidence/meta_eval/f3_process_split_boundary_pin.v0.json",
        "docs/a3/SPLIT_CHECKLIST.md",
    ],
    "F4": [
        "docs/a3/evidence/meta_eval/f4_release_scorecard_status.v0.json",
        "docs/a3/scorecard_v1.json",
        "docs/a3/evidence/evidence_manifest.v1.json",
    ],
}

GAPS: Dict[str, str] = {
    "F1": "Tier A gate authorize still false; product accuracy_claim remains false",
    "F2": "family_green ≠ L5 declare / security_certification",
    "F3": "family_green ≠ process_split_authorized flip",
    "F4": "unscored scorecard axes remain holdout-from-claim",
}


def _now() -> str:
    """+08:00 timestamp.

    Returns:
        Timestamp string.
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def find_defs(sym: str) -> List[str]:
    """Find def line sites for a symbol.

    Args:
        sym: Symbol name.

    Returns:
        List of path:line hits.
    """
    hits: List[str] = []
    for base in [str(REPO / "aiPlat-core"), str(ROOT)]:
        try:
            out = subprocess.check_output(
                [
                    "rg",
                    "-n",
                    rf"^(def|async def) {re.escape(sym)}\b",
                    base,
                    "-g",
                    "*.py",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            out = ""
        for line in out.strip().splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                rel = parts[0]
                try:
                    rel = str(Path(parts[0]).resolve().relative_to(REPO))
                except ValueError:
                    rel = parts[0]
                hits.append(f"{rel}:{parts[1]}")
    return hits


def main() -> int:
    """Write inventory JSON + MD and refresh PHASE3_PREP pointer.

    Returns:
        Exit code.
    """
    if not TIER.is_file():
        print("missing tier_matrix_v0.json", file=sys.stderr)
        return 1
    tier = json.loads(TIER.read_text(encoding="utf-8"))
    syms = list((tier.get("tiers") or {}).get("A_candidate") or [])
    if not syms:
        print("empty A_candidate", file=sys.stderr)
        return 1

    META.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for s in syms:
        fam = FAMILY.get(str(s), "unknown")
        defs = find_defs(str(s))
        impl = next((h for h in defs if "/api/core_facade.py" not in h), None)
        if impl is None and defs:
            impl = defs[0]
        facade = next((h for h in defs if "/api/core_facade.py" in h), None)
        rows.append(
            {
                "symbol": s,
                "kind": "facade_wrapper" if str(s).startswith("eval_") else "impl",
                "meta_family": fam,
                "impl_def": impl,
                "facade_def": facade,
                "evidence_refs": EVIDENCE.get(fam, []),
                "meta_family_green": True,
                "tier_a_gate_authorized": False,
                "gap": GAPS.get(fam, "unmapped family"),
            }
        )

    now = _now()
    out = {
        "schema": "eval.phase3.a_candidate_inventory.v0",
        "recorded_at": now,
        "source": "docs/a3/evidence/tier_matrix_v0.json tiers.A_candidate",
        "n": len(rows),
        "tier_a_expansion_authorized": False,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "security_certification": False,
        "l5_declare_authorized": False,
        "items": rows,
        "honesty": (
            "Inventory only. meta_eval family_green is prerequisite; "
            "tier_a_expansion_authorized remains false. ≠ coverage complete."
        ),
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by: Dict[str, int] = {}
    for r in rows:
        by[str(r["meta_family"])] = by.get(str(r["meta_family"]), 0) + 1

    table = [
        "| 符号 | 家族 | kind | impl | Tier A authorize |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        table.append(
            f"| `{r['symbol']}` | {r['meta_family']} | {r['kind']} | "
            f"`{r.get('impl_def') or 'MISSING'}` | **false** |"
        )
    md = "\n".join(
        [
            "---",
            "doc_type: Reference",
            "---",
            "",
            "# Phase 3 · A_candidate 清单（工程预备）",
            "",
            f"> 机器：[`evidence/meta_eval/phase3_a_candidate_inventory.v0.json`](./evidence/meta_eval/phase3_a_candidate_inventory.v0.json) · 时点 {now}",
            "> **诚实锁**：本表 ≠ Tier A 扩容授权 · `tier_a_expansion_authorized=false`",
            "",
            "## 汇总",
            "",
            f"- n=**{len(rows)}** · by_family={by}",
            "- 全部 `meta_family_green=true`（见 [`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)）",
            "- 全部 `tier_a_gate_authorized=false`",
            "",
            "## 明细",
            "",
            *table,
            "",
            "## 复跑",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_a_candidate_inventory.py",
            "```",
            "",
            "## 关联",
            "",
            "- [`PHASE3_PREP.md`](./PHASE3_PREP.md)",
            "- [`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md)",
            "",
        ]
    )
    OUT_MD.write_text(md + "\n", encoding="utf-8")

    # Ensure PHASE3_PREP points at inventory (idempotent replace/insert).
    if PHASE3.is_file():
        text = PHASE3.read_text(encoding="utf-8")
        pointer = (
            "完整 19 个符号工程清单见 "
            "[`PHASE3_A_CANDIDATE_INVENTORY.md`](./PHASE3_A_CANDIDATE_INVENTORY.md) · "
            "[`evidence/meta_eval/phase3_a_candidate_inventory.v0.json`]"
            "(./evidence/meta_eval/phase3_a_candidate_inventory.v0.json)。"
        )
        old = (
            "完整 19 个符号见 [`evidence/tier_matrix_v0.json`]"
            "(./evidence/tier_matrix_v0.json) `tiers.A_candidate`。"
        )
        if pointer not in text:
            if old in text:
                text = text.replace(old, pointer)
            else:
                text = text.rstrip() + "\n\n" + pointer + "\n"
            PHASE3.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "n": len(rows),
                "by_family": by,
                "tier_a_expansion_authorized": False,
                "out": str(OUT_JSON.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
