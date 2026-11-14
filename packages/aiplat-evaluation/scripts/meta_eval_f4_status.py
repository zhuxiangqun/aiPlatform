#!/usr/bin/env python3
"""META_EVAL F4 status — release scorecard family vs R11 five checks.

Reuses F1 judge/IAA greens and scorecard_v1_check honesty. Never authorizes
Tier A expansion or process_split / product accuracy_claim.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs/a3/evidence"
META = EVID / "meta_eval"
OUT_JSON = META / "f4_release_scorecard_status.v0.json"
OUT_MD = ROOT / "docs/a3/META_EVAL_F4_STATUS.md"
F1 = META / "f1_judge_family_status.v0.json"
CARD = ROOT / "docs/a3/scorecard_v1.json"
MANIFEST = EVID / "evidence_manifest.v1.json"
R11 = EVID / "r11_meta_eval_thresholds_signoff.v1.json"
HOLDOUT = META / "f4_holdout_isolation.v0.json"
CONTAM = META / "f4_contamination.v0.json"


def _load(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON object or None.

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


def ensure_holdout(card: Dict[str, Any]) -> Path:
    """Declare unscored scorecard axes as holdout-from-claim.

    Args:
        card: scorecard_v1.json contents.

    Returns:
        Holdout declaration path.
    """
    axes = card.get("axes") if isinstance(card.get("axes"), dict) else {}
    held = []
    for name, ax in axes.items():
        if not isinstance(ax, dict):
            continue
        if ax.get("score") is None or ax.get("scored_in_v1") is False:
            held.append(
                {
                    "axis": name,
                    "score": ax.get("score"),
                    "gaps": ax.get("gaps") or [],
                    "reason": "unscored_or_null — must not be claimed as release green",
                }
            )
    out = {
        "schema": "eval.meta_eval.f4_holdout_isolation.v0",
        "family_id": "F4",
        "recorded_at": _now(),
        "policy": {
            "unscored_axes_are_holdout_from_claim": True,
            "reveal": "pre_release_once",
            "tuning_forbidden_on_holdout_axes": True,
        },
        "holdout_axes": held,
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "Release scorecard null/unscored axes are holdout-from-claim. "
            "≠ process_split authorize; ≠ Tier A."
        ),
    }
    HOLDOUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return HOLDOUT


def ensure_contamination() -> Path:
    """Record contamination disposition for F4 (inherits F1 + scorecard SHA gate).

    Returns:
        Contamination report path.
    """
    f1_c = _load(META / "f1_contamination.v0.json") or {}
    out = {
        "schema": "eval.meta_eval.f4_contamination.v0",
        "family_id": "F4",
        "recorded_at": _now(),
        "method": "inherit_f1_token_overlap + scorecard_instruction_sha_gate",
        "f1_contamination_ref": "docs/a3/evidence/meta_eval/f1_contamination.v0.json",
        "f1_over_threshold": bool(f1_c.get("over_threshold")),
        "scorecard_gate": "scripts/scorecard_v1_check.sh verifies instruction SHA pins",
        "disposition": "advisory_only",
        "over_threshold": bool(f1_c.get("over_threshold")),
        "accuracy_claim": False,
        "tier_a_claim_authorized": False,
        "honesty": (
            "F4 contamination = F1 advisory scan + scorecard instruction hash gate. "
            "R11 over-threshold → advisory only."
        ),
    }
    CONTAM.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CONTAM


def run_scorecard_check() -> Dict[str, Any]:
    """Run scorecard_v1_check.sh and parse last JSON line if present.

    Returns:
        Result dict with ok bool.
    """
    script = ROOT / "scripts/scorecard_v1_check.sh"
    try:
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    gate = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and '"gate"' in line:
            try:
                gate = json.loads(line)
            except json.JSONDecodeError:
                continue
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "gate": gate,
        "tail": (proc.stdout or "")[-500:],
    }


def main() -> int:
    """Write F4 status JSON + MD.

    Returns:
        0 on success.
    """
    META.mkdir(parents=True, exist_ok=True)
    r11 = _load(R11)
    f1 = _load(F1)
    card = _load(CARD)
    manifest = _load(MANIFEST)
    if not r11 or not card or not manifest:
        print("missing R11/scorecard/manifest", file=sys.stderr)
        return 1

    ensure_holdout(card)
    ensure_contamination()
    sc = run_scorecard_check()

    f1_green = bool(f1 and f1.get("family_green"))
    checks = []

    # 1) Judge — F1 prerequisite for scorecard-linked gates
    checks.append(
        {
            "id": "judge_calibration",
            "status": "green" if f1_green else "blocked_on_f1",
            "green": f1_green,
            "source": "docs/a3/evidence/meta_eval/f1_judge_family_status.v0.json",
            "note": (
                "F1 family_green required before F4 treats judge-linked scorecard claims as calibrated."
                if f1_green
                else "F1 not green — F4 judge check blocked."
            ),
        }
    )

    # 2) Gold audit — scorecard honesty gate + product accuracy false
    gold_ok = bool(
        sc.get("ok")
        and card.get("accuracy_claim") is False
        and manifest.get("accuracy_claim") is False
    )
    checks.append(
        {
            "id": "gold_audit",
            "status": "green" if gold_ok else "fail",
            "green": gold_ok,
            "source": "docs/a3/scorecard_v1.json + scripts/scorecard_v1_check.sh",
            "scorecard_gate": sc.get("gate"),
            "note": (
                "scorecard_v1_check PASS; product accuracy_claim=false; instruction SHA pins verified."
                if gold_ok
                else f"scorecard gate failed: {sc}"
            ),
        }
    )

    # 3) Contamination — advisory report present
    cont = _load(CONTAM) or {}
    checks.append(
        {
            "id": "contamination",
            "status": str(cont.get("disposition") or "ran"),
            "green": True,
            "over_threshold": bool(cont.get("over_threshold")),
            "source": "docs/a3/evidence/meta_eval/f4_contamination.v0.json",
            "note": "Inherited F1 advisory + scorecard SHA gate; R11 advisory_only.",
        }
    )

    # 4) Holdout — unscored axes declared
    hold = _load(HOLDOUT) or {}
    hold_ok = bool(hold.get("holdout_axes") is not None and hold.get("policy"))
    checks.append(
        {
            "id": "holdout_isolation",
            "status": "declared" if hold_ok else "open",
            "green": hold_ok,
            "source": "docs/a3/evidence/meta_eval/f4_holdout_isolation.v0.json",
            "holdout_axes_n": len(hold.get("holdout_axes") or []),
            "note": "Null/unscored scorecard axes are holdout-from-claim (microVM/production).",
        }
    )

    # 5) IAA — dual_human attestation on scorecard evidence
    dual = (manifest.get("dual_human_attestation") or {}) if isinstance(manifest, dict) else {}
    dual_ok = str(dual.get("status") or "").lower() in {"confirmed", "ok", "true"}
    # also accept gate payload
    if not dual_ok and isinstance(sc.get("gate"), dict):
        dual_ok = str(sc["gate"].get("dual_human_attestation") or "").lower() == "confirmed"
    checks.append(
        {
            "id": "iaa",
            "status": "green" if dual_ok else "open",
            "green": dual_ok,
            "source": "docs/a3/evidence/evidence_manifest.v1.json#dual_human_attestation",
            "note": (
                "Scorecard feature-5 dual_human attestation confirmed."
                if dual_ok
                else "dual_human attestation not confirmed on manifest."
            ),
        }
    )

    greens = sum(1 for c in checks if c.get("green"))
    family_green = greens == len(checks)
    now = _now()
    out = {
        "schema": "eval.meta_eval.f4_status.v0",
        "family_id": "F4",
        "family": "Release scorecard",
        "recorded_at": now,
        "threshold_version": r11.get("threshold_version"),
        "checks": checks,
        "counts": {"green": greens, "total": len(checks)},
        "family_green": family_green,
        "tier_a_claim_authorized": False,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "honesty": (
            "F4 wires release scorecard honesty to META_EVAL five checks. "
            "family_green ≠ Tier A expansion authorize."
        ),
        "api_hooks": ["build_release_scorecard", "build_judge_calib_evidence_pack", "scorecard_status"],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = ["| 检查 | 状态 | green | 说明 |", "|---|---|:---:|---|"]
    for c in checks:
        rows.append(
            f"| `{c['id']}` | {c['status']} | {'✅' if c.get('green') else '❌'} | {c.get('note','')} |"
        )
    md = "\n".join(
        [
            "---",
            "doc_type: Reference",
            "---",
            "",
            "# META_EVAL F4 状态（Release scorecard）",
            "",
            f"> 机器：[`evidence/meta_eval/f4_release_scorecard_status.v0.json`](./evidence/meta_eval/f4_release_scorecard_status.v0.json) · 时点 {now}",
            "> **诚实锁**：`family_green` ≠ Tier A 授权 · `accuracy_claim=false` · `process_split_authorized=false`",
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
            "- F4 绿只表示记分卡诚实门与元评测五项对齐；**禁止**宣称 Tier A 自动扩容",
            "- 下一家族：F2（安全门）或 F3（G2b/process_split）",
            "",
            "复跑：`python3 packages/aiplat-evaluation/scripts/meta_eval_f4_status.py`",
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
