#!/usr/bin/env python3
"""cleanup_reports.py — apply reports retention (dry-run by default).

Date resolution order (first hit wins):
1. frontmatter / header ``generated_at`` / ``date`` (YYYY-MM-DD)
2. full ISO date in filename
3. year-month in filename (``YYYY-MM`` → day 1 of that month)
4. first ISO date in the first 1200 chars of body
5. with ``--mtime-fallback``: file mtime (last resort; recent git touches can mask age)
"""

from __future__ import annotations
import argparse
import datetime as dt
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "reports"
TODAY = dt.date.today()
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
YEAR_MONTH_RE = re.compile(r"(20\d{2})-(\d{2})(?!\d)")
# Compact evidence stamps: 20261101T032316Z
COMPACT_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})T\d{6}Z?")


def rule(rel: str) -> int | None:
    """Return retention days for a reports-relative path, or None if not governed.

    Args:
        rel: Path relative to ``reports/``.
    """
    if (rel.startswith("products/") or rel.startswith("five-products/")) and "/ops/" in rel:
        return 180
    if rel.startswith("security/evidence/"):
        return 365
    if rel.startswith("docs-governance/"):
        return 365
    if "/" not in rel and rel.endswith(".md"):
        return 90
    return None


def date_of(p: Path, *, mtime_fallback: bool = False) -> tuple[dt.date | None, str]:
    """Best-effort content date for retention age.

    Why prefer the earliest signal: root analysis snapshots often carry a fresh
    ``generated_at`` from re-wrapping while the filename/body still encodes the
    historical snapshot month (e.g. ``*_2026-04.md``).

    Args:
        p: Report file path.
        mtime_fallback: If True, use filesystem mtime when no content date exists.

    Returns:
        ``(date, source)`` where source names the winning signal.
    """
    text = p.read_text(encoding="utf-8", errors="ignore")[:1200]
    candidates: list[tuple[dt.date, str]] = []

    # snapshot_date / content_date encode historical age; generated_at is often a re-wrap stamp.
    for m in re.finditer(
        r"^(?:snapshot_date|content_date|generated_at|date)\s*:\s*[\"']?(20\d{2}-\d{2}-\d{2})",
        text,
        re.M,
    ):
        key = m.group(0).split(":", 1)[0].strip()
        candidates.append((dt.date.fromisoformat(m.group(1)), f"fm:{key}"))
    m = DATE_RE.search(p.name)
    if m:
        candidates.append((dt.date.fromisoformat(m.group(1)), "name_iso"))
    m = YEAR_MONTH_RE.search(p.name)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            candidates.append((dt.date(y, mo, 1), "name_ym"))
    m = COMPACT_RE.search(p.name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            candidates.append((dt.date(y, mo, d), "name_compact"))
        except ValueError:
            pass
    m = DATE_RE.search(text)
    if m:
        candidates.append((dt.date.fromisoformat(m.group(1)), "body"))

    if candidates:
        # Earliest date wins (historical snapshot > recent re-stamp).
        best = min(candidates, key=lambda x: x[0])
        return best[0], best[1]
    if mtime_fallback:
        return dt.datetime.fromtimestamp(p.stat().st_mtime).date(), "mtime"
    return None, "none"


def main() -> int:
    """CLI entry: dry-run retention candidates; ``--apply`` moves into ``_archive/``."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--mtime-fallback",
        action="store_true",
        help="Use file mtime when no content/filename date is found",
    )
    args = ap.parse_args()
    candidates = []
    undated = []
    governed = 0
    for p in REPORTS.rglob("*"):
        if not p.is_file() or "_archive" in p.parts:
            continue
        rel = str(p.relative_to(REPORTS))
        days = rule(rel)
        if days is None:
            continue
        governed += 1
        d, src = date_of(p, mtime_fallback=args.mtime_fallback)
        if d is None:
            undated.append(rel)
            continue
        age = (TODAY - d).days
        if age <= days:
            continue
        candidates.append((p, rel, age, days, src))
    print(f"governed={governed} candidates={len(candidates)} undated={len(undated)} apply={args.apply}")
    for _p, rel, age, days, src in sorted(candidates, key=lambda x: -x[2])[:40]:
        print(f"  {age:>4}d > {days:>3}d  [{src}]  {rel}")
    if undated:
        print("undated (skipped; add YYYY-MM-DD or use --mtime-fallback):")
        for rel in undated[:20]:
            print(f"  - {rel}")
        if len(undated) > 20:
            print(f"  ... +{len(undated) - 20} more")
    if args.apply:
        for p, rel, _age, _days, _src in candidates:
            dst = REPORTS / "_archive" / p.relative_to(REPORTS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dst))
        print(f"moved={len(candidates)} to reports/_archive/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
