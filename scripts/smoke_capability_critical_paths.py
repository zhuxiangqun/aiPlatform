#!/usr/bin/env python3
"""
smoke_capability_critical_paths.py — Phase D critical-path behavior smoke

Separates 「行为通过」 from CAPABILITIES ✅:
  - static checks: repo file + AST symbol / substring (always available in CI)
  - live checks: HTTP against CORE/PLATFORM (opt-in locally;
    CI hard gate = job capability-critical-live with --require-live)

Usage:
  python3 scripts/smoke_capability_critical_paths.py           # report, exit 0
  python3 scripts/smoke_capability_critical_paths.py --ci      # static fail → exit 1
  python3 scripts/smoke_capability_critical_paths.py --live    # also attempt HTTP
  python3 scripts/smoke_capability_critical_paths.py --ci --require-live
      # live failures also hard-fail (capability-critical-live CI job)

Env:
  AIPLAT_SMOKE_CORE_URL   default http://127.0.0.1:8002
  AIPLAT_SMOKE_PLATFORM_URL default http://127.0.0.1:8003
  AIPLAT_SMOKE_LIVE=1     same as --live
"""
from __future__ import annotations

import ast
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "baselines" / "capability_critical_paths.yaml"


def _load_manifest() -> Dict[str, Any]:
    import yaml

    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _top_level_names(path: Path) -> set:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return set()
    names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _check_static(item: Dict[str, Any]) -> Tuple[bool, str]:
    rel = str(item.get("module") or "")
    path = ROOT / rel
    if not path.is_file():
        return False, f"missing file {rel}"
    symbol = item.get("symbol")
    contains = item.get("contains")
    if symbol:
        names = _top_level_names(path)
        if symbol not in names:
            return False, f"symbol {symbol!r} not in AST top-level of {rel}"
    if contains:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if contains not in text:
            return False, f"substring {contains!r} not found in {rel}"
    if not symbol and not contains:
        return True, "file exists"
    return True, "ok"


def _http(method: str, url: str, timeout: float = 5.0) -> Tuple[int, str]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(200).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read(200).decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def _check_live(item: Dict[str, Any], core: str, platform: str) -> Tuple[bool, str]:
    url_t = str(item.get("url") or "")
    url = url_t.format(CORE=core.rstrip("/"), PLATFORM=platform.rstrip("/"))
    method = str(item.get("method") or "GET").upper()
    expect = int(item.get("expect_status") or 200)
    status, body = _http(method, url)
    if status == expect:
        return True, f"{method} {url} → {status}"
    return False, f"{method} {url} → {status} (want {expect}); {body[:120]}"


def run_smoke(
    *,
    live: bool = False,
    require_live: bool = False,
) -> Dict[str, Any]:
    data = _load_manifest()
    core = os.environ.get("AIPLAT_SMOKE_CORE_URL", "http://127.0.0.1:8002")
    platform = os.environ.get("AIPLAT_SMOKE_PLATFORM_URL", "http://127.0.0.1:8003")
    results: List[Dict[str, Any]] = []
    static_fail = 0
    live_fail = 0
    live_skip = 0

    for item in data.get("paths") or []:
        kind = str(item.get("kind") or "static")
        rid = str(item.get("id") or "?")
        title = str(item.get("title") or rid)
        if kind == "static":
            ok, detail = _check_static(item)
            if not ok:
                static_fail += 1
            results.append(
                {"id": rid, "kind": kind, "title": title, "ok": ok, "detail": detail}
            )
        elif kind == "live":
            if not live:
                live_skip += 1
                results.append(
                    {
                        "id": rid,
                        "kind": kind,
                        "title": title,
                        "ok": None,
                        "detail": "skipped (pass --live or AIPLAT_SMOKE_LIVE=1)",
                    }
                )
                continue
            ok, detail = _check_live(item, core, platform)
            if not ok:
                live_fail += 1
            results.append(
                {"id": rid, "kind": kind, "title": title, "ok": ok, "detail": detail}
            )
        else:
            results.append(
                {
                    "id": rid,
                    "kind": kind,
                    "title": title,
                    "ok": False,
                    "detail": f"unknown kind {kind}",
                }
            )
            static_fail += 1

    return {
        "static_fail": static_fail,
        "live_fail": live_fail,
        "live_skip": live_skip,
        "require_live": require_live,
        "results": results,
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    ci = "--ci" in argv
    live = "--live" in argv or os.environ.get("AIPLAT_SMOKE_LIVE", "") == "1"
    require_live = "--require-live" in argv
    report_json = "--json" in argv

    print("capability critical-path smoke (Phase D)")
    print(f"manifest: {MANIFEST}")
    print("-" * 60)
    out = run_smoke(live=live, require_live=require_live)
    for r in out["results"]:
        flag = {True: "PASS", False: "FAIL", None: "SKIP"}[r["ok"]]
        print(f"[{flag}] {r['kind']:6} {r['id']}: {r['detail']}")
    print("-" * 60)
    print(
        f"static_fail={out['static_fail']} live_fail={out['live_fail']} "
        f"live_skip={out['live_skip']}"
    )
    if report_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))

    hard = out["static_fail"] > 0
    if require_live and out["live_fail"] > 0:
        hard = True
    if ci and hard:
        print("CI FAIL")
        return 1
    if ci:
        print("CI PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
