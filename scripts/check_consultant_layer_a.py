#!/usr/bin/env python3
"""check_consultant_layer_a.py — Layer A 加深路由必须接线 reportPageData。

SSOT：aiPlat-management/frontend/src/lib/consultantLayerARoutes.ts
（与 XIAOZHU.md §1.4 对齐）。防止顾问在未上报页宣称「功能不存在」。

用法：
  python3 scripts/check_consultant_layer_a.py
  # exit 0 = 全绿；exit 1 = 有路由缺 reportPageData
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES_TS = ROOT / "aiPlat-management/frontend/src/lib/consultantLayerARoutes.ts"
SRC = ROOT / "aiPlat-management/frontend/src"


def _parse_routes(text: str) -> list[str]:
    """从 consultantLayerARoutes.ts 解析 route 字符串。"""
    return re.findall(r"route:\s*['\"]([^'\"]+)['\"]", text)


def _corpus() -> str:
    chunks: list[str] = []
    for p in SRC.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        if ".test." in p.name or p.name.endswith(".test.ts") or p.name.endswith(".test.tsx"):
            continue
        if "node_modules" in p.parts or "dist" in p.parts:
            continue
        try:
            chunks.append(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> int:
    """校验顾问 Layer A 深链路由均有 reportPageData 接线；缺则非零退出。"""
    if not ROUTES_TS.is_file():
        print(f"FAIL: missing {ROUTES_TS}", file=sys.stderr)
        return 2
    routes = _parse_routes(ROUTES_TS.read_text(encoding="utf-8"))
    if not routes:
        print("FAIL: no routes parsed from consultantLayerARoutes.ts", file=sys.stderr)
        return 2
    text = _corpus()
    missing: list[str] = []
    for route in routes:
        pat = re.compile(
            r"reportPageData\(\s*['\"]" + re.escape(route) + r"['\"]"
        )
        if not pat.search(text):
            missing.append(route)
    if missing:
        print("FAIL: Layer A deep routes missing reportPageData:")
        for m in missing:
            print(f"  - {m}")
        print(
            "Fix: add reportPageData + guideGlossary on that page, "
            "keep consultantLayerARoutes.ts / XIAOZHU.md §1.4 in sync."
        )
        return 1
    print(f"PASS: {len(routes)} Layer A deep routes have reportPageData")
    return 0


if __name__ == "__main__":
    sys.exit(main())
