"""C1 fixture metrics — Top-1 / Top-3 / unknown-stale on real fixture pack only."""
from __future__ import annotations

from typing import Any, Dict, List

from core.apps.diagnosis.service.adapters import fixture_root, load_fixture
from core.apps.diagnosis.service.engine import diagnose_case


def fixture_metrics(*, limit: int = 10) -> Dict[str, Any]:
    root = fixture_root()
    case_dirs = sorted(
        p for p in root.iterdir() if p.is_dir() and p.name.startswith("dx.")
    )[: max(1, int(limit))]
    rows: List[Dict[str, Any]] = []
    top1 = top3 = unk_ok = stale_ok = 0
    for d in case_dirs:
        evidence_doc, expected = load_fixture(d.name)
        out = diagnose_case(
            case_id=d.name,
            evidence=list(evidence_doc.get("evidence") or []),
            payload=evidence_doc.get("payload") or {},
            expected=expected,
        )
        hyps = out.get("hypotheses") or []
        ranked = [str(h.get("root_cause") or "") for h in hyps]
        gold = str(expected.get("gold_root_cause") or "")
        hit1 = bool(ranked) and ranked[0] == gold
        hit3 = gold in ranked[:3]
        if hit1:
            top1 += 1
        if hit3:
            top3 += 1
        expect_u = bool(expected.get("expect_unknown"))
        expect_s = bool(expected.get("expect_stale"))
        status = out.get("status")
        if expect_u:
            unk_ok += int(status == "blocked_unknown" or gold == "insufficient_evidence" and hit1)
        if expect_s:
            stale_ok += int(status == "blocked_stale" or (hit1 and gold == "data_stale"))
        rows.append(
            {
                "case_id": d.name,
                "gold_root_cause": gold,
                "top1": ranked[0] if ranked else None,
                "top3": ranked[:3],
                "hit_top1": hit1,
                "hit_top3": hit3,
                "status": status,
                "expect_unknown": expect_u,
                "expect_stale": expect_s,
            }
        )
    n = len(rows) or 1
    expect_u_n = sum(1 for r in rows if r["expect_unknown"]) or 0
    expect_s_n = sum(1 for r in rows if r["expect_stale"]) or 0
    return {
        "ok": True,
        "product_id": "diagnosis",
        "accuracy_claim": False,
        "provenance": "desensitized_local_export",
        "n": len(rows),
        "top1_rate": round(top1 / n, 4),
        "top3_rate": round(top3 / n, 4),
        "unknown_correct_rate": round(unk_ok / expect_u_n, 4) if expect_u_n else None,
        "stale_correct_rate": round(stale_ok / expect_s_n, 4) if expect_s_n else None,
        "cases": rows,
        "note": "Engineering fixture metrics only — not an accuracy certification.",
    }
