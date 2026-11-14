#!/usr/bin/env python3
"""Apply OWNER AUTHORIZE b_cycle1_owner_signoff to Cycle1 board.

Flips per-bucket owner_signoff after sample_rerun. Does NOT claim Tier B
coverage complete. Does NOT flip Chart.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
CYCLE = META / "phase3_b_review_cycle1.v0.json"
AUTH = META / "phase3_b_cycle1_owner_signoff_authorize.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_B_REVIEW_CYCLE1.md"
AUTH_MD = ROOT / "docs/a3/PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md"
LOCKS = META / "phase3_honesty_locks.v0.json"
LOCKS_MD = ROOT / "docs/a3/PHASE3_HONESTY_LOCKS.md"


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def apply_signoff(*, owner: str = "朱向群") -> Dict[str, Any]:
    """应用 owner_signoff 授权到 Cycle1 六桶。

    Args:
        owner: 授权人。

    Returns:
        摘要。

    Raises:
        FileNotFoundError: Cycle1 账本缺失。
        ValueError: sample_rerun 未齐。
    """
    if not CYCLE.is_file():
        raise FileNotFoundError(str(CYCLE))
    data = json.loads(CYCLE.read_text(encoding="utf-8"))
    waves = list(data.get("waves") or [])
    signed: List[str] = []
    blocked: List[str] = []
    ts = _now()
    for w in waves:
        if not isinstance(w, dict):
            continue
        ck = dict(w.get("checklist") or {})
        bid = str(w.get("bucket_id") or "")
        if not ck.get("sample_rerun"):
            blocked.append(bid)
            continue
        ck["owner_signoff"] = True
        w["checklist"] = ck
        w["owner_signoff_at"] = ts
        w["owner_signoff_by"] = owner
        w["status"] = "closed"
        signed.append(bid)

    if blocked:
        raise ValueError(f"sample_rerun incomplete for: {blocked}")

    data["recorded_at"] = ts
    data["status"] = "owner_signed"
    data["owner_signoff_authorized"] = True
    data["owner_signoff_authorized_at"] = ts
    data["owner_signoff_by"] = owner
    data["coverage_complete_claim"] = False
    data["chart_a3_process_split_authorized"] = False
    data["waves"] = waves
    data["honesty"] = (
        "Owner AUTHORIZE b_cycle1_owner_signoff closed Cycle-1 buckets after sample_rerun. "
        "≠ Tier B coverage complete ≠ Chart flip ≠ closed_loop."
    )
    data["authorize_ref"] = "docs/a3/evidence/meta_eval/phase3_b_cycle1_owner_signoff_authorize.v0.json"
    CYCLE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    auth = {
        "schema": "eval.phase3.b_cycle1_owner_signoff_authorize.v0",
        "recorded_at": ts,
        "status": "authorized",
        "owner": owner,
        "owner_decision": "AUTHORIZE b_cycle1_owner_signoff",
        "decided_at": ts,
        "b_cycle1_owner_signoff_authorized": True,
        "buckets_signed": signed,
        "buckets_n": len(signed),
        "residual": {
            "coverage_complete_claim": False,
            "chart_a3_process_split_authorized": False,
            "closed_loop_claim": False,
            "independent_staging_host": False,
            "note": "Cycle-1 owner signoff only. Staging live and Tier B coverage remain open.",
        },
        "honesty": (
            "Owner AUTHORIZE b_cycle1_owner_signoff. "
            "≠ Tier B coverage complete ≠ staging live ≠ Chart flip."
        ),
    }
    META.mkdir(parents=True, exist_ok=True)
    AUTH.write_text(json.dumps(auth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 3 · Tier B 首轮复核（Cycle 1）",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_b_review_cycle1.v0.json`](./evidence/meta_eval/phase3_b_review_cycle1.v0.json) · {ts}",
        f"> 授权：[`PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md`](./PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md)",
        "> **诚实锁**：owner_signoff ≠ 覆盖完成 · Chart 仍 false",
        "",
        "| bucket | n | due | status | sample_rerun | owner_signoff |",
        "|---|---:|---|---|:---:|:---:|",
    ]
    for w in waves:
        ck = w.get("checklist") or {}
        lines.append(
            f"| `{w.get('bucket_id')}` | {w.get('n')} | {w.get('due_on')} | "
            f"{w.get('status')} | "
            f"{'✅' if ck.get('sample_rerun') else '☐'} | "
            f"{'✅' if ck.get('owner_signoff') else '☐'} |"
        )
    lines.extend(
        [
            "",
            "## 状态",
            "",
            f"- Cycle1：`owner_signed`（{len(signed)}/6 buckets）",
            "- `coverage_complete_claim`：**false**",
            "- Chart：**false**",
            "",
            "## 复跑（不会清 signoff）",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_b_cycle1_sample_rerun.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    AUTH_MD.write_text(
        "\n".join(
            [
                "---",
                "doc_type: Reference",
                "---",
                "",
                "# AUTHORIZE b_cycle1_owner_signoff",
                "",
                f"> 机器：[`evidence/meta_eval/phase3_b_cycle1_owner_signoff_authorize.v0.json`](./evidence/meta_eval/phase3_b_cycle1_owner_signoff_authorize.v0.json)  ",
                f"> **状态**：`authorized`（{owner} · `AUTHORIZE b_cycle1_owner_signoff`） · {ts}",
                "",
                "## 翻转",
                "",
                "| 项 | 值 |",
                "|---|---|",
                "| Cycle1 六桶 `owner_signoff` | **true** |",
                "| Cycle1 `status` | `owner_signed` |",
                "| `coverage_complete_claim` | **仍 false** |",
                "| Chart `a3_process_split_authorized` | **仍 false** |",
                "| staging live | **仍 blocked**（无独立 host） |",
                "",
                "## Buckets",
                "",
                ", ".join(f"`{b}`" for b in signed),
                "",
                f"看板：[`PHASE3_B_REVIEW_CYCLE1.md`](./PHASE3_B_REVIEW_CYCLE1.md)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if LOCKS.is_file():
        locks = json.loads(LOCKS.read_text(encoding="utf-8"))
        flags = dict(locks.get("flags") or {})
        flags["b_cycle1_owner_signoff_authorized"] = True
        flags["tier_b_coverage_complete_claim"] = False
        flags["chart_a3_process_split_authorized"] = False
        locks["flags"] = flags
        refs = dict(locks.get("authorize_refs") or {})
        refs["b_cycle1_owner_signoff"] = (
            "docs/a3/evidence/meta_eval/phase3_b_cycle1_owner_signoff_authorize.v0.json"
        )
        locks["authorize_refs"] = refs
        locks["recorded_at"] = ts
        locks["honesty"] = (
            "Policy flags include b_cycle1_owner_signoff_authorized. "
            "Tier B coverage complete / Chart / staging live remain false."
        )
        LOCKS.write_text(json.dumps(locks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if LOCKS_MD.is_file():
        md = LOCKS_MD.read_text(encoding="utf-8")
        if "b_cycle1_owner_signoff_authorized" not in md:
            md = md.replace(
                "| `phase4_routing_authorized` | **true** | [`PHASE4_ROUTING_AUTHORIZE.md`](./PHASE4_ROUTING_AUTHORIZE.md) |\n",
                "| `phase4_routing_authorized` | **true** | [`PHASE4_ROUTING_AUTHORIZE.md`](./PHASE4_ROUTING_AUTHORIZE.md) |\n"
                "| `b_cycle1_owner_signoff_authorized` | **true** | [`PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md`](./PHASE3_B_CYCLE1_OWNER_SIGNOFF_AUTHORIZE.md) |\n",
            )
        # refresh timestamp line if present
        if "phase3_honesty_locks.v0.json" in md:
            import re

            md = re.sub(
                r"(phase3_honesty_locks\.v0\.json\]\(./evidence/meta_eval/phase3_honesty_locks\.v0\.json\) · )[^\n]+",
                rf"\g<1>{ts}",
                md,
                count=1,
            )
        LOCKS_MD.write_text(md, encoding="utf-8")

    return {
        "buckets_signed": signed,
        "status": "owner_signed",
        "coverage_complete_claim": False,
    }


def main() -> int:
    """CLI：应用 b_cycle1_owner_signoff。

    Returns:
        退出码。
    """
    try:
        summary = apply_signoff()
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **summary, "chart": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
