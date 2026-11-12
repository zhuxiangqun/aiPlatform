#!/usr/bin/env python3
"""Backfill generated_at for active reports from git last-commit date."""
from __future__ import annotations
import re, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
log = subprocess.check_output(
    ["git", "log", "--format=C%cs", "--name-only", "--", "reports"],
    cwd=REPO, text=True, errors="ignore",
)
dates: dict[str, str] = {}
cur = ""
for line in log.splitlines():
    if line.startswith("C") and re.fullmatch(r"C\d{4}-\d{2}-\d{2}", line):
        cur = line[1:]
    elif line.strip() and cur:
        dates.setdefault(line.strip(), cur)

added = 0
for p in (REPO / "reports").rglob("*.md"):
    if "_archive" in p.parts or p.name.lower() == "readme.md":
        continue
    rel = str(p.relative_to(REPO))
    s = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"^generated_at\s*:", s[:1500], re.M):
        continue
    m = re.search(r"^date\s*:\s*[\"']?(20\d{2}-\d{2}-\d{2})", s[:1500], re.M)
    day = m.group(1) if m else dates.get(rel, "2026-11-12")
    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", s, re.S)
    if fm:
        s = s[:fm.start(1)] + f"generated_at: {day}\n" + s[fm.start(1):]
    else:
        s = f"---\ndoc_type: Report\ngenerated_at: {day}\n---\n\n" + s
    p.write_text(s)
    added += 1
print(f"generated_at added: {added}")
