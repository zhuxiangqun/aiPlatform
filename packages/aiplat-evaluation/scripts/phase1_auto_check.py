#!/usr/bin/env python3
"""Phase 1 §2 engineering auto-check (≠ dual-human sign-off).

Runs the five mechanical audits from PHASE1_AUDIT_WORKSHEET.md §2 and writes
``docs/a3/evidence/phase1_auto_check.v0.json``.

Honesty: PASS here does **not** authorize claiming「首版 5/5 已审计通过」.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
MAN = ROOT / "docs/a3/evidence/evidence_manifest.v1.json"
ATT = ROOT / "docs/a3/evidence/g2b_accuracy_claim_attestation.v1.json"
SC = ROOT / "docs/a3/scorecard_v1.json"
AGG = ROOT / "docs/a3/evidence/g2b_accuracy_aggregate.v1.json"
OUT = ROOT / "docs/a3/evidence/phase1_auto_check.v0.json"

META_DOCS = {
    "PHASE1_AUDIT_WORKSHEET.md",
    "eval-system-improvement-plan.md",
    "PHASE0_FAILURE_DISPOSITION.md",
    "PHASE0_R_CHECKLIST_RECOMMENDATION.md",
    "SCORECARD_V1.md",
    "phase1_auto_check.v0.json",
}
FORBID_CUES = (
    "不可写",
    "不得宣称",
    "禁止",
    "≠",
    "仍禁止",
    "签字完成前",
    "无「",
    '无"',
    "无'",
    "诚实锁",
    "Honesty",
    "不得",
    "禁宣",
    "forbid",
    "not claim",
)
PATTERNS = ("生产已独立", "准确率已认证", "首版 5/5 已审计通过")


def _rec(results: List[Dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    results.append({"check": name, "pass": bool(passed), "detail": detail})
    print(("PASS" if passed else "FAIL"), name, "—", detail)


def _find_agg_entry(man: Dict[str, Any]) -> Dict[str, Any] | None:
    for v in man.values():
        if isinstance(v, list):
            for e in v:
                if isinstance(e, dict) and str(e.get("path", "")).endswith(
                    "g2b_accuracy_aggregate.v1.json"
                ):
                    return e
    return None


def main() -> int:
    """Run §2 auto-checks and write evidence JSON.

    Returns:
        0 if all five checks pass; 1 otherwise.
    """
    results: List[Dict[str, Any]] = []
    man = json.loads(MAN.read_text(encoding="utf-8"))
    samples = [
        man["instruction_versions"]["SCORE_SCOPE_V1.md"],
        man["instruction_versions"]["PREFERENCE_V0.md"],
    ]
    agg_e = _find_agg_entry(man)
    if agg_e:
        samples.append(agg_e)

    sha_ok: List[str] = []
    sha_fail: List[str] = []
    for e in samples[:5]:
        rel = str(e["path"])
        exp = str(e["sha256"])
        path = ROOT / rel
        if not path.is_file():
            sha_fail.append(f"missing {rel}")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got.lower() == exp.lower():
            sha_ok.append(rel)
        else:
            sha_fail.append(f"{rel} mismatch")
    _rec(
        results,
        "P1-A1 sha256_sample",
        len(sha_ok) >= 3 and not sha_fail,
        f"matched={sha_ok}; fail={sha_fail}",
    )

    dha = man.get("dual_human_attestation") or {}
    note = str(dha.get("note") or "")
    claimed = dha.get("claimed") or {}
    dha_pass = (
        dha.get("status") == "confirmed"
        and claimed.get("two_distinct_humans") is True
        and claimed.get("independent_blind") is True
        and ("≠" in note or "!=" in note)
        and ("accuracy" in note.lower())
    )
    _rec(
        results,
        "P1-A2 dual_human_attestation",
        dha_pass,
        f"status={dha.get('status')}; note={note[:140]}",
    )

    att = json.loads(ATT.read_text(encoding="utf-8"))
    ack = att.get("acknowledgements") or {}
    sc = json.loads(SC.read_text(encoding="utf-8"))
    agg = json.loads(AGG.read_text(encoding="utf-8"))
    scoped_ok = (
        att.get("decision") == "accept_scoped_g2b_accuracy_claim"
        and ack.get("scoped_g2b_accuracy_claim_only") is True
        and ack.get("not_production_accuracy_certification") is True
        and sc.get("accuracy_claim") is False
        and man.get("accuracy_claim") is False
        and agg.get("accuracy_claim") is False
        and agg.get("scoped_accuracy_claim") is True
    )
    _rec(
        results,
        "P1-A3 scoped_not_product_claim",
        scoped_ok,
        (
            f"decision={att.get('decision')}; "
            f"product={[sc.get('accuracy_claim'), man.get('accuracy_claim'), agg.get('accuracy_claim')]}; "
            f"scoped={agg.get('scoped_accuracy_claim')}"
        ),
    )

    hits: List[str] = []
    for search_root in (
        ROOT / "docs/a3",
        REPO / "aiPlat-management/frontend/src/pages/Eval",
    ):
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if not path.is_file():
                continue
            if "_archive" in path.parts or "fixtures" in path.parts:
                continue
            if path.suffix.lower() not in {".md", ".json", ".tsx", ".ts", ".py"}:
                continue
            if path.name in META_DOCS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                for pat in PATTERNS:
                    if pat not in line:
                        continue
                    window = "\n".join(lines[max(0, i - 3) : i + 2])
                    if any(c in window for c in FORBID_CUES):
                        continue
                    rel = (
                        str(path.relative_to(REPO))
                        if REPO in path.parents
                        else str(path)
                    )
                    hits.append(f"{rel}:{i}:{pat}")
    _rec(
        results,
        "P1-A4 forbidden_claims_scan",
        len(hits) == 0,
        f"hits={len(hits)} sample={hits[:8]}",
    )

    prod = (sc.get("axes") or {}).get("production_independence") or {}
    need = {"staging", "B4-S", "B5", "B6", "SPLIT_CHECKLIST"}
    gaps = set(prod.get("gaps") or [])
    prod_ok = (
        prod.get("score") is None
        and prod.get("scored_in_v1") is False
        and need.issubset(gaps)
        and sc.get("process_split_authorized") is False
    )
    _rec(
        results,
        "P1-A5 production_unscored",
        prod_ok,
        (
            f"score={prod.get('score')}; scored_in_v1={prod.get('scored_in_v1')}; "
            f"gaps={sorted(gaps)}; authorize={sc.get('process_split_authorized')}"
        ),
    )

    all_pass = all(r["pass"] for r in results)
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    out = {
        "schema": "eval.phase1.auto_check.v0",
        "checked_at": now,
        "accuracy_claim": False,
        "not_dual_human_signoff": True,
        "honesty": (
            "Engineering auto-check of PHASE1_AUDIT_WORKSHEET §2 items 1–5. "
            "Does NOT replace dual-human sign-off. "
            "Does NOT authorize claiming 首版 5/5 已审计通过."
        ),
        "all_pass": all_pass,
        "results": results,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("---")
    print(
        json.dumps(
            {"all_pass": all_pass, "wrote": str(OUT.relative_to(ROOT)), "checked_at": now},
            ensure_ascii=False,
        )
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
