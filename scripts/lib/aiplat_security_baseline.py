#!/usr/bin/env python3
"""Shared security baseline file checks for five-products D2 packs.

Usage:
  python3 scripts/lib/aiplat_security_baseline.py <repo_root> <baseline.yaml>
"""
from __future__ import annotations

import sys
from pathlib import Path


def check_baseline(root: Path, baseline: Path) -> int:
    text = baseline.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        data = None

    errors: list[str] = []
    if data is None:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("path:"):
                rel = s.split(":", 1)[1].strip().strip('"').strip("'")
                if not (root / rel).exists():
                    errors.append(f"missing {rel}")
        if errors:
            print("FAIL security baseline (path scan):")
            for e in errors:
                print(" -", e)
            return 1
        print(f"OK security baseline path-scan (PyYAML unavailable) file={baseline}")
        return 0

    for c in data.get("checks") or []:
        cid = c.get("id")
        rel = c.get("path")
        p = root / str(rel)
        if not p.is_file():
            errors.append(f"{cid}: missing {rel}")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        for needle in c.get("must_contain") or []:
            if str(needle) not in body:
                errors.append(f"{cid}: missing snippet {needle!r} in {rel}")

    if errors:
        print("FAIL security baseline:")
        for e in errors:
            print(" -", e)
        return 1

    n = len(data.get("checks") or [])
    print(f"OK security baseline checks={n} file={baseline}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "usage: aiplat_security_baseline.py <repo_root> <baseline.yaml>",
            file=sys.stderr,
        )
        return 2
    root = Path(args[0])
    baseline = Path(args[1])
    if not baseline.is_file():
        print(f"ERROR: missing {baseline}", file=sys.stderr)
        return 2
    return check_baseline(root, baseline)


if __name__ == "__main__":
    raise SystemExit(main())
