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
    """Judge↔human calibration — no frozen pack with ECE yet.

    Args:
        thr: R11 thresholds blob.

    Returns:
        Check result dict (intentionally not green without evidence).
    """
    jc = thr.get("judge_calibration") or {}
    return {
        "id": "judge_calibration",
        "status": "open",
        "green": False,
        "agreement": None,
        "kappa": None,
        "ece": None,
        "thresholds": {
            "agreement_min": jc.get("agreement_min"),
            "kappa_min": jc.get("kappa_min"),
            "ece_max": jc.get("ece_max"),
        },
        "source": None,
        "note": (
            "No frozen judge↔human ratings pack with ECE in evidence/meta_eval/. "
            "G2b IAA must not be reused as judge calibration green. "
            "Next: open_capability_judge_calibration + dual ratings → "
            "evaluate_judge_calibration_gate + ECE artifact."
        ),
        "api_hooks": [
            "evaluate_judge_calibration_gate",
            "open_capability_judge_calibration",
            "cohen_kappa_binary",
        ],
    }


def _check_gold(adj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gold audit presence — adjudication exists ≠ error-rate certified.

    Args:
        adj: g2b_adjudication document or None.

    Returns:
        Check result dict.
    """
    if not adj:
        return {
            "id": "gold_audit",
            "status": "open",
            "green": False,
            "note": "missing g2b_adjudication",
        }
    return {
        "id": "gold_audit",
        "status": "advisory_present",
        "green": False,
        "source": "docs/a3/evidence/g2b_adjudication.v1.json",
        "note": (
            "Adjudication artifact present; sample error-rate ≤5% not yet "
            "measured for META_EVAL F1 — keep blocked."
        ),
    }


def _check_contamination() -> Dict[str, Any]:
    """Contamination — not run for F1 yet.

    Returns:
        Check result dict.
    """
    return {
        "id": "contamination",
        "status": "not_run",
        "green": False,
        "note": "No contamination overlap report for F1 family; R11 over-threshold=advisory_only",
    }


def _check_holdout(freeze: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Holdout isolation declaration from freeze record if any.

    Args:
        freeze: g2b_freeze_record or None.

    Returns:
        Check result dict.
    """
    if not freeze:
        return {
            "id": "holdout_isolation",
            "status": "open",
            "green": False,
            "note": "missing freeze record",
        }
    return {
        "id": "holdout_isolation",
        "status": "declared_local",
        "green": False,
        "source": "docs/a3/evidence/g2b_freeze_record.v1.json",
        "freeze_status": freeze.get("status"),
        "note": (
            "Freeze confirmed for G2b pack; META_EVAL still requires explicit "
            "dev/val/holdout split declaration for Tier A family — not green."
        ),
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
            "## 下一步（开 judge 绿灯）",
            "",
            "1. 固定人标 pack 指纹 + seed（禁止边调边改）",
            "2. `open_capability_judge_calibration` → 双人/人机 ratings",
            "3. `evaluate_judge_calibration_gate` + κ/ECE 写入 `evidence/meta_eval/`",
            "4. 补 gold 抽样错误率、contamination 报告、holdout 三分声明",
            "",
            "复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f1_status.py`",
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
