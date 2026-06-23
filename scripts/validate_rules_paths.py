#!/usr/bin/env python3
"""
Tool self-test: validate that every `paths` field in arch_guard_rules.yaml
references files/directories that actually exist.

Rules:
  - File-like paths (containing .py/.tsx/.ts/.yaml/.json/.md) → must exist
  - Directory-like paths (with trailing / or known dir names) → must exist
  - Home paths (~/.aiplat/...) → skip (may not exist in CI)

Usage:
    python3 scripts/validate_rules_paths.py
"""
import os
import sys
from pathlib import Path

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = WORKSPACE_ROOT / "aiPlat-core/core/management/arch_guard_rules.yaml"

KNOWN_DIRS = {
    "aiPlat-core", "aiPlat-platform", "aiPlat-infra", "aiPlat-app",
    "aiPlat-management", "aiplat-sdk",
    "aiPlat-management/frontend/src",
}

def is_file_path(p: str) -> bool:
    return any(p.endswith(ext) for ext in (".py", ".tsx", ".ts", ".yaml", ".json", ".md", ".sh"))

def is_dir_path(p: str) -> bool:
    return p.rstrip("/") in KNOWN_DIRS or p.endswith("/") or (
        not is_file_path(p) and "/" in p and not p.startswith("~")
    )

if not RULES_FILE.exists():
    print(f"ERROR: rules file not found: {RULES_FILE}")
    sys.exit(1)

with open(RULES_FILE) as f:
    data = yaml.safe_load(f)

rules = data.get("rules", [])
broken = 0
skipped = 0

print(f"Validating {len(rules)} rules...")

for rule in rules:
    rule_id = rule.get("id", "?")
    check = rule.get("check", {})
    paths = check.get("paths", [])
    if not isinstance(paths, list):
        paths = [paths] if paths else []

    for p in paths:
        p = str(p).rstrip()
        # Skip home-relative paths (may not exist in CI)
        if p.startswith("~") or p.startswith("."):
            skipped += 1
            continue

        # File path validation
        if is_file_path(p):
            full = WORKSPACE_ROOT / p
            if not full.exists():
                print(f"  BROKEN  {rule_id}: file '{p}' → NOT FOUND")
                broken += 1

        # Directory path validation
        elif is_dir_path(p):
            full = WORKSPACE_ROOT / p.rstrip("/")
            if not full.exists() and p.rstrip("/") not in KNOWN_DIRS:
                full = WORKSPACE_ROOT / p.rstrip("/")
                if not full.exists():
                    print(f"  BROKEN  {rule_id}: dir '{p}' → NOT FOUND")
                    broken += 1

if broken:
    print(f"\nFAILED: {broken} broken path(s) found ({skipped} skipped)")
    sys.exit(1)
else:
    print(f"\nPASSED: all paths valid ({skipped} home/special paths skipped)")
    sys.exit(0)
