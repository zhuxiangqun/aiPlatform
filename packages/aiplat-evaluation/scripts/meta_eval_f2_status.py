#!/usr/bin/env python3
"""META_EVAL F2 status — security family gates vs R11 five checks.

F1 judge green is a prerequisite note only — security judge calibration is a
separate ruler and stays open until security-specific human evidence exists.
Never authorizes Tier A / L5 declare / accuracy_claim / process_split.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
OUT_JSON = META / "f2_security_family_status.v0.json"
OUT_MD = ROOT / "docs/a3/META_EVAL_F2_STATUS.md"
F1 = META / "f1_judge_family_status.v0.json"
R11 = EVID / "r11_meta_eval_thresholds_signoff.v1.json"
S1_AGG = EVID / "s1_prod_model_aggregate.v1.json"
HOLDOUT = META / "f2_holdout_isolation.v0.json"
CONTAM = META / "f2_contamination.v0.json"
SEC_JUDGE = META / "f2_security_judge_pack_pin.v0.json"
DUAL = META / "f2_security_dual_human.worksheet.v0.json"


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


def _now() -> str:
    """+08:00 timestamp.

    Returns:
        Timestamp string.
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def ensure_holdout() -> Path:
    """Declare L5/certification axes as holdout-from-claim.

    Returns:
        Holdout path.
    """
    out = {
        "schema": "eval.meta_eval.f2_holdout_isolation.v0",
        "family_id": "F2",
        "recorded_at": _now(),
        "policy": {
            "l5_declare_holdout_until_meta_eval_green": True,
            "security_certification_holdout": True,
            "reveal": "pre_release_once",
            "tuning_forbidden_on_holdout": True,
        },
        "holdout_claims": [
            "l5_declare_allowed_families",
            "security_certification",
            "accuracy_claim",
        ],
        "accuracy_claim": False,
        "security_certification": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "L5 declare / security certification stay holdout-from-claim until "
            "F2 META_EVAL family_green AND explicit owner authorize. ≠ Tier A."
        ),
    }
    HOLDOUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return HOLDOUT


def ensure_contamination() -> Path:
    """Inherit F1 contamination advisory for F2.

    Returns:
        Contamination path.
    """
    f1_c = _load(META / "f1_contamination.v0.json") or {}
    out = {
        "schema": "eval.meta_eval.f2_contamination.v0",
        "family_id": "F2",
        "recorded_at": _now(),
        "method": "inherit_f1_token_overlap_advisory",
        "f1_contamination_ref": "docs/a3/evidence/meta_eval/f1_contamination.v0.json",
        "over_threshold": bool(f1_c.get("over_threshold")),
        "disposition": "advisory_only",
        "accuracy_claim": False,
        "security_certification": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "F2 contamination inherits F1 advisory scan. "
            "R11 over-threshold → advisory only. ≠ security certification."
        ),
    }
    CONTAM.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CONTAM


def ensure_security_judge_pin() -> Path:
    """Pin security judge pack placeholder (pending human security ratings).

    Returns:
        Pin path.
    """
    existing = _load(SEC_JUDGE)
    # Keep scored green, scored-below-threshold, or worksheet-pointing pending pins.
    if existing and (
        (existing.get("status") == "scored" and existing.get("green"))
        or existing.get("ratings_path")
        or str(existing.get("status") or "").startswith("scored")
    ):
        return SEC_JUDGE
    out = {
        "schema": "eval.meta_eval.f2_security_judge_pack_pin.v0",
        "family_id": "F2",
        "recorded_at": _now(),
        "api_hooks": [
            "evaluate_security_judge_calibration",
            "evaluate_security_family_gates",
            "evaluate_security_severity_l5_gate",
            "build_judge_calib_evidence_pack",
        ],
        "f1_prerequisite_note": "F1 META_EVAL green is necessary but not sufficient for F2 judge",
        "ratings_path": None,
        "agreement": None,
        "kappa": None,
        "ece": None,
        "asr_status": None,
        "status": "pending_security_human_judge",
        "green": False,
        "judge_kind": "human",
        "accuracy_claim": False,
        "security_certification": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Security judge calibration pending. Do not reuse F1 G2b human_judge "
            "pack as security family green. ≠ L5 declare."
        ),
    }
    SEC_JUDGE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return SEC_JUDGE


def main() -> int:
    """Write F2 status JSON + MD.

    Returns:
        0 on success.
    """
    META.mkdir(parents=True, exist_ok=True)
    r11 = _load(R11)
    f1 = _load(F1)
    if not r11:
        print("missing R11 signoff", file=sys.stderr)
        return 1

    ensure_holdout()
    ensure_contamination()
    ensure_security_judge_pin()
    pin = _load(SEC_JUDGE) or {}
    s1 = _load(S1_AGG) or {}
    f1_green = bool(f1 and f1.get("family_green"))

    checks: List[Dict[str, Any]] = []

    # 1) Security judge calibration — NOT auto from F1
    sec_metrics_ok = (
        pin.get("agreement") is not None
        and pin.get("kappa") is not None
        and pin.get("ece") is not None
        and float(pin["agreement"]) >= 0.8
        and float(pin["kappa"]) >= 0.6
        and float(pin["ece"]) <= 0.1
        and bool(pin.get("green"))
        and str(pin.get("status") or "") == "scored"
        and "pending" not in str(pin.get("honesty") or "").lower()
        and "ai" not in str(pin.get("ratings_path") or "").lower()
    )
    checks.append(
        {
            "id": "judge_calibration",
            "status": "green" if sec_metrics_ok else str(pin.get("status") or "open"),
            "green": bool(sec_metrics_ok),
            "f1_prerequisite_met": f1_green,
            "source": "docs/a3/evidence/meta_eval/f2_security_judge_pack_pin.v0.json",
            "note": (
                "Security human judge metrics meet R11."
                if sec_metrics_ok
                else (
                    "Pending security-specific human judge ratings "
                    f"(F1 prerequisite={'met' if f1_green else 'MISSING'}; "
                    "F1 ≠ F2 security judge)."
                )
            ),
        }
    )

    # 2) Gold audit — S1 aggregate honesty locks present (local, not cert)
    gold_ok = bool(
        s1
        and s1.get("accuracy_claim") is False
        and s1.get("not_security_certification") is True
        and s1.get("process_split_authorized") is False
    )
    checks.append(
        {
            "id": "gold_audit",
            "status": "advisory_present" if gold_ok else "open",
            "green": gold_ok,
            "source": "docs/a3/evidence/s1_prod_model_aggregate.v1.json",
            "note": (
                "S1 aggregate present with honesty locks "
                "(accuracy_claim=false, not_security_certification=true)."
                if gold_ok
                else "Missing S1 honesty aggregate for F2 gold slot."
            ),
        }
    )

    # 3) Contamination
    cont = _load(CONTAM) or {}
    checks.append(
        {
            "id": "contamination",
            "status": str(cont.get("disposition") or "ran"),
            "green": True,
            "over_threshold": bool(cont.get("over_threshold")),
            "source": "docs/a3/evidence/meta_eval/f2_contamination.v0.json",
            "note": "Inherited F1 advisory; R11 advisory_only.",
        }
    )

    # 4) Holdout
    hold = _load(HOLDOUT) or {}
    hold_ok = bool(hold.get("policy", {}).get("security_certification_holdout"))
    checks.append(
        {
            "id": "holdout_isolation",
            "status": "declared" if hold_ok else "open",
            "green": hold_ok,
            "source": "docs/a3/evidence/meta_eval/f2_holdout_isolation.v0.json",
            "note": "L5 declare / security certification holdout-from-claim declared.",
        }
    )

    # 5) IAA — security dual-human (F1 G2b κ ≠ this pack)
    dual = _load(DUAL) or {}
    dual_reviews = dual.get("reviews") if isinstance(dual.get("reviews"), list) else []
    dual_complete = bool(dual_reviews) and all(
        isinstance(r, dict)
        and str(r.get("reviewer_a") or "").strip()
        and str(r.get("reviewer_b") or "").strip()
        and str(r.get("reviewer_a") or "").strip() != str(r.get("reviewer_b") or "").strip()
        and r.get("independent_blind") is True
        and (
            r.get("agree") is True
            or (
                r.get("agree") is False
                and str(r.get("arbiter") or "").strip()
                and str(r.get("arbiter_decision") or "").strip()
            )
        )
        for r in dual_reviews
    )
    dual_ok = bool(
        dual_complete
        and dual.get("green") is True
        and str(dual.get("status") or "") in {"attested", "green", "scored"}
        and dual.get("security_certification") is not True
    )
    checks.append(
        {
            "id": "iaa",
            "status": "green" if dual_ok else str(dual.get("status") or "pending_security_dual_human"),
            "green": dual_ok,
            "source": "docs/a3/evidence/meta_eval/f2_security_dual_human.worksheet.v0.json",
            "note": (
                "Security failure dual-human attestation complete."
                if dual_ok
                else (
                    "F1 G2b IAA must not substitute security dual_human_on_failures. "
                    "Fill f2_security_dual_human.worksheet then set status=attested green=true."
                )
            ),
        }
    )

    greens = sum(1 for c in checks if c.get("green"))
    family_green = greens == len(checks)
    now = _now()
    out = {
        "schema": "eval.meta_eval.f2_status.v0",
        "family_id": "F2",
        "family": "Security family gates",
        "recorded_at": now,
        "threshold_version": r11.get("threshold_version"),
        "checks": checks,
        "counts": {"green": greens, "total": len(checks)},
        "family_green": family_green,
        "tier_a_claim_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "process_split_authorized": False,
        "l5_declare_authorized": False,
        "honesty": (
            "F2 partial until security judge + dual-human IAA land. "
            "family_green ≠ L5 declare ≠ Tier A."
        ),
        "api_hooks": [
            "evaluate_security_family_gates",
            "evaluate_security_judge_calibration",
            "evaluate_security_severity_l5_gate",
        ],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = ["| 检查 | 状态 | green | 说明 |", "|---|---|:---:|---|"]
    for c in checks:
        rows.append(
            f"| `{c['id']}` | {c['status']} | {'✅' if c.get('green') else '❌'} | {c.get('note', '')} |"
        )
    md = "\n".join(
        [
            "---",
            "doc_type: Reference",
            "---",
            "",
            "# META_EVAL F2 状态（Security family）",
            "",
            f"> 机器：[`evidence/meta_eval/f2_security_family_status.v0.json`](./evidence/meta_eval/f2_security_family_status.v0.json) · 时点 {now}",
            "> **诚实锁**：`family_green` ≠ L5 declare ≠ Tier A · `accuracy_claim=false` · `security_certification=false`",
            "",
            "## 汇总",
            "",
            f"- green **{greens}/{len(checks)}**",
            f"- `family_green`: **{str(family_green).lower()}**",
            f"- `tier_a_claim_authorized`: **false**",
            f"- `l5_declare_authorized`: **false**",
            "",
            "## 五项",
            "",
            *rows,
            "",
            "## 下一步（仍须人 / 安全专项）",
            "",
            "1. 填写说明：[`META_EVAL_F2_HUMAN_FILL.md`](./META_EVAL_F2_HUMAN_FILL.md)",
            "2. 填安全裁判 worksheet → `meta_eval_f2_prep.py --score`",
            "3. 填 dual-human worksheet → `status=attested` `green=true`",
            "4. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f2_status.py`",
            "",
        ]
    )
    OUT_MD.write_text(md + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "family_green": family_green,
                "green": greens,
                "total": len(checks),
                "out": str(OUT_JSON.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
