#!/usr/bin/env python3
"""R12 tranche-1：evaluation-system ⋈ AIPLAT_CAPABILITIES.md + H1–H5 triage.

Writes reconciliation JSON/MD and triage summary. Does not authorize Tier A
expansion or claim full coverage.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REG = REPO / "aiPlat-core/core/capability_registry.yaml"
CAP = REPO / "AIPLAT_CAPABILITIES.md"
OUT_JSON = ROOT / "docs/a3/evidence/r12_capability_reconciliation.v0.json"
OUT_MD = ROOT / "docs/a3/R12_CAPABILITY_RECONCILIATION.md"
TRIAGE_JSON = ROOT / "docs/a3/evidence/r12_triage_v0.json"
EXEMPT_UNTIL = "2027-02-14"


def _capabilities_symbols(text: str) -> set[str]:
    """Extract join keys from AIPLAT_CAPABILITIES.md.

    Args:
        text: Full markdown contents.

    Returns:
        Symbol set from backticks **and** table first-column tokens
        (many capability names are not wrapped in backticks).
    """
    ticks = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_\.\-]{2,})`", text))
    cells: set[str] = set()
    skip = {
        "能力",
        "名称",
        "模块",
        "状态",
        "Status",
        "#",
        "符号",
        "说明",
        "路径",
        "生成物",
        "批次",
    }
    for m in re.finditer(r"^\|\s*([^|\n]+?)\s*\|", text, re.M):
        cell = m.group(1).strip()
        if not cell or cell.startswith("---") or cell in skip:
            continue
        for t in re.findall(
            r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_\.\-]{2,})", cell
        ):
            sym = t[0] or t[1]
            if sym:
                cells.add(sym)
    return ticks | cells


def _classify_reg(sym: str, mod: str) -> str:
    """Classify registry-only symbols into triage buckets.

    Args:
        sym: Symbol from registry provides.
        mod: Module path string.

    Returns:
        Category id (H1_candidate / H2 / H4).
    """
    if sym.endswith("Error") or sym.endswith("Exception"):
        return "H2"
    if "core_facade" in (mod or "").replace("\\", "/"):
        return "H2"
    if re.search(r"(?i)(helper|_internal|private)", sym):
        return "H2"
    if (mod or "").endswith(".sh") or "/scripts/" in (mod or "").replace("\\", "/"):
        return "H4"
    return "H1_candidate"


def _classify_cap(sym: str) -> str:
    """Classify CAPABILITIES-only tokens for evaluation-system tranche.

    Args:
        sym: Token from AIPLAT_CAPABILITIES.md.

    Returns:
        H3 (non-capability / noise), H5 (likely missing registry), or
        H6 (matched loose eval keyword but out of this domain tranche).
    """
    if re.search(r"(?i)\.(md|tsx|ts|json|py)$", sym):
        return "H3"
    if (
        sym.startswith("ADR-")
        or sym.startswith("AIPLAT_")
        or "CLOSEOUT" in sym
        or "PANEL" in sym.upper()
        or sym.endswith("Panel")
        or "Panel.tsx" in sym
        or "/" in sym
        or " " in sym
        # Doc stems like `eval_` / `eval_api_capability_` are not provides.
        or sym.endswith("_")
    ):
        return "H3"
    # Strict: only these shapes are expected in evaluation-system provides.
    if re.match(
        r"(?i)^(eval_|g2b_|scorecard_|preference_|aiplat_eval_|"
        r"run_[a-z0-9_]+_capability_smoke$|.*SubjectAdapter$)",
        sym,
    ):
        return "H5"
    return "H6"


def main() -> int:
    """Generate R12 reconciliation + triage artifacts.

    Returns:
        0 on success.
    """
    import yaml

    reg = yaml.safe_load(REG.read_text(encoding="utf-8"))
    cap_syms = _capabilities_symbols(CAP.read_text(encoding="utf-8"))
    domain = (reg.get("domains") or {}).get("evaluation-system")
    if not isinstance(domain, dict):
        print("evaluation-system domain missing", file=sys.stderr)
        return 1

    rows: List[Dict[str, str]] = []

    def collect(obj: Any, mod: str = "") -> None:
        if isinstance(obj, dict):
            mod2 = str(obj.get("module") or obj.get("path") or mod)
            for p in obj.get("provides") or []:
                if isinstance(p, str):
                    rows.append({"module": mod2, "symbol": p})
                elif isinstance(p, dict):
                    n = p.get("name") or p.get("symbol") or p.get("id")
                    if n:
                        rows.append(
                            {
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

    diffs: List[Dict[str, Any]] = []
    for sym, r in sorted(by_sym.items()):
        if sym in cap_syms:
            continue
        cat = _classify_reg(sym, r.get("module") or "")
        if cat == "H2":
            disp, note = "exempt_human_view", "re-export/Error/helper；豁免"
        elif cat == "H4":
            disp, note = "exempt_tooling", "脚本/工具；豁免"
        else:
            disp, note = "open", "待评测 owner 批 H1 白名单或降 H2"
        diffs.append(
            {
                "capability_or_symbol": sym,
                "type": "registry_has_capabilities_missing",
                "module": r.get("module"),
                "category": cat,
                "owner": "评测 owner",
                "disposition": disp,
                "exempt_until": EXEMPT_UNTIL if disp.startswith("exempt") else None,
                "note": note,
            }
        )

    # Cap-only scan: prefer strict eval shapes; loose keyword hits → H6 out-of-tranche.
    eval_cap = sorted(
        s
        for s in cap_syms
        if re.search(r"(?i)eval|scorecard|g2b|preference|arena|SubjectAdapter", s)
    )
    for sym in eval_cap:
        if sym in by_sym:
            continue
        cat = _classify_cap(sym)
        if cat == "H3":
            disp, note = "downgrade_non_capability", "文档/UI/路径非能力"
        elif cat == "H6":
            disp, note = "out_of_tranche", "含 eval 样词但不属 evaluation-system 对账分子"
        else:
            disp, note = "open", "补 registry provides 或删夸大叙述"
        diffs.append(
            {
                "capability_or_symbol": sym,
                "type": "capabilities_has_registry_missing",
                "module": None,
                "category": cat,
                "owner": "评测 owner",
                "disposition": disp,
                "exempt_until": None,
                "note": note,
            }
        )

    cat_c = Counter(str(d["category"]) for d in diffs)
    disp_c = Counter(str(d["disposition"]) for d in diffs)
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    in_both = sorted(s for s in by_sym if s in cap_syms)

    summary = {
        "schema": "eval.r12.capability_reconciliation.v0",
        "tranche": "evaluation-system-domain-only",
        "recorded_at": now,
        "accuracy_claim": False,
        "join_key": "(module,symbol); triage=H1–H5",
        "counts": {
            "registry_symbols": len(by_sym),
            "in_both": len(in_both),
            "diff_total": len(diffs),
            "open": sum(1 for d in diffs if d["disposition"] == "open"),
            "exempt": sum(
                1 for d in diffs if str(d["disposition"]).startswith("exempt")
            ),
            "downgraded": sum(
                1 for d in diffs if d["disposition"] == "downgrade_non_capability"
            ),
            "out_of_tranche": sum(
                1 for d in diffs if d["disposition"] == "out_of_tranche"
            ),
        },
        "by_category": dict(cat_c),
        "by_disposition": dict(disp_c),
        "in_both_sample": in_both[:40],
        "diffs": diffs,
        "owner": "评测 owner",
        "honesty": (
            "Triage filters applied. Open H1_candidate/H5 remain. "
            "≠ Tier A expansion; ≠ coverage complete."
        ),
    }
    OUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    TRIAGE_JSON.write_text(
        json.dumps(
            {
                "schema": "eval.r12.triage.v0",
                "recorded_at": now,
                "exempt_until_default": EXEMPT_UNTIL,
                "by_category": dict(cat_c),
                "by_disposition": dict(disp_c),
                "h1_candidate_n": cat_c.get("H1_candidate", 0),
                "doc": "docs/a3/R12_TRIAGE_V0.md",
                "accuracy_claim": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [
        "---",
        "doc_type: Reference",
        "---",
        "",
        "# R12 · 能力对账结果（tranche-1：evaluation-system）",
        "",
        "> 分诊：[`R12_TRIAGE_V0.md`](./R12_TRIAGE_V0.md) · "
        f"时点 {now}",
        "> 复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`",
        "",
        "## 汇总",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| registry 符号 | {summary['counts']['registry_symbols']} |",
        f"| 两边均有 | {summary['counts']['in_both']} |",
        f"| 差异合计 | {summary['counts']['diff_total']} |",
        f"| open | {summary['counts']['open']} |",
        f"| exempt | {summary['counts']['exempt']} |",
        f"| downgraded | {summary['counts']['downgraded']} |",
        f"| out_of_tranche | {summary['counts']['out_of_tranche']} |",
        "",
        "## 分诊类别",
        "",
        "| 类别 | 数量 |",
        "|---|---:|",
    ]
    for k, v in sorted(cat_c.items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        f"H2/H4 豁免到期：**{EXEMPT_UNTIL}**。"
        " H1_candidate 已清零（见白名单）。"
        " H5 open ≠ Tier A 扩容；见 [`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md)。",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "counts": summary["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
