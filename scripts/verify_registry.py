#!/usr/bin/env python3
"""
Registry Consistency Verifier — checks all 7 entity registries for:
  1. Duplicate entries
  2. Missing source_path
  3. Non-existent source files
  4. Filesystem orphans (entity on disk but not in registry)
  5. Invalid agent_type values (not in agent_types.yaml)
  6. Invalid execution_type values (not in execution_types.yaml)

Usage:
    python scripts/verify_registry.py          # check all
    python scripts/verify_registry.py agents   # check specific type
    python scripts/verify_registry.py --json   # machine-readable output
    python scripts/verify_registry.py --fix    # auto-discover + register orphans

Exit codes: 0 = clean, 1 = issues found
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aiPlat-core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aiPlat-platform"))


def main():
    parser = argparse.ArgumentParser(description="Verify entity registry consistency")
    parser.add_argument("entity_type", nargs="?", default="all",
                        help="Entity type to check (agents|skills|mcps|workflows|tools|domains|all)")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--fix", action="store_true", help="Auto-discover and register missing entities")
    args = parser.parse_args()

    from core.harness.registry.registry_loader import (
        verify_registry_consistency,
        auto_discover_and_register,
        load_agent_types,
        load_execution_types,
        load_entity_registry,
    )

    entity_types = (["agents", "skills", "mcps", "workflows", "tools", "domains"]
                    if args.entity_type == "all" else [args.entity_type])

    # Load type registries for cross-validation
    agent_types = load_agent_types()
    exec_types = load_execution_types()

    all_issues = []
    for et in entity_types:
        if args.fix:
            n = auto_discover_and_register(et)
            if n > 0 and not args.json:
                print(f"[FIX] {et}: auto-discovered {n} new entities")

        issues = verify_registry_consistency(et)

        # Cross-validate: agent_type values
        if et == "agents":
            records = load_entity_registry(et)
            for r in records:
                at = r.get("agent_type", "")
                if at and not agent_types.is_valid(at):
                    from core.harness.registry.registry_loader import RegistryConsistencyIssue
                    issues.append(RegistryConsistencyIssue(
                        et, "error", r.get("id", "?"),
                        f"Invalid agent_type '{at}' — not in agent_types.yaml"))

        # Cross-validate: execution_type values
        if et == "skills":
            records = load_entity_registry(et)
            for r in records:
                et_val = r.get("execution_type", "")
                if et_val and not exec_types.is_valid(et_val):
                    from core.harness.registry.registry_loader import RegistryConsistencyIssue
                    issues.append(RegistryConsistencyIssue(
                        et, "error", r.get("id", "?"),
                        f"Invalid execution_type '{et_val}' — not in execution_types.yaml"))

        all_issues.extend(issues)

    if args.json:
        output = {
            "entity_types_checked": entity_types,
            "total_issues": len(all_issues),
            "errors": len([i for i in all_issues if i.severity == "error"]),
            "warnings": len([i for i in all_issues if i.severity == "warning"]),
            "issues": [
                {
                    "entity_type": i.entity_type,
                    "severity": i.severity,
                    "entity_id": i.entity_id,
                    "message": i.message,
                }
                for i in all_issues
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        errors = [i for i in all_issues if i.severity == "error"]
        warnings = [i for i in all_issues if i.severity == "warning"]

        for etype in entity_types:
            type_issues = [i for i in all_issues if i.entity_type == etype]
            type_errs = [i for i in type_issues if i.severity == "error"]
            type_warns = [i for i in type_issues if i.severity == "warning"]
            status = "✅" if not type_issues else "❌" if type_errs else "⚠️"
            print(f"{status} {etype}: {len(type_errs)} errors, {len(type_warns)} warnings")
            for i in type_errs[:5]:
                print(f"   ❌ {i.entity_id}: {i.message}")
            for i in type_warns[:5]:
                print(f"   ⚠️  {i.entity_id}: {i.message}")

        if errors:
            print(f"\n❌ {len(errors)} error(s) found — fix before proceeding")
            sys.exit(1)
        elif warnings:
            print(f"\n⚠️  {len(warnings)} warning(s) — review recommended")
        else:
            print(f"\n✅ All {len(entity_types)} registries clean")


if __name__ == "__main__":
    main()
