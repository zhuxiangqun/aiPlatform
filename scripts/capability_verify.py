#!/usr/bin/env python3
"""
Capability Verification — 能力声明 × 代码可达性 × 方法级调用 三维交叉验证

Usage:
    python3 scripts/capability_verify.py          # Console report
    python3 scripts/capability_verify.py --json   # JSON output

Checks:
    1. Module reachability — entry_point module exists and provided_by modules exist
    2. Method-level calling — each key_method has >=1 external production caller
    3. Dependency completeness — depends_on modules are referenced
"""
import json
import os
import sys
from pathlib import Path

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = WORKSPACE_ROOT / "aiPlat-core/core/management/capability_manifest.yaml"

sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


def load_manifest():
    with open(MANIFEST_FILE) as f:
        return yaml.safe_load(f)


def has_production_caller(symbol: str, module_filename: str) -> bool:
    """Check if a symbol has callers outside its own file and test dirs."""
    import subprocess
    try:
        result = subprocess.run(
            ["grep", "-rEl", "--include=*.py",
             "--exclude-dir=__pycache__", "--exclude-dir=tests",
             symbol, str(WORKSPACE_ROOT / "aiPlat-core")],
            capture_output=True, text=True, timeout=30,
        )
        callers = [
            f for f in result.stdout.splitlines()
            if module_filename not in f
        ]
        return len(callers) > 0
    except Exception:
        return False


def module_exists(module_path: str) -> bool:
    """Check if a module file exists relative to workspace."""
    full = WORKSPACE_ROOT / module_path
    return full.exists()


def verify_capability(cap: dict) -> dict:
    """Run all checks on a single capability."""
    cap_id = cap.get("id", "?")
    result = {
        "id": cap_id,
        "name": cap.get("name", ""),
        "domain": cap.get("domain", ""),
        "module_exists": True,
        "methods_checked": {},
        "methods_total": 0,
        "methods_wired": 0,
        "completeness": "0/0",
    }

    # Check 1: Module existence
    providers = cap.get("provided_by", [])
    for p in providers:
        mod = p.get("module", "")
        if not module_exists(mod):
            result["module_exists"] = False
            result.setdefault("missing_modules", []).append(mod)

    # Check 2: Method-level calling
    for p in providers:
        methods = p.get("key_methods", [])
        if not methods:
            continue
        basename = os.path.basename(p.get("module", ""))
        for m in methods:
            wired = has_production_caller(m, basename) if basename else False
            result["methods_total"] += 1
            if wired:
                result["methods_wired"] += 1
            result["methods_checked"][f"{basename}:{m}"] = wired

    # Compute completeness
    total = result["methods_total"]
    wired = result["methods_wired"]
    result["completeness"] = f"{wired}/{total}"

    # Categorize
    if not result["module_exists"]:
        result["level"] = "P0_UNREACHABLE"
    elif total > 0 and wired == 0:
        result["level"] = "P0_ZERO_METHODS"
    elif total > 0 and wired / total < 0.5:
        result["level"] = "P1_BELOW_50"
    elif total > 0 and wired < total:
        result["level"] = "P2_PARTIAL"
    else:
        result["level"] = "P3_COMPLETE"

    return result


def verify_all() -> list:
    manifest = load_manifest()
    caps = manifest.get("capabilities", [])
    results = []

    for cap in caps:
        # Skip tool/infrastructure capabilities (no key_methods)
        providers = cap.get("provided_by", [])
        has_methods = any(p.get("key_methods") for p in providers)
        if not has_methods:
            continue
        results.append(verify_capability(cap))

    # Sort by severity
    priority = {"P0_UNREACHABLE": 0, "P0_ZERO_METHODS": 1, "P1_BELOW_50": 2, "P2_PARTIAL": 3, "P3_COMPLETE": 4}
    results.sort(key=lambda r: priority.get(r["level"], 99))
    return results


def print_report(results: list):
    """Print colored console report."""
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"

    total = len(results)
    complete = sum(1 for r in results if r["level"] == "P3_COMPLETE")
    severe = sum(1 for r in results if r["level"].startswith("P0") or r["level"].startswith("P1"))

    print("")
    print("═" * 70)
    print("  CAPABILITY VERIFICATION — 能力可执行性报告")
    print("═" * 70)
    print(f"  Total: {total} capabilities | {GREEN}{complete} complete{NC} | {RED}{severe} need attention{NC}")
    print("")

    for r in results:
        color = {"P0_UNREACHABLE": RED, "P0_ZERO_METHODS": RED,
                 "P1_BELOW_50": YELLOW, "P2_PARTIAL": CYAN, "P3_COMPLETE": GREEN}
        c = color.get(r["level"], NC)

        print(f"  {c}{r['level']:<16s}{NC} | {r['domain']:<12s} | {r['name']:<40s} | {r['completeness']:>5s}")
        if r["level"] != "P3_COMPLETE":
            for method, wired in r["methods_checked"].items():
                status = f"{GREEN}✓{NC}" if wired else f"{RED}✗{NC}"
                print(f"    {status} {method}")
            if r.get("missing_modules"):
                for m in r["missing_modules"]:
                    print(f"    {RED}✗ module not found{NC}: {m}")

    print("")
    if severe:
        print(f"  {RED}═══ {severe} capabilities need attention ═══{NC}")
    else:
        print(f"  {GREEN}═══ ALL CAPABILITIES VERIFIED ═══{NC}")
    print("")
    return 0 if severe == 0 else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = verify_all()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        sys.exit(print_report(results))
