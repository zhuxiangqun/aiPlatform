#!/usr/bin/env python3
"""cleanup_reports.py — apply reports retention (dry-run by default)."""

from __future__ import annotations
import argparse, datetime as dt, re, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "reports"
TODAY = dt.date.today()
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

def rule(rel: str) -> int | None:
    if rel.startswith("products/") and "/ops/" in rel: return 180
    if rel.startswith("security/evidence/"): return 365
    if rel.startswith("docs-governance/"): return 365
    if "/" not in rel and rel.endswith(".md"): return 90
    return None

def date_of(p: Path) -> dt.date | None:
    text = p.read_text(encoding="utf-8", errors="ignore")[:1200]
    m = re.search(r"^(?:generated_at|date)\s*:\s*[\"']?(20\d{2}-\d{2}-\d{2})", text, re.M)
    if m: return dt.date.fromisoformat(m.group(1))
    m = DATE_RE.search(p.name)
    if m: return dt.date.fromisoformat(m.group(1))
    return None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    candidates = []
    for p in REPORTS.rglob("*"):
        if not p.is_file() or "_archive" in p.parts: continue
        rel = str(p.relative_to(REPORTS))
        days = rule(rel)
        if days is None: continue
        d = date_of(p)
        if d is None: continue
        age = (TODAY - d).days
        if age <= days: continue
        candidates.append((p, rel, age, days))
    print(f"candidates={len(candidates)} apply={args.apply}")
    for p, rel, age, days in sorted(candidates, key=lambda x: -x[2])[:30]:
        print(f"  {age:>4}d > {days:>3}d  {rel}")
    if args.apply:
        for p, rel, _age, _days in candidates:
            dst = REPORTS / "_archive" / p.relative_to(REPORTS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dst))
        print(f"moved={len(candidates)} to reports/_archive/")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
