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
_VENV_PY = REPO / ".venv" / "bin" / "python"

# Plan §10 categories → default owner_role (config table; not wired runtime).
ROUTING_DRAFT = [
    {"category": "environment", "route_to": "infra_ops", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "data", "route_to": "fixture_gold_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "implementation", "route_to": "module_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "stale_assertion", "route_to": "eval_owner_plus_product", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "product_defect", "route_to": "product_owner", "sla_owner_h": 24, "sla_disposition_h": 72},
    {"category": "eval_defect", "route_to": "eval_owner_meta", "sla_owner_h": 24, "sla_disposition_h": 72},
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

    gates = {
        "failure_taxonomy_fn": bool(taxonomy.get("ok")),
        "g2b_fail_decision_table": decision.is_file(),
        "report_compare_fn": bool(report_compare.get("ok")),
        "routing_table_draft": True,
        "reeval_sla_draft": True,
        "runtime_router_wired": False,
        "closed_loop_claim": False,
        "chart_a3_process_split_authorized": False,
        "security_certification": False,
    }
    payload: Dict[str, Any] = {
        "schema": "eval.phase4.repair_loop_prep.v0",
        "recorded_at": _now(),
        "status": "prep",
        "gates": gates,
        "imports": {"build_failure_taxonomy": taxonomy, "compare_eval_reports": report_compare},
        "routing_draft": ROUTING_DRAFT,
        "sla_draft": {
            "tier_a_red_owner_hours": 24,
            "tier_a_disposition_hours": 72,
            "note": "from eval-system-improvement-plan §10; not enforced in runtime yet",
        },
        "evidence_refs": [
            "aiPlat-core/core/apps/eval/service/gate_v1.py",
            ".aiplat/eval_trust/g2b_fail_decision_table_v0.json",
            "docs/architecture/plans/eval-system-improvement-plan.md#10",
        ],
        "next_actions": [
            "Wire disposition ledger write path after gate_v1 taxonomy",
            "Add reeval job fingerprint (same pack SHA) stub",
            "Owner accept routing_draft categories before automation",
        ],
        "honesty": (
            "Prep inventory only. ≠ closed-loop automation claim. "
            "≠ Chart flip ≠ security cert ≠ production independent."
        ),
    }
    META.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    g = gates
    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# Phase 4 预备（修复闭环 · 未接线）",
        "",
        f"> 机器：[`evidence/meta_eval/phase4_repair_loop_prep_board.v0.json`](./evidence/meta_eval/phase4_repair_loop_prep_board.v0.json) · {_now()}",
        "> 计划 §10 · **诚实锁**：预备 ≠ 「自动改进已闭环」· Chart 仍 false",
        "",
        "## 闸门",
        "",
        "| 项 | 状态 |",
        "|---|---|",
        f"| `build_failure_taxonomy` import | {'✅' if g['failure_taxonomy_fn'] else '❌'} |",
        f"| G2b fail decision table | {'✅' if g['g2b_fail_decision_table'] else '❌'} |",
        f"| `compare_eval_reports` import | {'✅' if g['report_compare_fn'] else '❌'} |",
        f"| routing 表草稿 | ✅ |",
        f"| 复评 SLA 草稿（24h/72h） | ✅ |",
        f"| runtime router 接线 | ❌ |",
        f"| closed_loop_claim | **false** |",
        "",
        "## 路由草稿（配置 · 未强制）",
        "",
        "| category | route_to | owner SLA | disposition SLA |",
        "|---|---|---:|---:|",
    ]
    for r in ROUTING_DRAFT:
        lines.append(
            f"| `{r['category']}` | {r['route_to']} | {r['sla_owner_h']}h | {r['sla_disposition_h']}h |"
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "1. Owner 确认 routing_draft 类别",
            "2. 接线 disposition 账本写路径（taxonomy → 处置单）",
            "3. 复评同一 pack 指纹 stub",
            "",
            "## 复跑",
            "",
            "```bash",
            "python3 packages/aiplat-evaluation/scripts/phase4_repair_loop_prep.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "prep", "gates": gates}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
