#!/usr/bin/env python3
"""R12 tranche-1：evaluation-system domain ⋈ AIPLAT_CAPABILITIES.md.

Writes evidence JSON + markdown queue. Open diffs are valid dispositions.
Does not authorize Tier A expansion or plan freeze.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REG = REPO / "aiPlat-core/core/capability_registry.yaml"
CAP = REPO / "AIPLAT_CAPABILITIES.md"
OUT_JSON = ROOT / "docs/a3/evidence/r12_capability_reconciliation.v0.json"
OUT_MD = ROOT / "docs/a3/R12_CAPABILITY_RECONCILIATION.md"


def main() -> int:
    """Generate R12 reconciliation artifacts for evaluation-system.

    Returns:
        0 on success.
    """
    import yaml

    reg = yaml.safe_load(REG.read_text(encoding="utf-8"))
    cap_ticks = set(
        re.findall(r"`([A-Za-z_][A-Za-z0-9_\.\-]{2,})`", CAP.read_text(encoding="utf-8"))
    )
    domain = (reg.get("domains") or {}).get("evaluation-system")
    if not isinstance(domain, dict):
        print("evaluation-system domain missing", file=sys.stderr)
        return 1

    rows: List[Dict[str, Any]] = []

    def collect(obj: Any, mod: str = "") -> None:
        if isinstance(obj, dict):
            mod2 = str(obj.get("module") or obj.get("path") or mod)
            for p in obj.get("provides") or []:
                if isinstance(p, str):
                    rows.append(
                        {"domain": "evaluation-system", "module": mod2, "symbol": p}
                    )
                elif isinstance(p, dict):
                    n = p.get("name") or p.get("symbol") or p.get("id")
                    if n:
                        rows.append(
                            {
                                "domain": "evaluation-system",
                                "module": str(p.get("module") or mod2),
                                "symbol": str(n),
                            }
                        )
            for v in obj.values():
                collect(v, mod2)
        elif isinstance(obj, list):
            for v in obj:
                collect(v, mod)

    collect(domain)
    by_sym = {r["symbol"]: r for r in rows}
    in_both = sorted(s for s in by_sym if s in cap_ticks)
    only_reg = sorted(s for s in by_sym if s not in cap_ticks)
    eval_cap = sorted(
        s
        for s in cap_ticks
        if re.search(r"(?i)eval|scorecard|g2b|preference_v0|arena", s)
    )
    only_cap = sorted(s for s in eval_cap if s not in by_sym)

    diffs: List[Dict[str, Any]] = []
    for s in only_reg:
        diffs.append(
            {
                "capability_or_symbol": s,
                "type": "registry_has_capabilities_missing",
                "module": by_sym[s].get("module"),
                "owner": "评测 owner",
                "disposition": "open",
                "note": "补 CAPABILITIES 行或标待登记人类视图",
            }
        )
    for s in only_cap:
        diffs.append(
            {
                "capability_or_symbol": s,
                "type": "capabilities_has_registry_missing",
                "module": None,
                "owner": "评测 owner",
                "disposition": "open",
                "note": "补 registry provides 或降为非能力叙述",
            }
        )

    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    summary = {
        "schema": "eval.r12.capability_reconciliation.v0",
        "tranche": "evaluation-system-domain-only",
        "recorded_at": now,
        "accuracy_claim": False,
        "join_key": "(module,symbol) fallback; domain=evaluation-system",
        "counts": {
            "registry_symbols": len(by_sym),
            "in_both": len(in_both),
            "registry_only": len(only_reg),
            "capabilities_evalish_only": len(only_cap),
            "diff_total": len(diffs),
        },
        "by_type": {
            "registry_has_capabilities_missing": len(only_reg),
            "capabilities_has_registry_missing": len(only_cap),
            "duplicate_join": 0,
        },
        "in_both_sample": in_both[:30],
        "diffs": diffs,
        "owner": "评测 owner",
        "honesty": (
            "Tranche-1 R12 for evaluation-system only. "
            "Open diffs are valid dispositions. "
            "≠ Tier A expansion; ≠ plan freeze; process_split_authorized=false."
        ),
    }
    OUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# R12 · 能力对账结果（tranche-1：evaluation-system）",
        "",
        "> 规则：计划 §4.5 · 主键 `capability_registry.yaml` · 视图 `AIPLAT_CAPABILITIES.md`",
        "> **范围**：仅 `domains.evaluation-system`",
        "> **诚实锁**：对账工件已产出；差异多为 `open`；**≠** Tier A 扩容；**≠** 定稿",
        f"> **时点**：{now}",
        "> 复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`",
        "> 机器可读：[`evidence/r12_capability_reconciliation.v0.json`](./evidence/r12_capability_reconciliation.v0.json)",
        "",
        "## 汇总",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| registry 符号（evaluation-system） | {summary['counts']['registry_symbols']} |",
        f"| 两边均有 | {summary['counts']['in_both']} |",
        f"| registry 有、CAPABILITIES 无 | {summary['counts']['registry_only']} |",
        f"| CAPABILITIES eval 样词有、本域 registry 无 | {summary['counts']['capabilities_evalish_only']} |",
        f"| 差异合计 | {summary['counts']['diff_total']} |",
        "",
        "## 处置队列（前 40 条；全文见 JSON）",
        "",
        "| 类型 | 符号 | module | owner | 处理结果 |",
        "|---|---|---|---|---|",
    ]
    for drow in diffs[:40]:
        lines.append(
            f"| {drow['type']} | `{drow['capability_or_symbol']}` | "
            f"`{drow.get('module') or ''}` | {drow['owner']} | {drow['disposition']} |"
        )
    if len(diffs) > 40:
        lines.append(f"| … | （另有 {len(diffs) - 40} 条见 JSON） | | | open |")
    lines += [
        "",
        "## Owner",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        "| Owner | 评测 owner |",
        "| 签字日 | ________________ |",
        "| 备注 | 差异清零前禁止宣称全平台覆盖完成 |",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "counts": summary["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
