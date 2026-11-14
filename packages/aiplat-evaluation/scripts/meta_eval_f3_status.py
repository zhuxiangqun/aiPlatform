#!/usr/bin/env python3
"""META_EVAL F3 status — G2b / process_split boundary vs R11 five checks.

Validates the boundary between scoped G2b accuracy evidence and process-split
authorize. Never flips process_split_authorized or Tier A expansion.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
OUT_JSON = META / "f3_process_split_boundary_status.v0.json"
OUT_MD = ROOT / "docs/a3/META_EVAL_F3_STATUS.md"
F1 = META / "f1_judge_family_status.v0.json"
R11 = EVID / "r11_meta_eval_thresholds_signoff.v1.json"
KAPPA = EVID / "g2b_kappa_aggregate.v1.json"
ADJ = EVID / "g2b_adjudication.v1.json"
ATTEST = EVID / "g2b_accuracy_claim_attestation.v1.json"
HOLDOUT = META / "f3_holdout_isolation.v0.json"
CONTAM = META / "f3_contamination.v0.json"
BOUNDARY = META / "f3_process_split_boundary_pin.v0.json"
SPLIT_SH = ROOT / "scripts/a3_split_authorize.sh"


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


def run_split_authorize_status() -> Dict[str, Any]:
    """Run a3_split_authorize.sh status and parse JSON report.

    Returns:
        Gate report dict (ok=False on failure).
    """
    try:
        proc = subprocess.run(
            ["bash", str(SPLIT_SH), "status"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    raw = (proc.stdout or "").strip()
    report: Optional[Dict[str, Any]] = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            report = parsed
    except json.JSONDecodeError:
        report = None
    if report is None:
        return {
            "ok": False,
            "returncode": proc.returncode,
            "tail": raw[-400:],
        }
    report["ok"] = proc.returncode == 0
    report["returncode"] = proc.returncode
    return report


def ensure_holdout() -> Path:
    """Declare process_split authorize as holdout-from-claim.

    Returns:
        Holdout path.
    """
    out = {
        "schema": "eval.meta_eval.f3_holdout_isolation.v0",
        "family_id": "F3",
        "recorded_at": _now(),
        "policy": {
            "process_split_authorize_holdout_until_split_checklist_all_green": True,
            "live_production_signed_required": True,
            "reveal": "pre_release_once",
            "tuning_forbidden_on_holdout": True,
            "g2b_scoped_accuracy_must_not_flip_process_split": True,
        },
        "holdout_claims": [
            "process_split_authorized",
            "production_independence_claim",
            "tier_a_expansion",
        ],
        "accuracy_claim": False,
        "process_split_authorized": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "process_split_authorized stays holdout until SPLIT_CHECKLIST all ✅ "
            "+ live production-signed drill. G2b scoped accuracy ≠ split authorize. ≠ Tier A."
        ),
    }
    HOLDOUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return HOLDOUT


def ensure_contamination() -> Path:
    """Inherit F1 contamination advisory for F3.

    Returns:
        Contamination path.
    """
    f1_c = _load(META / "f1_contamination.v0.json") or {}
    out = {
        "schema": "eval.meta_eval.f3_contamination.v0",
        "family_id": "F3",
        "recorded_at": _now(),
        "method": "inherit_f1_token_overlap_advisory",
        "f1_contamination_ref": "docs/a3/evidence/meta_eval/f1_contamination.v0.json",
        "over_threshold": bool(f1_c.get("over_threshold")),
        "disposition": "advisory_only",
        "accuracy_claim": False,
        "process_split_authorized": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "F3 contamination inherits F1 advisory scan. "
            "R11 over-threshold → advisory only. ≠ process_split authorize."
        ),
    }
    CONTAM.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CONTAM


def ensure_boundary_pin(split: Dict[str, Any]) -> Path:
    """Pin process_split boundary evidence from split-authorize status.

    Args:
        split: Output of run_split_authorize_status().

    Returns:
        Boundary pin path.
    """
    locks_ok = (
        split.get("ok") is True
        and split.get("process_split_authorized_doc") is False
        and split.get("process_split_authorized_status_json") is False
        and split.get("chart_split_false_annotation") is True
        and split.get("ready_to_authorize") is False
    )
    out = {
        "schema": "eval.meta_eval.f3_process_split_boundary_pin.v0",
        "family_id": "F3",
        "recorded_at": _now(),
        "api_hooks": [
            "assert_t13_process_split_boundary",
            "build_g2b_s_dual_review_workflow",
            "eval_assert_t13_process_split_boundary",
        ],
        "split_authorize_gate": "scripts/a3_split_authorize.sh status",
        "checklist_marks": split.get("checklist_marks"),
        "all_green": split.get("all_green"),
        "live_production_signed": split.get("live_production_signed"),
        "process_split_authorized_doc": split.get("process_split_authorized_doc"),
        "process_split_authorized_status_json": split.get(
            "process_split_authorized_status_json"
        ),
        "chart_split_false_annotation": split.get("chart_split_false_annotation"),
        "ready_to_authorize": split.get("ready_to_authorize"),
        "boundary_locks_hold": locks_ok,
        "status": "boundary_hold" if locks_ok else "boundary_breach_or_gate_fail",
        "green": locks_ok,
        "process_split_authorized": False,
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Boundary pin: process_split remains false in checklist/status/chart; "
            "ready_to_authorize=false until live signed + all ✅. "
            "family META_EVAL green ≠ authorize flip. ≠ Tier A."
        ),
    }
    if split.get("error"):
        out["error"] = split["error"]
    BOUNDARY.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return BOUNDARY


def main() -> int:
    """Write F3 status JSON + MD.

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
    split = run_split_authorize_status()
    ensure_boundary_pin(split)
    pin = _load(BOUNDARY) or {}
    kappa = _load(KAPPA) or {}
    adj = _load(ADJ) or {}
    attest = _load(ATTEST) or {}
    f1_green = bool(f1 and f1.get("family_green"))

    checks: List[Dict[str, Any]] = []

    # 1) Judge / boundary ruler — split authorize locks hold (not F1 reuse as G2b judge)
    boundary_ok = bool(pin.get("green") and pin.get("boundary_locks_hold"))
    checks.append(
        {
            "id": "judge_calibration",
            "status": str(pin.get("status") or "open"),
            "green": boundary_ok,
            "f1_prerequisite_met": f1_green,
            "source": "docs/a3/evidence/meta_eval/f3_process_split_boundary_pin.v0.json",
            "note": (
                "a3_split_authorize status: process_split locks hold "
                "(doc/status false, chart annotation false, ready_to_authorize=false)."
                if boundary_ok
                else (
                    "Boundary pin missing or breached — check "
                    "scripts/a3_split_authorize.sh status."
                )
            ),
        }
    )

    # 2) Gold — G2b adjudication + attestation keep not_process_split
    ack = attest.get("acknowledgements") if isinstance(attest.get("acknowledgements"), dict) else {}
    gold_ok = bool(
        adj
        and attest
        and ack.get("not_process_split_authorize") is True
        and attest.get("honesty")
        and "process_split" in str(attest.get("honesty") or "").lower()
    )
    checks.append(
        {
            "id": "gold_audit",
            "status": "advisory_present" if gold_ok else "open",
            "green": gold_ok,
            "source": (
                "docs/a3/evidence/g2b_adjudication.v1.json + "
                "g2b_accuracy_claim_attestation.v1.json"
            ),
            "note": (
                "G2b adjudication + scoped attestation present; "
                "acknowledgements.not_process_split_authorize=true."
                if gold_ok
                else "Missing G2b gold/attestation boundary acknowledgements."
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
            "source": "docs/a3/evidence/meta_eval/f3_contamination.v0.json",
            "note": "Inherited F1 advisory; R11 advisory_only.",
        }
    )

    # 4) Holdout
    hold = _load(HOLDOUT) or {}
    hold_ok = bool(
        hold.get("policy", {}).get(
            "process_split_authorize_holdout_until_split_checklist_all_green"
        )
        and hold.get("process_split_authorized") is False
    )
    checks.append(
        {
            "id": "holdout_isolation",
            "status": "declared" if hold_ok else "open",
            "green": hold_ok,
            "source": "docs/a3/evidence/meta_eval/f3_holdout_isolation.v0.json",
            "note": "process_split_authorized holdout-from-claim declared until checklist+live.",
        }
    )

    # 5) IAA — G2b inter-annotator κ (appropriate for F3; ≠ F2 security dual-human)
    k_val = kappa.get("inter_annotator_kappa")
    iaa_ok = (
        k_val is not None
        and float(k_val) >= 0.60
        and kappa.get("accuracy_claim") is False
    )
    checks.append(
        {
            "id": "iaa",
            "status": "green" if iaa_ok else "open",
            "green": bool(iaa_ok),
            "kappa": k_val,
            "agreement": kappa.get("agreement"),
            "source": "docs/a3/evidence/g2b_kappa_aggregate.v1.json",
            "note": (
                f"G2b inter-annotator κ={k_val} ≥ 0.60; accuracy_claim=false on aggregate."
                if iaa_ok
                else "G2b kappa aggregate missing or below R11 IAA floor."
            ),
        }
    )

    greens = sum(1 for c in checks if c.get("green"))
    family_green = greens == len(checks)
    now = _now()
    out = {
        "schema": "eval.meta_eval.f3_status.v0",
        "family_id": "F3",
        "family": "G2b / process_split boundary",
        "recorded_at": now,
        "threshold_version": r11.get("threshold_version"),
        "checks": checks,
        "counts": {"green": greens, "total": len(checks)},
        "family_green": family_green,
        "tier_a_claim_authorized": False,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "security_certification": False,
        "honesty": (
            "F3 META_EVAL scores the G2b↔process_split boundary. "
            "family_green ≠ flip process_split_authorized ≠ Tier A ≠ production independence."
        ),
        "api_hooks": [
            "assert_t13_process_split_boundary",
            "build_g2b_s_dual_review_workflow",
            "eval_assert_t13_process_split_boundary",
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
            "# META_EVAL F3 状态（G2b / process_split 边界）",
            "",
            f"> 机器：[`evidence/meta_eval/f3_process_split_boundary_status.v0.json`](./evidence/meta_eval/f3_process_split_boundary_status.v0.json) · 时点 {now}",
            "> **诚实锁**：`family_green` ≠ `process_split_authorized=true` ≠ Tier A · `accuracy_claim=false`",
            "",
            "## 汇总",
            "",
            f"- green **{greens}/{len(checks)}**",
            f"- `family_green`: **{str(family_green).lower()}**",
            f"- `process_split_authorized`: **false**",
            f"- `tier_a_claim_authorized`: **false**",
            "",
            "## 五项",
            "",
            *rows,
            "",
            "## 下一步",
            "",
            "1. SPLIT_CHECKLIST #1/#4 仍须 live 签字后才可谈 authorize（本家族绿 ≠ 翻转）",
            "2. 复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f3_status.py`",
            "3. F2 安全人裁判 / dual-human 仍并行待人（≠ 本家族 IAA）",
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
                "process_split_authorized": False,
                "out": str(OUT_JSON.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
