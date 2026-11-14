#!/usr/bin/env python3
"""META_EVAL F1 status — judge-family five checks vs R11 thresholds.

Reads existing G2b IAA aggregate for inter-annotator only. Does NOT invent
judge↔human agreement/ECE. Never sets Tier A / accuracy_claim / authorize.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META_DIR = EVID / "meta_eval"
OUT_JSON = META_DIR / "f1_judge_family_status.v0.json"
OUT_MD = ROOT / "docs/a3/META_EVAL_F1_STATUS.md"
R11 = EVID / "r11_meta_eval_thresholds_signoff.v1.json"
G2B_KAPPA = EVID / "g2b_kappa_aggregate.v1.json"
G2B_ADJ = EVID / "g2b_adjudication.v1.json"
G2B_FREEZE = EVID / "g2b_freeze_record.v1.json"
JUDGE_PIN = META_DIR / "f1_judge_pack_pin.v0.json"
GOLD_SAMPLE = META_DIR / "f1_gold_audit_sample.v0.json"
CONTAM = META_DIR / "f1_contamination.v0.json"
HOLDOUT = META_DIR / "f1_holdout_isolation.v0.json"


def _load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _check_iaa(thr: Dict[str, Any], kappa_doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map G2b inter-annotator κ into META_EVAL IAA slot.

    Args:
        thr: R11 thresholds blob.
        kappa_doc: g2b_kappa_aggregate document or None.

    Returns:
        Check result dict.
    """
    kmin = float((thr.get("inter_annotator") or {}).get("kappa_min") or 0.6)
    amin = float((thr.get("judge_calibration") or {}).get("agreement_min") or 0.8)
    if not kappa_doc:
        return {
            "id": "iaa",
            "status": "open",
            "green": False,
            "note": "missing g2b_kappa_aggregate",
        }
    agreement = kappa_doc.get("agreement")
    kappa = kappa_doc.get("inter_annotator_kappa")
    ok_a = agreement is not None and float(agreement) >= amin
    ok_k = kappa is not None and float(kappa) >= kmin
    green = bool(ok_a and ok_k)
    return {
        "id": "iaa",
        "status": "green" if green else "below_threshold",
        "green": green,
        "agreement": agreement,
        "kappa": kappa,
        "thresholds": {"agreement_min": amin, "kappa_min": kmin},
        "source": "docs/a3/evidence/g2b_kappa_aggregate.v1.json",
        "note": "IAA only — not judge↔human calibration",
    }


def _check_judge(thr: Dict[str, Any]) -> Dict[str, Any]:
    """Judge↔human calibration — pack pin ≠ green without ratings/ECE.

    Args:
        thr: R11 thresholds blob.

    Returns:
        Check result dict (intentionally not green without evidence).
    """
    jc = thr.get("judge_calibration") or {}
    pin = _load(JUDGE_PIN)
    base = {
        "id": "judge_calibration",
        "thresholds": {
            "agreement_min": jc.get("agreement_min"),
            "kappa_min": jc.get("kappa_min"),
            "ece_max": jc.get("ece_max"),
        },
        "api_hooks": [
            "evaluate_judge_calibration_gate",
            "open_capability_judge_calibration",
            "cohen_kappa_binary",
        ],
    }
    if not pin:
        return {
            **base,
            "status": "open",
            "green": False,
            "source": None,
            "note": "Run meta_eval_f1_prep.py to pin pack; then collect ratings+ECE.",
        }
    agreement = pin.get("agreement")
    kappa = pin.get("kappa")
    ece = pin.get("ece")
    amin = float(jc.get("agreement_min") or 0.8)
    kmin = float(jc.get("kappa_min") or 0.6)
    emax = float(jc.get("ece_max") or 0.1)
    metrics_ok = (
        agreement is not None
        and kappa is not None
        and ece is not None
        and float(agreement) >= amin
        and float(kappa) >= kmin
        and float(ece) <= emax
    )
    status = str(pin.get("status") or "pending_ratings")
    judge_kind = str(pin.get("judge_kind") or "human").lower()
    ratings_path = str(pin.get("ratings_path") or "")
    # paths in pin are relative to package root (docs/a3/...)
    ratings_doc = _load(ROOT / ratings_path) if ratings_path else None
    ratings_kind = str((ratings_doc or {}).get("judge_kind") or "").lower()
    ratings_judge_id = str((ratings_doc or {}).get("judge_id") or "").lower()
    ratings_honesty = str((ratings_doc or {}).get("honesty") or "").lower()
    ratings_status = str((ratings_doc or {}).get("status") or "").lower()
    honesty = str(pin.get("honesty") or "").lower()
    path_l = ratings_path.lower()
    path_looks_ai = any(
        x in path_l
        for x in (
            "ai_precheck",
            "ai.precheck",
            "ai_judge",
            "plus_ai",
            "human_plus_ai",
        )
    )
    ratings_looks_ai = (
        ratings_kind in {"ai", "llm", "model"}
        or ratings_kind.startswith("ai.")
        or "precheck" in ratings_kind
        or "ai." in ratings_judge_id
        or "precheck" in ratings_judge_id
        or "ai precheck" in ratings_honesty
        or "not a human judge" in ratings_honesty
        or "pending" in ratings_status
        or "ai_judge" in ratings_status
        or bool((ratings_doc or {}).get("precheck_green"))
    )
    honesty_blocks = (
        "pending" in honesty
        or "ai precheck" in honesty
        or "judge side ai" in honesty
        or "still pending" in honesty
    )
    # AI / precheck / pending_human never counts as META_EVAL judge green.
    human_ok = (
        bool(pin.get("green"))
        and judge_kind in {"human", "dual_human"}
        and ("pending" not in status and "ai_" not in status and "precheck" not in status)
        and not path_looks_ai
        and not ratings_looks_ai
        and not honesty_blocks
        and ratings_doc is not None
        and bool((ratings_doc or {}).get("green")) is True
    )
    green = bool(metrics_ok and human_ok)
    if metrics_ok and not human_ok:
        note = (
            f"Metrics meet R11 numerically (agreement={agreement}, κ={kappa}, "
            f"ECE={ece}) but human evidence incomplete: status={status!r} "
            f"judge_kind={judge_kind!r} ratings_path={ratings_path!r} "
            f"ratings_judge_kind={ratings_kind!r}. "
            "Need human ratings file (not ai_precheck) + honesty without pending."
        )
    elif not metrics_ok:
        note = (
            "Pack pinned; ratings/ECE missing or below threshold — not green. "
            "Do not reuse G2b IAA as judge calibration."
        )
    else:
        note = "Judge↔human metrics meet R11 thresholds (report-only)."
    return {
        **base,
        "status": "green" if green else status,
        "green": green,
        "agreement": agreement,
        "kappa": kappa,
        "ece": ece,
        "precheck_green": pin.get("precheck_green"),
        "judge_kind": judge_kind,
        "ratings_path": ratings_path or None,
        "source": "docs/a3/evidence/meta_eval/f1_judge_pack_pin.v0.json",
        "note": note,
    }


def _check_gold(adj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gold audit — needs completed human re-audit sample ≤5% error.

    Args:
        adj: g2b_adjudication document or None.

    Returns:
        Check result dict.
    """
    sample = _load(GOLD_SAMPLE)
    if sample:
        rate = sample.get("sample_error_rate")
        pending = sample.get("status") == "pending_human_reaudit" or rate is None
        if not pending and rate is not None:
            thr = float(sample.get("threshold_sample_error_rate_max") or 0.05)
            green = float(rate) <= thr
            return {
                "id": "gold_audit",
                "status": "green" if green else "above_threshold",
                "green": green,
                "sample_error_rate": rate,
                "source": "docs/a3/evidence/meta_eval/f1_gold_audit_sample.v0.json",
                "note": "Human re-audit sample scored against R11 gold_audit threshold.",
            }
        return {
            "id": "gold_audit",
            "status": "pending_human_reaudit",
            "green": False,
            "source": "docs/a3/evidence/meta_eval/f1_gold_audit_sample.v0.json",
            "note": (
                f"Seeded sample_n={sample.get('sample_n')} ready; "
                "fill reaudit_* then recompute sample_error_rate."
            ),
        }
    if not adj:
        return {
            "id": "gold_audit",
            "status": "open",
            "green": False,
            "note": "missing adjudication and gold sample worksheet",
        }
    return {
        "id": "gold_audit",
        "status": "advisory_present",
        "green": False,
        "source": "docs/a3/evidence/g2b_adjudication.v1.json",
        "note": "Adjudication present; run meta_eval_f1_prep.py for re-audit sample.",
    }


def _check_contamination() -> Dict[str, Any]:
    """Contamination — green when scan artifact exists (R11 advisory-only).

    Returns:
        Check result dict.
    """
    doc = _load(CONTAM)
    if not doc:
        return {
            "id": "contamination",
            "status": "not_run",
            "green": False,
            "note": "Run meta_eval_f1_prep.py to emit f1_contamination.v0.json",
        }
    return {
        "id": "contamination",
        "status": str(doc.get("disposition") or "ran"),
        "green": True,
        "over_threshold": bool(doc.get("over_threshold")),
        "source": "docs/a3/evidence/meta_eval/f1_contamination.v0.json",
        "note": (
            "Scan ran; over-threshold is advisory_only per R11 "
            f"(over_threshold={bool(doc.get('over_threshold'))})."
        ),
    }


def _check_holdout(freeze: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Holdout isolation — green when explicit split declaration is on file.

    Args:
        freeze: g2b_freeze_record or None.

    Returns:
        Check result dict.
    """
    decl = _load(HOLDOUT)
    if decl and decl.get("policy", {}).get("reveal") == "pre_release_once":
        return {
            "id": "holdout_isolation",
            "status": "declared",
            "green": True,
            "source": "docs/a3/evidence/meta_eval/f1_holdout_isolation.v0.json",
            "counts": decl.get("counts"),
            "note": (
                "dev/val/holdout declared; tuning forbidden on holdout; "
                "reveal=pre_release_once. Not a score reveal."
            ),
        }
    if not freeze:
        return {
            "id": "holdout_isolation",
            "status": "open",
            "green": False,
            "note": "missing holdout declaration and freeze record",
        }
    return {
        "id": "holdout_isolation",
        "status": "freeze_only",
        "green": False,
        "source": "docs/a3/evidence/g2b_freeze_record.v1.json",
        "note": "Freeze exists; run meta_eval_f1_prep.py for explicit split declaration.",
    }


def main() -> int:
    """Write F1 status JSON + MD.

    Returns:
        0 on success.
    """
    r11 = _load(R11)
    if not r11:
        print(f"missing R11 signoff: {R11}", file=sys.stderr)
        return 1
    thr = r11.get("thresholds") or {}
    checks = [
        _check_judge(thr),
        _check_gold(_load(G2B_ADJ)),
        _check_contamination(),
        _check_holdout(_load(G2B_FREEZE)),
        _check_iaa(thr, _load(G2B_KAPPA)),
    ]
    greens = sum(1 for c in checks if c.get("green"))
    family_green = greens == len(checks)
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    out: Dict[str, Any] = {
        "schema": "eval.meta_eval.f1_status.v0",
        "family_id": "F1",
        "family": "Judge calibration",
        "recorded_at": now,
        "threshold_version": r11.get("threshold_version"),
        "checks": checks,
        "counts": {"green": greens, "total": len(checks)},
        "family_green": family_green,
        "tier_a_claim_authorized": False,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "honesty": (
            "Partial evidence only. family_green requires all five checks. "
            "IAA≠judge calibration. ≠ Tier A expansion."
        ),
    }
    META_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        "| 检查 | 状态 | green | 说明 |",
        "|---|---|:---:|---|",
    ]
    for c in checks:
        rows.append(
            f"| `{c['id']}` | {c['status']} | {'✅' if c.get('green') else '❌'} | "
            f"{c.get('note', '')} |"
        )
    md = "\n".join(
        [
            "---",
            "doc_type: Reference",
            "---",
            "",
            "# META_EVAL F1 状态（Judge family）",
            "",
            f"> 机器：[`evidence/meta_eval/f1_judge_family_status.v0.json`](./evidence/meta_eval/f1_judge_family_status.v0.json) · 时点 {now}",
            "> **诚实锁**：`family_green` 须五项全绿；当前 **≠** Tier A 授权 · `accuracy_claim=false`",
            "",
            "## 汇总",
            "",
            f"- green **{greens}/{len(checks)}**",
            f"- `family_green`: **{str(family_green).lower()}**",
            f"- `tier_a_claim_authorized`: **false**",
            "",
            "## 五项",
            "",
            *rows,
            "",
            "## 下一步",
            "",
            (
                "- F1 已 `family_green`：**仍禁止** Tier A 扩容宣称"
                if family_green
                else "- 补齐未绿项后复跑本脚本"
            ),
            "- 下一家族：F4 / F2 / F3（见 [`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)）",
            "",
            "复跑状态：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_status.py`",
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
