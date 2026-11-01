"""C1/C3.5 fixture metrics — Top-1 / Top-3 / unknown-stale on real fixture packs.

Blind by default: diagnose without `expected` gold ranking so rates are not
self-certified by fixture labels. Labels are used only for scoring.

C3.5: subset=core|adversarial|all — adversarial rates may be <1.00 (honesty).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.apps.diagnosis.service.adapters import fixture_root, load_fixture
from core.apps.diagnosis.service.engine import diagnose_case

VALID_SUBSETS = frozenset({"core", "adversarial", "all"})


def _case_subset(name: str) -> str:
    if name.startswith("dx.adv."):
        return "adversarial"
    return "core"


def _select_cases(*, subset: str, limit: int) -> List[str]:
    root = fixture_root()
    all_dirs = sorted(
        p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("dx.")
    )
    if subset == "adversarial":
        names = [n for n in all_dirs if _case_subset(n) == "adversarial"]
    elif subset == "core":
        names = [n for n in all_dirs if _case_subset(n) == "core"]
    else:
        names = all_dirs
    return names[: max(1, int(limit))]


def fixture_metrics(
    *,
    limit: int = 10,
    blind: bool = True,
    subset: str = "core",
) -> Dict[str, Any]:
    sub = (subset or "core").strip().lower()
    if sub not in VALID_SUBSETS:
        raise ValueError(f"invalid_subset:{subset}")
    case_ids = _select_cases(subset=sub, limit=limit)
    rows: List[Dict[str, Any]] = []
    top1 = top3 = unk_ok = stale_ok = 0
    bare = 0
    hyp_n = 0
    for cid in case_ids:
        evidence_doc, expected = load_fixture(cid)
        # Blind path: heuristics only. Labels score after the fact.
        out = diagnose_case(
            case_id=cid,
            evidence=list(evidence_doc.get("evidence") or []),
            payload=evidence_doc.get("payload") or {},
            expected=None if blind else expected,
        )
        hyps = out.get("hypotheses") or []
        findings = out.get("findings") or []
        for h in hyps:
            hyp_n += 1
            if not h.get("support_evidence_ids"):
                bare += 1
        for f in findings:
            if not f.get("evidence_ids"):
                bare += 1
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
            unk_ok += int(
                status == "blocked_unknown"
                or (gold == "insufficient_evidence" and hit1)
            )
        if expect_s:
            stale_ok += int(status == "blocked_stale" or (hit1 and gold == "data_stale"))
        rows.append(
            {
                "case_id": cid,
                "subset": _case_subset(cid),
                "adversarial": bool(expected.get("adversarial"))
                or cid.startswith("dx.adv."),
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
    evidence_complete_rate = round((hyp_n - bare) / hyp_n, 4) if hyp_n else 0.0
    note = "Engineering fixture metrics only — not an accuracy certification."
    if sub == "adversarial":
        note += " Adversarial holdout may score well below core; do not market as accuracy."
    elif sub == "all":
        note += " Mixed core+adversarial; report subsets separately for honesty."
    return {
        "ok": True,
        "product_id": "diagnosis",
        "accuracy_claim": False,
        "blind": bool(blind),
        "subset": sub,
        "provenance": "desensitized_local_export",
        "n": len(rows),
        "top1_rate": round(top1 / n, 4),
        "top3_rate": round(top3 / n, 4),
        "evidence_complete_rate": evidence_complete_rate,
        "bare_conclusion_count": bare,
        "unknown_correct_rate": round(unk_ok / expect_u_n, 4) if expect_u_n else None,
        "stale_correct_rate": round(stale_ok / expect_s_n, 4) if expect_s_n else None,
        "cases": rows,
        "note": note,
    }


def fixture_metrics_by_subset(
    *,
    limit_core: int = 10,
    limit_adv: int = 30,
    blind: bool = True,
) -> Dict[str, Any]:
    """Convenience: return core + adversarial + all snapshots (honesty bundle)."""
    core = fixture_metrics(limit=limit_core, blind=blind, subset="core")
    adv = fixture_metrics(limit=limit_adv, blind=blind, subset="adversarial")
    return {
        "ok": True,
        "accuracy_claim": False,
        "blind": bool(blind),
        "core": core,
        "adversarial": adv,
        "note": (
            "Report core and adversarial separately. "
            "Never market core Top-1 as diagnosis accuracy."
        ),
    }
