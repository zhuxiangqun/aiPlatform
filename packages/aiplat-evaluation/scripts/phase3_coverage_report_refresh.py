#!/usr/bin/env python3
"""Phase 3 — refresh A/B/C coverage skeleton from ledger + inventory.

Does not flip global_tier_a_expansion_authorized. Never emits a single coverage%.
with_suite = symbols whose evidence_refs all resolve under packages/aiplat-evaluation.
with_gate = symbols with tier_a_gate_authorized on the per-symbol ledger (A only).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
OUT_JSON = META / "phase3_coverage_report_skeleton.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_COVERAGE_REPORT_SKELETON.md"
INV = META / "phase3_a_candidate_inventory.v0.json"
AUTH = META / "phase3_tier_a_authorized_symbols.v0.json"
CAL = META / "phase3_b_review_calendar.v0.json"
TIER = ROOT / "docs/a3/evidence/tier_matrix_v0.json"


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _measure_a() -> Dict[str, Any]:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    auth_syms = {x["symbol"] for x in auth.get("symbols", []) if x.get("tier_a_gate_authorized")}
    with_suite = 0
    with_gate = 0
    missing_evidence: List[str] = []
    for it in inv.get("items", []):
        sym = it["symbol"]
        refs = it.get("evidence_refs") or []
        ok = bool(refs) and all((ROOT / r).exists() for r in refs)
        if ok:
            with_suite += 1
        else:
            bad = [r for r in refs if not (ROOT / r).exists()]
            if bad:
                missing_evidence.append(f"{sym}:{','.join(bad)}")
        if sym in auth_syms or it.get("tier_a_gate_authorized"):
            with_gate += 1
    return {
        "tier": "A_candidate",
        "n": inv.get("n", len(inv.get("items", []))),
        "with_suite": with_suite,
        "with_gate": with_gate,
        "scoped_authorized": len(auth_syms),
        "exempt": 0,
        "unauthorized_claim": False,
        "note": (
            f"scoped_authorized={len(auth_syms)}; "
            "global_tier_a_expansion_authorized=false; "
            "with_suite=evidence_refs-on-disk"
        ),
        "missing_evidence_sample": missing_evidence[:5],
    }


def main() -> int:
    ts = _now()
    tier = json.loads(TIER.read_text(encoding="utf-8")) if TIER.exists() else {}
    tiers = (tier.get("tiers") or {}) if isinstance(tier, dict) else {}
    n_b = len(tiers.get("B") or [])
    n_c = len(tiers.get("C") or [])
    if CAL.exists():
        cal = json.loads(CAL.read_text(encoding="utf-8"))
        n_b = cal.get("n_symbols", n_b) or n_b

    a_row = _measure_a()
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    payload = {
        "schema": "eval.phase3.coverage_report_skeleton.v0",
        "recorded_at": ts,
        "columns": [
            "tier",
            "n",
            "with_suite",
            "with_gate",
            "scoped_authorized",
            "exempt",
            "unauthorized_claim",
        ],
        "rows": [
            a_row,
            {
                "tier": "B",
                "n": n_b,
                "with_suite": None,
                "with_gate": None,
                "scoped_authorized": None,
                "exempt": 0,
                "unauthorized_claim": False,
                "note": "calendar draft only; suite attach pending",
            },
            {
                "tier": "C",
                "n": n_c or 458,
                "with_suite": None,
                "with_gate": None,
                "scoped_authorized": None,
                "exempt": 0,
                "unauthorized_claim": False,
                "note": "register-only; must not crowd A slots",
            },
        ],
        "forbid_single_coverage_percent": True,
        "tier_a_expansion_authorized": bool(auth.get("global_tier_a_expansion_authorized")),
        "accuracy_claim": bool(auth.get("accuracy_claim")),
        "a_candidate_scoped_complete": bool(auth.get("a_candidate_scoped_complete")),
        "honesty": (
            "A row measured from inventory evidence_refs + per-symbol ledger. "
            "B/C suite/gate remain null until measured. "
            "Never collapse A/B/C into one coverage%. "
            "scoped complete ≠ global_tier_a_expansion_authorized."
        ),
    }
    # strip helper field from published row
    a_row.pop("missing_evidence_sample", None)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 3 · 覆盖率报表骨架（A/B/C 分列）",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_coverage_report_skeleton.v0.json`](./evidence/meta_eval/phase3_coverage_report_skeleton.v0.json) · 时点 {ts}",
        "> **禁止**单一「覆盖%」；B/C 的 `with_suite`/`with_gate` 仍为 null（待实测）",
        "",
        "",
        "| tier | n | with_suite | with_gate | scoped_authorized | exempt | unauthorized_claim |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in payload["rows"]:
        lines.append(
            f"| {r['tier']} | {r['n']} | {r.get('with_suite')} | {r.get('with_gate')} | "
            f"{r.get('scoped_authorized')} | {r['exempt']} | {r['unauthorized_claim']} |"
        )
    lines += [
        "",
        "## 诚实锁",
        "",
        f"- `tier_a_expansion_authorized={payload['tier_a_expansion_authorized']}`",
        f"- `a_candidate_scoped_complete={payload.get('a_candidate_scoped_complete')}`",
        "- `forbid_single_coverage_percent=true`",
        "- A.`with_gate` = 按符号 scoped 账本；**≠** 全局扩容授权",
        "",
        "## 复跑",
        "",
        "```bash",
        "python3 packages/aiplat-evaluation/scripts/phase3_coverage_report_refresh.py",
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"A n={a_row['n']} suite={a_row['with_suite']} gate={a_row['with_gate']} "
        f"scoped={a_row['scoped_authorized']} global={payload['tier_a_expansion_authorized']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
