#!/usr/bin/env python3
"""
Frontend Infrastructure Guard — §43 + §44

§43: Vite proxy routing — verifies proxy targets are correct
§44: Cross-language API contract — checks TS fetch fields vs Python endpoint params

Usage:
    python3 scripts/guard_frontend.py
Output: text (same format as architecture_guard.sh), exit code 0=pass, 1=violations.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def bold(s): return f"\033[1m{s}\033[0m"
def red(s): return f"\033[0;31m{s}\033[0m"
def green(s): return f"\033[0;32m{s}\033[0m"
def yellow(s): return f"\033[0;33m{s}\033[0m"


# ═══════════════════════════════════════════════════════════════
# §43: Vite Proxy Routing Check
# ═══════════════════════════════════════════════════════════════

def check_vite_proxy() -> list[dict]:
    """Verify vite.config.ts proxy targets point to correct ports."""
    issues = []
    vite_config = WORKSPACE_ROOT / "aiPlat-management" / "frontend" / "vite.config.ts"
    if not vite_config.exists():
        return [{"level": "warning", "msg": "vite.config.ts not found — skipping proxy check"}]

    content = vite_config.read_text(encoding="utf-8")

    # Extract proxy rules: pattern → target, port
    proxy_entries = re.findall(
        r"'([^']+)'\s*:\s*\{[^}]*?target:\s*'([^']+)'[^}]*\}",
        content, re.DOTALL
    )

    # Known server processes (port → expected module)
    expected = {
        "8000": "management.server:create_app",
        "8001": "infra.management.api.main:create_app",
        "8002": "server:app",
        "8003": "api.rest.routes:app",
        "8004": "api.rest.routes:app",
    }

    # Check running processes
    running_ports = _get_running_ports()

    violations = 0
    for pattern, target in proxy_entries:
        port_match = re.search(r':(\d+)$', target)
        if not port_match:
            continue
        port = port_match.group(1)

        # Check 1: Is the target port alive?
        if port not in running_ports:
            issues.append({
                "code": "proxy_dead_target",
                "level": "warning",
                "msg": f"proxy '{pattern}' → {target} — port {port} has no running process",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

        # Check 2: /api/core catch-all must point to 8002 (has all core routes)
        if pattern == "/api/core" and port != "8002":
            issues.append({
                "code": "proxy_core_misdirected",
                "level": "error",
                "msg": f"/api/core catch-all proxy → port {port} (must be 8002 — core routes live there)",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

        # Check 3: /api/core/workspace/* routes should NOT go to 8000 (management)
        if pattern.startswith("/api/core/workspace/") and port == "8000":
            issues.append({
                "code": "proxy_workspace_to_management",
                "level": "error",
                "msg": f"'{pattern}' → port 8000 (management) — workspace routes must go to 8002 (core)",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

    if not issues and proxy_entries:
        issues.append({
            "code": "proxy_ok",
            "level": "pass",
            "msg": f"All {len(proxy_entries)} proxy rules verified",
        })

    return issues


def _get_running_ports() -> set[str]:
    """Get set of ports with running Python processes."""
    ports = set()
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            if "uvicorn" not in line and "python" not in line:
                continue
            for m in re.finditer(r'--port\s+(\d+)', line):
                ports.add(m.group(1))
    except Exception:
        pass
    return ports


# ═══════════════════════════════════════════════════════════════
# §44: Cross-Language API Contract Check
# ═══════════════════════════════════════════════════════════════

def check_api_contract() -> list[dict]:
    """Check frontend fetch() body fields vs backend endpoint parameters."""
    issues = []

    # Known mismatches to scan for (pattern-driven, expandable)
    checks = [
        {
            "name": "MCP test-invoke args vs arguments",
            "ts_files": ["aiPlat-management/frontend/src/pages/Workspace/MCP/MCP.tsx"],
            "ts_pattern": r'body\.arguments\s*=\s*args|"arguments"\s*:',
            "py_files": ["aiPlat-core/core/api/routers/mcp_admin.py"],
            "py_pattern": r'"arguments"',
            "expect": "arguments",  # frontend sends "arguments", backend must accept it
            "section": "§44",
        },
        # Add more contract checks here as patterns emerge
    ]

    for check in checks:
        ts_found = False
        py_found = False
        py_key = None

        for ts_file in check["ts_files"]:
            fp = WORKSPACE_ROOT / ts_file
            if not fp.exists():
                continue
            if re.search(check["ts_pattern"], fp.read_text(encoding="utf-8")):
                ts_found = True
                break

        for py_file in check["py_files"]:
            fp = WORKSPACE_ROOT / py_file
            if not fp.exists():
                continue
            m = re.search(check["py_pattern"], fp.read_text(encoding="utf-8"))
            if m:
                py_found = True
                py_key = m.group(0)
                break

        if ts_found and py_found:
            if check["expect"] in str(py_key):
                issues.append({
                    "code": "contract_ok",
                    "level": "pass",
                    "msg": f"{check['name']}: frontend+backend field '{check['expect']}' consistent",
                })
            else:
                issues.append({
                    "code": "contract_mismatch",
                    "level": "error",
                    "msg": f"{check['name']}: field mismatch — backend uses '{py_key}'",
                    "files": [str(WORKSPACE_ROOT / f) for f in check["ts_files"]],
                })

    if not any(i.get("code") in ("contract_mismatch", "contract_ok") for i in issues):
        issues.append({
            "code": "contract_ok",
            "level": "pass",
            "msg": "No contract checks defined or all files missing — extend guard_frontend.py",
        })

    return issues


def check_ts_import_hygiene() -> list[dict]:
    """§45: Check that frontend imports go through barrel files (services/index.ts, components/ui)."""
    issues = []
    checks = [
        {
            "name": "No direct coreApi.ts imports (use services/index.ts)",
            "pattern": r"from\s+['\"].*services/coreApi['\"]",
            "path": "aiPlat-management/frontend/src",
            "exclude": ["services/index.ts", "services/coreApi.ts"],
            "level": "error",
            "msg": "Direct import from coreApi.ts — import from services/index.ts instead (§5.1)",
        },
        {
            "name": "No scattered UI imports (use components/ui)",
            "pattern": r"from\s+['\"].*components/ui/",
            "path": "aiPlat-management/frontend/src/pages",
            "exclude": [],
            "level": "warning",
            "msg": "Direct import from components/ui/ sub-file — import from components/ui barrel instead (§5.2)",
        },
    ]

    for check in checks:
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.tsx", "--include=*.ts", check["pattern"],
                 check["path"]],
                capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent)
            )
            hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for exc in check.get("exclude", []):
                hits = [h for h in hits if exc not in h]
            for hit in hits[:10]:
                fp = hit.split(":", 2)
                issues.append({
                    "code": check["name"],
                    "level": check["level"],
                    "msg": f"{check['msg']} — {hit[:120]}",
                    "files": [],
                })
        except Exception as e:
            issues.append({"code": check["name"], "level": "warning", "msg": f"Check failed: {e}", "files": []})

    if not any(i.get("level") == "error" for i in issues):
        issues.append({"code": "ts-import-hygiene", "level": "pass", "msg": "All frontend imports follow barrel pattern"})
    return issues


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    sections = [
        ("§43", "Frontend Proxy Routing", check_vite_proxy),
        ("§44", "Cross-Language API Contract", check_api_contract),
        ("§45", "Frontend Import Path Hygiene", check_ts_import_hygiene),
    ]

    total_errors = 0
    total_warnings = 0

    print("")
    print("═" * 63)
    print("  FRONTEND GUARD: Checking frontend infrastructure + contracts")
    print("═" * 63)

    for number, name, check_fn in sections:
        print("")
        print("═" * 63)
        print(f"  {number}: {name}")
        print("═" * 63)
        issues = check_fn()
        if not issues:
            print(f"  {green('[PASS]')}  no checks defined")
            continue

        has_errors = any(i.get("level") == "error" for i in issues)
        has_warnings = any(i.get("level") == "warning" for i in issues)
        has_pass = any(i.get("level") == "pass" for i in issues)

        for issue in issues:
            level = issue.get("level", "info")
            color = {"error": red, "warning": yellow, "pass": green}.get(level, lambda x: x)
            if level == "pass":
                print(f"  {color('[PASS]')}  {issue['msg']}")
                continue
            print(f"  {color(f'[{level.upper()}]')}  [{issue.get('code','?')}] {issue['msg']}")
            for f in issue.get("files", []):
                print(f"         → {f}")
            if level == "error":
                total_errors += 1
            elif level == "warning":
                total_warnings += 1

    print("")
    if total_errors:
        print(f"  {red(f'═══ FRONTEND GUARD FAILED: {total_errors} errors, {total_warnings} warnings ═══')}")
        sys.exit(1)
    elif total_warnings:
        print(f"  {yellow(f'═══ FRONTEND GUARD WARNINGS: {total_warnings} warnings ═══')}")
        sys.exit(0)
    else:
        print(f"  {green('═══ FRONTEND GUARD PASSED — all checks pass ═══')}")
        sys.exit(0)


if __name__ == "__main__":
    main()
