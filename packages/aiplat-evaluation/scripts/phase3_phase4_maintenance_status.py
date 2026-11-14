#!/usr/bin/env python3
"""No-staging maintenance status — G2b re-ingest drift + Cycle1 due sampling.

Reports only. Does not flip Chart / closed_loop / coverage_complete.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
G2B = REPO / ".aiplat/eval_trust/g2b_fail_decision_table_v0.json"
INGEST = META / "phase4_g2b_taxonomy_ingest.v0.json"
CYCLE = META / "phase3_b_review_cycle1.v0.json"
OUT_JSON = META / "phase3_phase4_maintenance_status.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_PHASE4_MAINTENANCE.md"


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _sha256(path: Path) -> str:
    """文件内容 sha256。

    Args:
        path: 文件路径。

    Returns:
        hex digest。
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_day(s: str) -> Optional[date]:
    """解析 YYYY-MM-DD。

    Args:
        s: 日期字符串。

    Returns:
        date 或 None。
    """
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def main() -> int:
    """写出维护状态板。

    Returns:
        退出码（表缺失等为 1；仅「未到期/无漂移」仍 0）。
    """
    today = date.today()
    g2b: Dict[str, Any] = {
        "table_present": G2B.is_file(),
        "reingest_needed": False,
        "command": (
            "python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py "
            "--from-g2b-fail-table && "
            "python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py "
            "--close-from-g2b-provisional && "
            "python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --verify-pack"
        ),
    }
    if G2B.is_file():
        cur = _sha256(G2B)
        g2b["current_sha256"] = cur
        prev = None
        if INGEST.is_file():
            ing = json.loads(INGEST.read_text(encoding="utf-8"))
            prev = ing.get("source_sha256")
            g2b["last_ingest_at"] = ing.get("recorded_at")
            g2b["last_ingest_rows_n"] = ing.get("rows_n")
            g2b["last_ingest_sha256"] = prev
        if prev is None:
            g2b["reingest_needed"] = True
            g2b["reason"] = "no_source_sha256_on_last_ingest"
        elif prev != cur:
            g2b["reingest_needed"] = True
            g2b["reason"] = "g2b_table_sha_changed"
        else:
            g2b["reason"] = "sha_matches_last_ingest"

    cycle_rows: List[Dict[str, Any]] = []
    due_now: List[str] = []
    if CYCLE.is_file():
        cyc = json.loads(CYCLE.read_text(encoding="utf-8"))
        for w in cyc.get("waves") or []:
            if not isinstance(w, dict):
                continue
            due = _parse_day(str(w.get("due_on") or ""))
            bid = str(w.get("bucket_id") or "")
            days = (due - today).days if due else None
            row = {
                "bucket_id": bid,
                "due_on": w.get("due_on"),
                "days_until_due": days,
                "owner_signoff": bool((w.get("checklist") or {}).get("owner_signoff")),
                "sample_due": bool(due and days is not None and days <= 0),
            }
            cycle_rows.append(row)
            if row["sample_due"]:
                due_now.append(bid)

    cycle = {
        "cycle_present": CYCLE.is_file(),
        "as_of": today.isoformat(),
        "buckets_due_for_sample": due_now,
        "sample_rerun_needed": bool(due_now),
        "waves": cycle_rows,
        "command": (
            "python3 packages/aiplat-evaluation/scripts/phase3_b_cycle1_sample_rerun.py"
        ),
        "note": "Due-day sampling refreshes evidence; does not clear owner_signoff.",
    }

    payload = {
        "schema": "eval.phase3_phase4.maintenance_status.v0",
        "recorded_at": _now(),
        "g2b_reingest": g2b,
        "cycle1_due_sample": cycle,
        "closed_loop_claim": False,
        "chart_a3_process_split_authorized": False,
        "honesty": (
            "Maintenance status only. Re-ingest / due-day sample are optional ops "
            "until triggers fire. ≠ host tasks ≠ Chart flip ≠ closed_loop."
        ),
    }
    META.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cur_sha = str(g2b.get("current_sha256") or "")
    prev_sha = str(g2b.get("last_ingest_sha256") or "")
    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase3/4 无 staging 维护（触发式）",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_phase4_maintenance_status.v0.json`](./evidence/meta_eval/phase3_phase4_maintenance_status.v0.json) · {_now()}",
        "> **诚实锁**：维护 ≠ closed_loop · ≠ Chart · ≠ staging live",
        "",
        "## 1. G2b 决策表更新 → 重跑摄入",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 当前表 sha256 | `{cur_sha[:16] + '…' if cur_sha else 'missing'}` |",
        f"| 上次摄入 sha | `{prev_sha[:16] + '…' if prev_sha else 'none'}` |",
        f"| 需重跑 | **{'是' if g2b.get('reingest_needed') else '否'}**（{g2b.get('reason')}） |",
        "",
        "> 仅当「需重跑=是」时执行；同 sha 强跑幂等（不重复开单）。",
        "",
        "```bash",
        g2b["command"],
        "```",
        "",
        "## 2. Cycle1 到 due 日 → 再抽样",
        "",
        f"as_of **{today.isoformat()}** · 到期需抽："
        + (", ".join(f"`{b}`" for b in due_now) if due_now else "（无）"),
        "",
        "> 仅当「到期需抽」非空时建议执行；未到期强跑只刷新证据，不清 signoff。",
        "",
        "| bucket | due | days | sample_due | owner_signoff |",
        "|---|---|---:|:---:|:---:|",
    ]
    for r in cycle_rows:
        lines.append(
            f"| `{r['bucket_id']}` | {r['due_on']} | {r['days_until_due']} | "
            f"{'✅' if r['sample_due'] else '☐'} | {'✅' if r['owner_signoff'] else '☐'} |"
        )
    lines.extend(
        [
            "",
            "```bash",
            cycle["command"],
            "```",
            "",
            "抽样不清 `owner_signoff`；≠ Tier B coverage complete。",
            "",
            "## 复跑本板",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_phase4_maintenance_status.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "g2b_reingest_needed": g2b.get("reingest_needed"),
                "cycle1_sample_due_n": len(due_now),
                "buckets_due": due_now,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
