#!/usr/bin/env python3
"""Phase 3 — refresh Tier C register-only inventory from tier matrix.

Does not attach suites or authorize gates. Must not crowd A_candidate slots.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIER = ROOT / "docs/a3/evidence/tier_matrix_v0.json"
OUT = ROOT / "docs/a3/evidence/meta_eval/phase3_tier_c_register.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_TIER_C_REGISTER.md"


def main() -> int:
    """Rewrite Tier C register JSON + short MD.

    Returns:
        Exit code.
    """
    tier = json.loads(TIER.read_text(encoding="utf-8"))
    syms = list((tier.get("tiers") or {}).get("C") or [])
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    payload = {
        "schema": "eval.phase3.tier_c_register.v0",
        "recorded_at": ts,
        "policy": "register_only",
        "n": len(syms),
        "suite_hook": None,
        "gate_authorized": False,
        "accuracy_claim_applies": False,
        "must_not_crowd_a_slots": True,
        "symbols": syms,
        "honesty": "Tier C register-only. No suite attach / no Tier A gate claim.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(
        "\n".join(
            [
                "---",
                "doc_type: Reference",
                "---",
                "",
                "# Phase 3 · Tier C 仅登记",
                "",
                f"> 机器：[`evidence/meta_eval/phase3_tier_c_register.v0.json`](./evidence/meta_eval/phase3_tier_c_register.v0.json) · 时点 {ts}",
                f"> n=**{len(syms)}** · **policy=`register_only`**",
                "",
                "## 规则",
                "",
                "| ✅ | ❌ |",
                "|---|---|",
                "| 登记符号名 | suite 挂接 / gate 宣称 |",
                "| 保持与 A 槽隔离 | 挤占 A_candidate |",
                "| 覆盖报表 C 列可计 n | 单一覆盖% |",
                "",
                "```bash",
                "python3 packages/aiplat-evaluation/scripts/phase3_tier_c_register.py",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"tier_c n={len(syms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
