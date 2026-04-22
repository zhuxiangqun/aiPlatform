#!/usr/bin/env python3
"""
Generate a lightweight "bypass path audit" report for aiPlat-core.

Focus:
- Enumerate mutating endpoints in core/server.py (POST/PUT/DELETE)
- Heuristically detect whether they call _rbac_guard and/or write audit logs

This is NOT a formal security proof. It's a fast regression guard and review aid.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
SERVER_PY = ROOT / "core" / "server.py"


DECORATOR_RE = re.compile(r'^\s*@api_router\.(post|put|delete)\("([^"]+)"')
DEF_RE = re.compile(r"^\s*async\s+def\s+([a-zA-Z0-9_]+)\(")


def _scan() -> List[Dict[str, object]]:
    lines = SERVER_PY.read_text(encoding="utf-8", errors="replace").splitlines()
    out: List[Dict[str, object]] = []
    i = 0
    while i < len(lines):
        m = DECORATOR_RE.match(lines[i])
        if not m:
            i += 1
            continue
        method = m.group(1).upper()
        path = m.group(2)
        j = i + 1
        # Skip other decorators
        while j < len(lines) and lines[j].lstrip().startswith("@"):
            j += 1
        dm = DEF_RE.match(lines[j]) if j < len(lines) else None
        fn = dm.group(1) if dm else "unknown"
        # naive body capture until next decorator/def at col0-ish
        body: List[str] = []
        k = j + 1
        while k < len(lines):
            if DECORATOR_RE.match(lines[k]) and lines[k].startswith("@"):
                break
            if lines[k].startswith("async def ") and not lines[k].startswith(" "):
                break
            body.append(lines[k])
            k += 1
        body_text = "\n".join(body)
        out.append(
            {
                "method": method,
                "path": path,
                "function": fn,
                "has_rbac_guard": "_rbac_guard" in body_text,
                "has_approval": "approval" in body_text.lower() and "approval_request" in body_text.lower(),
                "has_audit_log": "add_audit_log" in body_text,
                "has_changeset": "_record_changeset" in body_text,
            }
        )
        i = k
    return out


def main() -> None:
    rows = _scan()
    # Sort: write ops first, then path
    rows.sort(key=lambda r: (r["path"], r["method"]))

    md: List[str] = []
    md.append("# aiPlat-core 绕过路径审计（启发式）\n")
    md.append(f"- 扫描文件：`{SERVER_PY}`")
    md.append("- 范围：仅枚举 `@api_router.post/put/delete`，并用字符串匹配判断是否调用 `_rbac_guard` / `add_audit_log` 等。")
    md.append("- 目的：快速发现“明显未接门控/审计”的写操作端点，作为 review 与回归 guard。\n")

    md.append("## 端点清单（写操作）\n")
    md.append("| method | path | function | rbac_guard | audit_log | changeset | approval |")
    md.append("|---|---|---|---:|---:|---:|---:|")
    for r in rows:
        md.append(
            f"| {r['method']} | `{r['path']}` | `{r['function']}` | "
            f"{'✅' if r['has_rbac_guard'] else '❌'} | "
            f"{'✅' if r['has_audit_log'] else '❌'} | "
            f"{'✅' if r['has_changeset'] else '❌'} | "
            f"{'✅' if r['has_approval'] else '❌'} |"
        )

    # Findings
    missing_rbac = [r for r in rows if not r["has_rbac_guard"]]
    missing_audit = [r for r in rows if not r["has_audit_log"]]
    md.append("\n## 初步发现（需要人工复核）\n")
    md.append(f"- 写操作端点总数：**{len(rows)}**")
    md.append(f"- 未检测到 `_rbac_guard` 的端点：**{len(missing_rbac)}**")
    md.append(f"- 未检测到 `add_audit_log` 的端点：**{len(missing_audit)}**\n")

    if missing_rbac:
        md.append("### A) 可能缺少 RBAC 门控的端点（❌ _rbac_guard）\n")
        for r in missing_rbac[:50]:
            md.append(f"- {r['method']} `{r['path']}` ({r['function']})")
        if len(missing_rbac) > 50:
            md.append(f"- ... 其余 {len(missing_rbac)-50} 条略")
        md.append("")

    if missing_audit:
        md.append("### B) 可能缺少审计记录的端点（❌ add_audit_log）\n")
        md.append("> 注：有些端点可能仅靠 changeset/event 记录，仍需人工判断是否满足审计要求。\n")
        for r in missing_audit[:50]:
            md.append(f"- {r['method']} `{r['path']}` ({r['function']})")
        if len(missing_audit) > 50:
            md.append(f"- ... 其余 {len(missing_audit)-50} 条略")
        md.append("")

    print("\n".join(md))


if __name__ == "__main__":
    main()

