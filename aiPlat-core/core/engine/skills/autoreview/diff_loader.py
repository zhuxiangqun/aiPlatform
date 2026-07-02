"""
diff_loader.py — Git Diff loader. Never returns full files.

target types:
  - 'diff'          → git diff --unified=3 HEAD
  - 'commit:<sha>'  → git diff --unified=3 <sha>^..<sha>
  - 'branch:main'   → git diff --unified=3 origin/main...HEAD

Safety: diffs >8000 tokens are truncated (function signatures + first/last 200 lines).
"""

import subprocess
from dataclasses import dataclass
from typing import List

MAX_DIFF_TOKENS = 8000       # ~3000 lines of unified diff
MAX_NEW_FILE_LINES = 3000


@dataclass
class DiffResult:
    files: List[str]
    content: str
    total_lines: int
    truncated: bool = False


def load_diff(target: str) -> DiffResult:
    cmd = _build_git_cmd(target)
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = (result.stdout or result.stderr or "").strip()
    if not raw:
        return DiffResult(files=[], content="", total_lines=0)

    lines = raw.split("\n")
    total = len(lines)
    truncated = total > MAX_DIFF_TOKENS * 2
    content = _truncate_diff(raw) if truncated else raw
    files = _extract_files(raw)
    return DiffResult(files=files, content=content, total_lines=total, truncated=truncated)


def _build_git_cmd(target: str) -> list:
    if target == "diff":
        return ["git", "diff", "--unified=3", "HEAD"]
    if target.startswith("commit:"):
        sha = target.split(":", 1)[1]
        return ["git", "diff", "--unified=3", f"{sha}^..{sha}"]
    if target.startswith("branch:"):
        base = target.split(":", 1)[1]
        return ["git", "diff", "--unified=3", f"origin/{base}...HEAD"]
    raise ValueError(
        f"Unsupported target: {target}. Use 'diff', 'commit:<sha>', or 'branch:<name>'."
    )


def _truncate_diff(raw: str) -> str:
    """Truncate oversized diff: keep function signatures + first/last 200 lines per file.
    Preserves dev/null lines for delete/create detection."""
    parts = raw.split("diff --git ")
    if len(parts) <= 11:  # 10 files or fewer → keep all
        return raw

    result = [parts[0]]
    for chunk in parts[1:]:
        chunk_lines = chunk.split("\n")
        filtered = [l for l in chunk_lines if (
            l.startswith(("+", "-", "@@", "diff "))
            or "def " in l or "class " in l
            or "dev/null" in l
        )]
        result.append("\n".join(filtered[:200]))

    return "diff --git ".join(result)


def _extract_files(raw: str) -> List[str]:
    files = []
    for line in raw.split("\n"):
        if line.startswith("diff --git a/"):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3][2:])  # strip "b/" prefix
    return files
