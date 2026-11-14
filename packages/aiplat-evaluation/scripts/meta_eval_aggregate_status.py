#!/usr/bin/env python3
"""META_EVAL aggregate status — F1–F4 family rollup.

Reports families_green only. Never authorizes Tier A expansion, L5 declare,
security certification, process_split, or product accuracy_claim.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
OUT_JSON = META / "meta_eval_aggregate_status.v0.json"
OUT_MD = ROOT / "docs/a3/META_EVAL_STATUS.md"
TIER_JSON = ROOT / "docs/a3/evidence/tier_matrix_v0.json"
TIER_MD = ROOT / "docs/a3/TIER_MATRIX_V0.md"

FAMILIES = [
    ("F1", "f1_judge_family_status.v0.json", "Judge calibration"),
    ("F2", "f2_security_family_status.v0.json", "Security family gates"),
    ("F3", "f3_process_split_boundary_status.v0.json", "G2b / process_split boundary"),
    ("F4", "f4_release_scorecard_status.v0.json", "Release scorecard"),
]


def _now() -> str:
    """+08:00 timestamp.

    Returns:
        Timestamp string.
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _load(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON object.

    Args:
        path: File path.

    Returns:
        Dict or None.
    """
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def main() -> int:
    """Write aggregate META_EVAL status + refresh Tier matrix meta flags.

    Returns:
        Exit code.
    """
    META.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for fid, fname, title in FAMILIES:
        doc = _load(META / fname) or {}
        counts = doc.get("counts") if isinstance(doc.get("counts"), dict) else {}
        rows.append(
            {
                "family_id": fid,
                "family": title,
                "family_green": bool(doc.get("family_green")),
                "green": counts.get("green"),
                "total": counts.get("total"),
                "source": f"docs/a3/evidence/meta_eval/{fname}",
                "status_md": f"docs/a3/META_EVAL_{fid}_STATUS.md",
            }
        )
    green_n = sum(1 for r in rows if r.get("family_green"))
    all_green = green_n == len(rows) and len(rows) == 4
    now = _now()
    out = {
        "schema": "eval.meta_eval.aggregate_status.v0",
        "recorded_at": now,
        "families": rows,
        "counts": {"families_green": green_n, "families_total": len(rows)},
        "meta_eval_families_green": all_green,
        "tier_a_expansion_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "process_split_authorized": False,
        "l5_declare_authorized": False,
        "honesty": (
            "META_EVAL F1–F4 rollup. families_green is a ruler prerequisite only — "
            "≠ Tier A expansion authorize ≠ L5 ≠ security cert ≠ process_split."
        ),
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    table = ["| 家族 | green | family_green | 状态页 |", "|---|:---:|:---:|---|"]
    for r in rows:
        table.append(
            f"| {r['family_id']} {r['family']} | "
            f"{r.get('green')}/{r.get('total')} | "
            f"{'✅' if r.get('family_green') else '❌'} | "
            f"[`META_EVAL_{r['family_id']}_STATUS.md`](./META_EVAL_{r['family_id']}_STATUS.md) |"
        )
    md = "\n".join(
        [
            "---",
            "doc_type: Reference",
            "---",
            "",
            "# META_EVAL 汇总状态",
            "",
            f"> 机器：[`evidence/meta_eval/meta_eval_aggregate_status.v0.json`](./evidence/meta_eval/meta_eval_aggregate_status.v0.json) · 时点 {now}",
            "> **诚实锁**：`meta_eval_families_green` ≠ Tier A 扩容授权 · ≠ L5 · ≠ process_split · `accuracy_claim=false`",
            "",
            "## 汇总",
            "",
            f"- families_green **{green_n}/{len(rows)}**",
            f"- `meta_eval_families_green`: **{str(all_green).lower()}**",
            f"- `tier_a_expansion_authorized`: **false**",
            "",
            "## 家族",
            "",
            *table,
            "",
            "## 下一步",
            "",
            "1. Phase 3 预备：见 [`PHASE3_PREP.md`](./PHASE3_PREP.md)（仍须 owner 授权才扩 Tier A gate）",
            "2. Phase 2 authorize 仍独立：[`PHASE2_PREP.md`](./PHASE2_PREP.md) / SPLIT_CHECKLIST",
            "3. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_aggregate_status.py`",
            "",
        ]
    )
    OUT_MD.write_text(md + "\n", encoding="utf-8")

    # Refresh Tier matrix honesty flags (do not promote A_candidate → authorized).
    tier = _load(TIER_JSON)
    if tier:
        tier["recorded_at"] = now
        tier["meta_eval_families_green"] = all_green
        tier["meta_eval_blocks_tier_a_claim"] = True
        tier["tier_a_expansion_authorized"] = False
        tier["accuracy_claim"] = False
        tier["process_split_authorized"] = False
        tier["honesty"] = (
            "A_candidate is NOT an authorized Tier A gate claim. "
            f"meta_eval_families_green={str(all_green).lower()} is prerequisite only; "
            "tier_a_expansion_authorized remains false until owner authorize."
        )
        TIER_JSON.write_text(json.dumps(tier, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        counts = tier.get("counts") if isinstance(tier.get("counts"), dict) else {}
        tier_md = "\n".join(
            [
                "---",
                "doc_type: Reference",
                "---",
                "",
                "# Tier 覆盖矩阵 v0（evaluation-system）",
                "",
                f"> 计划 §4.5 / §8 · 源：R12 `in_both` · 机器：[`evidence/tier_matrix_v0.json`](./evidence/tier_matrix_v0.json)",
                f"> **诚实锁**：`A_candidate` **≠** 已授权 Tier A gate 宣称；META_EVAL 家族绿见 [`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md)",
                f"> **时点**：{now} · R12 H5 open=**{tier.get('r12_h5_open', '?')}** · "
                f"`meta_eval_families_green`=**{str(all_green).lower()}**（≠ 扩容授权）",
                "",
                "## 汇总",
                "",
                "| Tier | 数量 | 含义 |",
                "|---|---:|---|",
                f"| **A_candidate** | {counts.get('A_candidate', '?')} | 准确率/证据/安全门/记分卡相关；扩容前须元评测 |",
                f"| **B** | {counts.get('B', '?')} | Subject/smoke/pack/方法轨等内部关键路径 |",
                f"| **C** | {counts.get('C', '?')} | 其余登记符号（含 Error/helper） |",
                "",
                "## META_EVAL 前置",
                "",
                f"- `meta_eval_families_green`: **{str(all_green).lower()}**（F1–F4）",
                "- `tier_a_expansion_authorized`: **false**",
                "",
                "## 下一步",
                "",
                "1. META_EVAL 已绿 → 进入 [`PHASE3_PREP.md`](./PHASE3_PREP.md) 首波 A_candidate 工程预备（禁一次全开）",
                "2. B 轨挂 suite + 复核日历",
                "3. C 仅登记；禁止挤占 A 名额",
                "",
                "## 关联",
                "",
                "- R12：[`R12_CAPABILITY_RECONCILIATION.md`](./R12_CAPABILITY_RECONCILIATION.md)",
                "- META：[`META_EVAL_STATUS.md`](./META_EVAL_STATUS.md) · [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)",
                "",
            ]
        )
        TIER_MD.write_text(tier_md + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "meta_eval_families_green": all_green,
                "families_green": green_n,
                "tier_a_expansion_authorized": False,
                "out": str(OUT_JSON.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
