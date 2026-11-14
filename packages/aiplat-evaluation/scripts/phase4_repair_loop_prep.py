#!/usr/bin/env python3
"""Phase 4 prep — inventory failure taxonomy / disposition / reeval SLA stubs.

Does not claim closed-loop automation. Does not flip Chart or security cert.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
OUT_JSON = META / "phase4_repair_loop_prep_board.v0.json"
OUT_MD = ROOT / "docs/a3/PHASE4_PREP.md"
ROUTING_FILE = ROOT / "docs/a3/config/phase4_routing.v0.json"
LEDGER_FILE = META / "phase4_disposition_ledger.v0.json"
ROUTING_AUTH = META / "phase4_routing_authorize.v0.json"
_VENV_PY = REPO / ".venv" / "bin" / "python"

# Plan §10 categories → default owner_role (config table; runtime dispatch still off).
ROUTING_DRAFT = [
    {"category": "environment", "route_to": "infra_ops", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "data", "route_to": "fixture_gold_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "implementation", "route_to": "module_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "stale_assertion", "route_to": "eval_owner_plus_product", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "product_defect", "route_to": "product_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "eval_defect", "route_to": "eval_owner_meta", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "unknown", "route_to": "eval_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
]


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _import_ok(mod: str, symbol: str) -> Dict[str, Any]:
    """Import smoke for a symbol.

    Args:
        mod: 模块路径。
        symbol: 符号名。

    Returns:
        状态字典。
    """
    sys.path.insert(0, str(REPO / "aiPlat-core"))
    sys.path.insert(0, str(REPO))
    try:
        m = importlib.import_module(mod)
        return {"ok": hasattr(m, symbol), "module": mod, "symbol": symbol}
    except Exception as exc:  # noqa: BLE001 — prep board records import errors
        return {"ok": False, "module": mod, "symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    """写出 Phase 4 修复闭环预备板。

    Returns:
        进程退出码。
    """
    if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
        if os.environ.get("AIPLAT_PHASE4_NO_REEXEC") != "1":
            os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

    taxonomy = _import_ok("core.apps.eval.service.gate_v1", "build_failure_taxonomy")
    decision = REPO / ".aiplat/eval_trust/g2b_fail_decision_table_v0.json"
    report_compare = _import_ok("core.apps.eval.service.report_compare", "compare_eval_reports")
    routing_cfg = ROUTING_FILE.is_file()
    ledger_wired = LEDGER_FILE.is_file()
    routing_authorized = False
    if ROUTING_AUTH.is_file():
        try:
            auth = json.loads(ROUTING_AUTH.read_text(encoding="utf-8"))
            routing_authorized = bool(auth.get("phase4_routing_authorized")) and str(
                auth.get("status") or ""
            ).lower() in ("authorized", "accepted")
        except Exception:  # noqa: BLE001 — prep board records parse errors
            routing_authorized = False
    if routing_cfg and not routing_authorized:
        try:
            cfg = json.loads(ROUTING_FILE.read_text(encoding="utf-8"))
            routing_authorized = bool(cfg.get("phase4_routing_authorized"))
        except Exception:  # noqa: BLE001
            pass
    fingerprint_stub = False
    if ledger_wired:
        try:
            ledger = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
            packs = ledger.get("packs") or []
            fingerprint_stub = bool(packs) and any(
                isinstance(p, dict) and p.get("fingerprint_sha256") for p in packs
            )
        except Exception:  # noqa: BLE001 — prep board records parse errors
            fingerprint_stub = False

    gates = {
        "failure_taxonomy_fn": bool(taxonomy.get("ok")),
        "g2b_fail_decision_table": decision.is_file(),
        "report_compare_fn": bool(report_compare.get("ok")),
        "routing_table_draft": True,
        "routing_config_file": routing_cfg,
        "phase4_routing_authorized": routing_authorized,
        "reeval_sla_draft": True,
        "disposition_ledger_wired": ledger_wired,
        "reeval_fingerprint_stub": fingerprint_stub,
        "runtime_router_wired": False,
        "closed_loop_claim": False,
        "chart_a3_process_split_authorized": False,
        "security_certification": False,
    }
    if ledger_wired and routing_cfg and routing_authorized:
        status = "routing_authorized"
    elif ledger_wired and routing_cfg:
        status = "ledger_wired"
    else:
        status = "prep"
    if routing_authorized:
        next_actions = [
            "Human disposition + close tickets (phase4_disposition_ledger.py --close)",
            "Same-pack reeval after disposition (fingerprint)",
            "Runtime auto-dispatch remains off",
        ]
    elif ledger_wired:
        next_actions = [
            "Owner AUTHORIZE phase4_routing (confirm categories)",
            "Human disposition + close tickets",
            "Same-pack reeval after disposition (fingerprint)",
            "Runtime auto-dispatch remains off until owner accept",
        ]
    else:
        next_actions = [
            "Wire disposition ledger write path after gate_v1 taxonomy",
            "Add reeval job fingerprint (same pack SHA) stub",
            "Owner accept routing_draft categories before automation",
        ]
    payload: Dict[str, Any] = {
        "schema": "eval.phase4.repair_loop_prep.v0",
        "recorded_at": _now(),
        "status": status,
        "gates": gates,
        "imports": {"build_failure_taxonomy": taxonomy, "compare_eval_reports": report_compare},
        "routing_draft": ROUTING_DRAFT,
        "routing_ref": "docs/a3/config/phase4_routing.v0.json" if routing_cfg else None,
        "ledger_ref": (
            "docs/a3/evidence/meta_eval/phase4_disposition_ledger.v0.json" if ledger_wired else None
        ),
        "sla_draft": {
            "tier_a_red_owner_hours": 24,
            "tier_a_disposition_hours": 72,
            "note": "from eval-system-improvement-plan §10; SLA not auto-enforced",
        },
        "evidence_refs": [
            "aiPlat-core/core/apps/eval/service/gate_v1.py",
            ".aiplat/eval_trust/g2b_fail_decision_table_v0.json",
            "docs/architecture/plans/eval-system-improvement-plan.md#10",
            "packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py",
        ],
        "next_actions": next_actions,
        "honesty": (
            "Disposition ledger + fingerprint stub may be wired; "
            "≠ closed-loop automation ≠ Chart flip ≠ security cert."
        ),
    }
    META.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    g = gates
    if routing_authorized:
        title = "# Phase 4 预备（修复闭环 · routing 已授权）"
    elif ledger_wired:
        title = "# Phase 4 预备（修复闭环 · 账本已接线）"
    else:
        title = "# Phase 4 预备（修复闭环 · 未接线）"
    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        title,
        "",
        f"> 机器：[`evidence/meta_eval/phase4_repair_loop_prep_board.v0.json`](./evidence/meta_eval/phase4_repair_loop_prep_board.v0.json) · {_now()}",
    ]
    if ledger_wired:
        lines.append(
            "> 账本：[`evidence/meta_eval/phase4_disposition_ledger.v0.json`](./evidence/meta_eval/phase4_disposition_ledger.v0.json)"
        )
        lines.append("> 路由：[`config/phase4_routing.v0.json`](./config/phase4_routing.v0.json)")
    lines.extend(
        [
            "> 计划 §10 · **诚实锁**：账本 ≠ 「自动改进已闭环」· Chart 仍 false",
            "",
            "## 闸门",
            "",
            "| 项 | 状态 |",
            "|---|---|",
            f"| `build_failure_taxonomy` import | {'✅' if g['failure_taxonomy_fn'] else '❌'} |",
            f"| G2b fail decision table | {'✅' if g['g2b_fail_decision_table'] else '❌'} |",
            f"| `compare_eval_reports` import | {'✅' if g['report_compare_fn'] else '❌'} |",
            f"| routing 配置文件 | {'✅' if g['routing_config_file'] else '❌'} |",
            f"| `phase4_routing_authorized` | {'✅' if g['phase4_routing_authorized'] else '❌'} |",
            f"| disposition 账本写路径 | {'✅' if g['disposition_ledger_wired'] else '❌'} |",
            f"| 复评 pack 指纹 stub | {'✅' if g['reeval_fingerprint_stub'] else '❌'} |",
            f"| runtime router 接线 | ❌ |",
            f"| closed_loop_claim | **false** |",
            "",
            "## 路由（配置 · 未 runtime 强制）",
            "",
            "| category | route_to | owner SLA | disposition SLA |",
            "|---|---|---:|---:|",
        ]
    )
    for r in ROUTING_DRAFT:
        lines.append(
            f"| `{r['category']}` | {r['route_to']} | {r['sla_owner_h']}h | {r['sla_disposition_h']}h |"
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "",
        ]
    )
    for i, action in enumerate(next_actions, 1):
        lines.append(f"{i}. {action}")
    lines.extend(
        [
            "",
            "## 复跑",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase4_disposition_ledger.py --demo",
            "python3 packages/aiplat-evaluation/scripts/phase4_repair_loop_prep.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": status, "gates": gates}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
