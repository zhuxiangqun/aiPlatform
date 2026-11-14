#!/usr/bin/env python3
"""Phase 3 — Tier B first review cycle board (concrete dates).

Reads attached suite rollup / calendar; writes cycle-1 due dates.
Does not claim Tier B coverage complete.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
CAL = META / "phase3_b_review_calendar.v0.json"
ROLLUP = META / "phase3_b_suite_attach_rollup.v0.json"
OUT_JSON = META / "phase3_b_review_cycle1.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_B_REVIEW_CYCLE1.md"
CAL_MD = ROOT / "docs/a3/PHASE3_B_REVIEW_CALENDAR.md"

# Anchor: first cycle opened 2026-11-14 (today in session).
ANCHOR = date(2026, 11, 14)
CADENCE_DELTA = {
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=90),
    "semi_annual": timedelta(days=180),
}


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main() -> int:
    """写出 B 轨首轮复核板并刷新日历 next_review 日期。

    Returns:
        进程退出码。
    """
    if not CAL.is_file():
        print("missing calendar json", file=sys.stderr)
        return 1

    cal = json.loads(CAL.read_text(encoding="utf-8"))
    waves_in = list(cal.get("waves") or [])
    cycle_waves: List[Dict[str, Any]] = []
    for w in waves_in:
        if not isinstance(w, dict):
            continue
        cadence = str(w.get("cadence") or "quarterly")
        due = ANCHOR + CADENCE_DELTA.get(cadence, timedelta(days=90))
        row = {
            "bucket_id": w.get("bucket_id"),
            "n": w.get("n"),
            "cadence": cadence,
            "owner_role": w.get("owner_role"),
            "suite_hook": w.get("suite_hook"),
            "attached_n": w.get("attached_n"),
            "cycle": 1,
            "opened_on": ANCHOR.isoformat(),
            "due_on": due.isoformat(),
            "status": "open",
            "checklist": {
                "suite_hook_attached": w.get("suite_hook") == "attached",
                "sample_rerun": False,
                "gap_symbols_triaged": not bool(w.get("gap_symbols")),
                "owner_signoff": False,
            },
            "gap_symbols": w.get("gap_symbols") or [],
            "suite_attach_ref": w.get("suite_attach_ref"),
        }
        cycle_waves.append(row)
        w["next_review"] = due.isoformat()
        w["cycle1_due_on"] = due.isoformat()
        w["cycle1_status"] = "open"

    cal["recorded_at"] = _now()
    cal["tier_a_expansion_authorized"] = True
    cal["accuracy_claim"] = True
    cal["process_split_authorized"] = True
    cal["cycle1"] = {
        "opened_on": ANCHOR.isoformat(),
        "status": "open",
        "ref": "docs/a3/evidence/meta_eval/phase3_b_review_cycle1.v0.json",
    }
    cal["honesty"] = (
        "First review cycle opened with concrete due dates. "
        "Suite hooks attached ≠ Tier B coverage complete. Chart still false."
    )
    CAL.write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {
        "schema": "eval.phase3.b_review_cycle1.v0",
        "recorded_at": _now(),
        "opened_on": ANCHOR.isoformat(),
        "status": "open",
        "tier_b_n": cal.get("tier_b_n"),
        "waves": cycle_waves,
        "coverage_complete_claim": False,
        "chart_a3_process_split_authorized": False,
        "honesty": (
            "Cycle-1 board only. Owners must complete sample_rerun + signoff by due_on. "
            "≠ coverage complete ≠ Chart flip."
        ),
    }
    if ROLLUP.is_file():
        payload["rollup_ref"] = "docs/a3/evidence/meta_eval/phase3_b_suite_attach_rollup.v0.json"
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 3 · Tier B 首轮复核（Cycle 1）",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_b_review_cycle1.v0.json`](./evidence/meta_eval/phase3_b_review_cycle1.v0.json) · {_now()}",
        f"> 开板：`{ANCHOR.isoformat()}` · 父日历：[`PHASE3_B_REVIEW_CALENDAR.md`](./PHASE3_B_REVIEW_CALENDAR.md)",
        "> **诚实锁**：suite attached ≠ 覆盖完成 · Chart 仍 false",
        "",
        "| bucket | n | cadence | due | status | sample_rerun | owner_signoff |",
        "|---|---:|---|---|---|:---:|:---:|",
    ]
    for w in cycle_waves:
        ck = w.get("checklist") or {}
        lines.append(
            f"| `{w.get('bucket_id')}` | {w.get('n')} | {w.get('cadence')} | "
            f"{w.get('due_on')} | {w.get('status')} | "
            f"{'✅' if ck.get('sample_rerun') else '☐'} | "
            f"{'✅' if ck.get('owner_signoff') else '☐'} |"
        )
    lines.extend(
        [
            "",
            "## Owner 动作",
            "",
            "1. 按 due 日前对该 bucket **抽样复跑** suite（记入 sample_rerun）",
            "2. 消化 `gap_symbols`（若有）",
            "3. owner_signoff 后把该 wave `status` → `closed`",
            "",
            "## 复跑生成",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_b_review_cycle1.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    # Refresh human calendar MD with concrete due dates.
    cal_lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 3 · Tier B 复核日历",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_b_review_calendar.v0.json`](./evidence/meta_eval/phase3_b_review_calendar.v0.json) · {_now()}",
        f"> Tier B n=**{cal.get('tier_b_n')}** · Cycle 1：[`PHASE3_B_REVIEW_CYCLE1.md`](./PHASE3_B_REVIEW_CYCLE1.md)",
        "> **诚实锁**：B1–B6 suite_hook **attached** ≠ 覆盖完成",
        "",
        "## Waves",
        "",
        "| bucket | n | cadence | owner_role | next_review | suite_hook |",
        "|---|---:|---|---|---|---|",
    ]
    for w in waves_in:
        bid = w.get("bucket_id")
        attach = "**attached**" if w.get("suite_hook") == "attached" else str(w.get("suite_hook"))
        cal_lines.append(
            f"| `{bid}` | {w.get('n')} | {w.get('cadence')} | {w.get('owner_role')} | "
            f"{w.get('next_review')} | {attach} |"
        )
    cal_lines.extend(
        [
            "",
            "汇总：[`PHASE3_B_SUITE_ATTACH_ROLLUP.md`](./PHASE3_B_SUITE_ATTACH_ROLLUP.md)",
            "",
            "## 复跑",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_b_review_cycle1.py",
            "```",
            "",
        ]
    )
    CAL_MD.write_text("\n".join(cal_lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "cycle": 1,
                "waves": len(cycle_waves),
                "opened_on": ANCHOR.isoformat(),
                "due_span": [cycle_waves[0]["due_on"], cycle_waves[-1]["due_on"]]
                if cycle_waves
                else [],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
