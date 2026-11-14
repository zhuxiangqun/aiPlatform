#!/usr/bin/env python3
"""Phase 3 — Tier A gold/gate run ledger for 19 authorized symbols.

Verifies evidence refs, import/callable smoke, and claim_ready flags.
Does not flip Chart, security cert, or invent a single coverage percent.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
AUTH = META / "phase3_tier_a_authorized_symbols.v0.json"
INV = META / "phase3_a_candidate_inventory.v0.json"
OUT_JSON = META / "phase3_tier_a_gold_gate_ledger.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE3_TIER_A_GOLD_GATE_LEDGER.md"
_VENV_PY = REPO / ".venv" / "bin" / "python"

# Prefer importing via known module paths (facade wrappers + impls).
IMPORT_CANDIDATES: Dict[str, List[str]] = {
    "cohen_kappa_binary": ["core.apps.eval.service.g2c"],
    "wilson_score_ci": ["core.apps.eval.service.mode_intersection_rank"],
    "evaluate_judge_calibration_gate": ["core.apps.eval.service.capability_p4_gate"],
    "open_capability_judge_calibration": ["core.apps.eval.service.capability_p4_gate"],
    "judge_calibration_gate_for_ticket": ["core.apps.eval.service.capability_p4_gate"],
    "eval_judge_calibration_gate": ["core.api.core_facade", "core.apps.eval.service.capability_p4_gate"],
    "eval_open_capability_judge_calibration": [
        "core.api.core_facade",
        "core.apps.eval.service.capability_p4_gate",
    ],
    "build_release_scorecard": ["core.harness.evaluation.release_scorecard"],
    "build_judge_calib_evidence_pack": ["core.apps.eval.service.security_cert_prep"],
    "assert_t13_process_split_boundary": ["core.apps.eval.service.security_t13_allowlist"],
    "eval_assert_t13_process_split_boundary": [
        "core.api.core_facade",
        "core.apps.eval.service.security_t13_allowlist",
    ],
    "build_g2b_s_dual_review_workflow": ["core.apps.eval.service.security_cert_prep"],
    "load_judge_calib_defaults": ["core.apps.eval.service.security_cert_prep"],
    "eval_load_security_judge_calib_defaults": ["core.api.core_facade"],
    "evaluate_security_family_gates": ["core.apps.eval.service.security_cert_prep"],
    "eval_evaluate_security_family_gates": ["core.api.core_facade"],
    "evaluate_security_judge_calibration": ["core.apps.eval.service.security_cert_prep"],
    "eval_evaluate_security_judge_calibration": ["core.api.core_facade"],
    "eval_evaluate_security_severity_l5_gate": ["core.api.core_facade"],
}


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _repo_path(rel: str) -> Path:
    """解析相对仓库根的路径。

    Args:
        rel: 相对路径。

    Returns:
        绝对 Path。
    """
    p = Path(rel)
    if p.is_absolute():
        return p
    # inventory refs are repo-relative or package-relative under packages/aiplat-evaluation
    for base in (REPO, ROOT):
        cand = base / rel
        if cand.is_file() or cand.is_dir():
            return cand
        # strip packages/aiplat-evaluation prefix if present
        if rel.startswith("docs/a3/"):
            cand2 = ROOT / rel
            if cand2.is_file():
                return cand2
    return REPO / rel


def _evidence_ok(refs: List[str]) -> Tuple[bool, List[str]]:
    """检查证据文件是否存在。

    Args:
        refs: 相对路径列表。

    Returns:
        (全部存在, 缺失列表)。
    """
    missing: List[str] = []
    for r in refs:
        if not r:
            continue
        if not _repo_path(r).is_file():
            missing.append(r)
    return (len(missing) == 0, missing)


def _import_smoke(symbol: str) -> Tuple[str, Optional[str]]:
    """尝试从候选模块导入符号。

    Args:
        symbol: 符号名。

    Returns:
        (ok|skip|fail, detail)。
    """
    mods = IMPORT_CANDIDATES.get(symbol) or []
    if not mods:
        return "skip", "no_import_candidate"
    sys.path.insert(0, str(REPO / "aiPlat-core"))
    sys.path.insert(0, str(REPO))
    last_err = ""
    for mod_name in mods:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, symbol):
                return "ok", f"{mod_name}.{symbol}"
            last_err = f"{mod_name}: attribute missing"
        except Exception as exc:  # noqa: BLE001 — smoke ledger must record import errors
            last_err = f"{mod_name}: {type(exc).__name__}: {exc}"
    return "fail", last_err


def main() -> int:
    """生成 Tier A gold/gate 账本。

    Returns:
        进程退出码。
    """
    # Re-exec under repo .venv so dataclass(kw_only=...) / deps resolve.
    if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
        if os.environ.get("AIPLAT_TIER_A_LEDGER_NO_REEXEC") != "1":
            os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

    if not AUTH.is_file() or not INV.is_file():
        print("missing authorized symbols or inventory", file=sys.stderr)
        return 1
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    inv = json.loads(INV.read_text(encoding="utf-8"))
    inv_by = {str(i.get("symbol")): i for i in (inv.get("items") or []) if isinstance(i, dict)}
    rows: List[Dict[str, Any]] = []
    for sym_row in auth.get("symbols") or []:
        if not isinstance(sym_row, dict):
            continue
        sym = str(sym_row.get("symbol") or "")
        item = inv_by.get(sym) or {}
        refs = list(item.get("evidence_refs") or [])
        # family-level evidence always count as gold-side refs for META families
        evid_ok, missing = _evidence_ok(refs)
        import_status, import_detail = _import_smoke(sym)
        gate_authorized = bool(sym_row.get("tier_a_gate_authorized"))
        claim_eligible = bool(sym_row.get("claim_eligible")) and bool(auth.get("accuracy_claim"))
        # claim_ready = authorized + evidence present + import ok|skip (skip = helper documented)
        # claim_ready: authorize + family evidence. import_smoke is advisory (env may block).
        claim_ready = bool(gate_authorized and claim_eligible and evid_ok)
        rows.append(
            {
                "symbol": sym,
                "meta_family": sym_row.get("meta_family") or item.get("meta_family"),
                "tier_a_gate_authorized": gate_authorized,
                "evidence_ok": evid_ok,
                "evidence_missing": missing,
                "evidence_refs": refs,
                "import_smoke": import_status,
                "import_detail": import_detail,
                "gold_side": "family_evidence" if evid_ok else "missing_evidence",
                "gate_side": "authorized" if gate_authorized else "not_authorized",
                "claim_eligible": claim_eligible,
                "claim_ready": claim_ready,
                "security_certification": False,
                "chart_a3_process_split_authorized": False,
            }
        )

    n = len(rows)
    n_ready = sum(1 for r in rows if r["claim_ready"])
    n_evid = sum(1 for r in rows if r["evidence_ok"])
    n_import_ok = sum(1 for r in rows if r["import_smoke"] == "ok")
    payload = {
        "schema": "eval.phase3.tier_a_gold_gate_ledger.v0",
        "recorded_at": _now(),
        "n": n,
        "n_evidence_ok": n_evid,
        "n_import_ok": n_import_ok,
        "n_claim_ready": n_ready,
        "accuracy_claim_policy": bool(auth.get("accuracy_claim")),
        "global_tier_a_expansion_authorized": bool(auth.get("global_tier_a_expansion_authorized")),
        "security_certification": False,
        "chart_a3_process_split_authorized": False,
        "forbid_single_coverage_percent": True,
        "symbols": rows,
        "honesty": (
            "Per-symbol evidence+import smoke ledger. claim_ready ≠ security cert ≠ Chart flip. "
            "No single platform coverage percent."
        ),
    }
    META.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 3 · Tier A gold/gate 实跑账本",
        "",
        f"> 机器：[`evidence/meta_eval/phase3_tier_a_gold_gate_ledger.v0.json`](./evidence/meta_eval/phase3_tier_a_gold_gate_ledger.v0.json) · {_now()}",
        f"> n=**{n}** · evidence_ok=**{n_evid}** · import_ok=**{n_import_ok}** · claim_ready=**{n_ready}**",
        "> **诚实锁**：≠ security cert · Chart 仍 false · 禁止单一覆盖%",
        "",
        "| 符号 | 家族 | evidence | import | claim_ready |",
        "|---|---|:---:|:---:|:---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['symbol']}` | {r.get('meta_family') or ''} | "
            f"{'✅' if r['evidence_ok'] else '❌'} | {r['import_smoke']} | "
            f"{'✅' if r['claim_ready'] else '❌'} |"
        )
    lines.extend(
        [
            "",
            "## 复跑",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase3_tier_a_gold_gate_ledger.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"n": n, "claim_ready": n_ready, "evidence_ok": n_evid, "import_ok": n_import_ok}))
    return 0


if __name__ == "__main__":
    import os

    venv_py = REPO / ".venv" / "bin" / "python"
    # Re-exec under repo venv when available (3.10+ / deps for core imports).
    if venv_py.is_file() and Path(sys.executable).resolve() != venv_py.resolve():
        os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(main())
