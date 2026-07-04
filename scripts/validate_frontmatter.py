#!/usr/bin/env python3
"""
validate_frontmatter.py — validate YAML frontmatter in all AGENT.md / SKILL.md / CLAUDE.md
files across the workspace. Detects YAML parse errors, missing closing --- delimiters,
and required-field violations.

Usage:
    python3 scripts/validate_frontmatter.py           # scan all repos
    python3 scripts/validate_frontmatter.py --quick    # skip field-level checks (parse only)
    python3 scripts/validate_frontmatter.py --path DIR # scan specific directory
"""

import argparse
import os
import sys
import yaml
from pathlib import Path

# ── Required fields per file type ──
AGENT_REQUIRED = ["name", "agent_type"]
SKILL_REQUIRED = ["name", "execution_type"]

# ── Per-type validations ──
AGENT_RECOMMENDED = ["model", "status", "display_name"]
SKILL_RECOMMENDED = ["display_name", "version", "status"]


def _parse_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter from a Markdown file. Returns dict or None on error."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        # Missing closing --- delimiter
        return {"_parse_error": "missing_closing_delimiter", "_raw": parts[1] if len(parts) > 1 else ""}

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        return {"_parse_error": f"yaml_parse_error: {e}", "_raw": parts[1][:200]}

    if not isinstance(fm, dict):
        return {"_parse_error": f"not_a_mapping: got {type(fm).__name__}"}

    return fm


def _file_type(filepath: Path) -> str:
    name = filepath.name.upper()
    if name == "AGENT.MD":
        return "agent"
    if name == "SKILL.MD":
        return "skill"
    if name == "CLAUDE.MD":
        return "claude"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Validate YAML frontmatter in Markdown config files")
    parser.add_argument("--quick", action="store_true", help="Skip field-level checks (parse only)")
    parser.add_argument("--path", type=str, help="Scan specific directory")
    parser.add_argument("--json", action="store_true", help="Output JSON (for CI ingestion)")
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parent.parent

    search_dirs = []
    if args.path:
        search_dirs.append(Path(args.path).resolve())
    else:
        # Scan all repos
        for d in [
            workspace_root / "aiPlat-core",
            workspace_root / "aiPlat-infra",
            workspace_root / "aiPlat-platform",
            workspace_root / "aiPlat-management",
            workspace_root / "aiPlat-app",
        ]:
            if d.exists():
                search_dirs.append(d)

        # Scan ~/.aiplat
        home_aiplat = Path.home() / ".aiplat"
        if home_aiplat.exists():
            search_dirs.append(home_aiplat)

    errors = []
    warnings = []
    total_files = 0
    ok_files = 0

    for search_dir in search_dirs:
        for md_file in sorted(search_dir.rglob("*.md")):
            ftype = _file_type(md_file)
            if ftype == "unknown":
                continue  # only check known config file types
            total_files += 1
            rel = md_file.relative_to(workspace_root) if workspace_root in md_file.parents else md_file

            fm = _parse_frontmatter(md_file)
            if fm is None:
                continue  # no frontmatter, skip silently

            parse_err = fm.pop("_parse_error", None) if isinstance(fm, dict) else None
            if parse_err:
                if "missing_closing_delimiter" in parse_err:
                    errors.append(f"{rel}: missing closing '---' delimiter")
                else:
                    errors.append(f"{rel}: {parse_err}")
                continue

            # Quick mode: stop after parse check
            if args.quick:
                ok_files += 1
                continue

            # Required field checks
            if ftype == "agent":
                for field in AGENT_REQUIRED:
                    if field not in fm:
                        errors.append(f"{rel}: missing required field '{field}'")
                for field in AGENT_RECOMMENDED:
                    if field not in fm:
                        warnings.append(f"{rel}: missing recommended field '{field}'")
            elif ftype == "skill":
                for field in SKILL_REQUIRED:
                    if field not in fm:
                        errors.append(f"{rel}: missing required field '{field}'")
                for field in SKILL_RECOMMENDED:
                    if field not in fm:
                        warnings.append(f"{rel}: missing recommended field '{field}'")
            elif ftype == "claude":
                # No required fields for CLAUDE.md, just check parse succeeded
                pass

            ok_files += 1

    # ── Output ──
    if args.json:
        import json
        print(json.dumps({
            "total": total_files,
            "ok": ok_files,
            "errors": len(errors),
            "warnings": len(warnings),
            "error_list": errors,
            "warning_list": warnings,
        }, indent=2))
    else:
        if errors:
            print(f"FRONTMATTER ERRORS ({len(errors)}):")
            for e in errors:
                print(f"  ❌ {e}")
        if warnings:
            print(f"FRONTMATTER WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"  ⚠️  {w}")
        print(f"\nFrontmatter checked: {total_files} files, {ok_files} OK, {len(errors)} errors, {len(warnings)} warnings")

    if errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
