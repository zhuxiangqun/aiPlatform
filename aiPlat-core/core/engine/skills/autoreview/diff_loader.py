"""
diff_loader.py — Git Diff loader. Never returns full files.

target types:
  - 'diff'          → git diff --unified=3 HEAD
  - 'commit:<sha>'  → git diff --unified=3 <sha>^..<sha>
  - 'branch:main'   → git diff --unified=3 origin/main...HEAD

Safety: diffs >8000 tokens are truncated (function signatures + first/last 200 lines).
Always uses a subprocess timeout so a huge worktree cannot wedge the event loop.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional

MAX_DIFF_TOKENS = 8000       # ~3000 lines of unified diff
MAX_NEW_FILE_LINES = 3000
# Hard cap: monorepo `git diff` without GIT_WORK_TREE previously hung workers for minutes.
_DEFAULT_GIT_TIMEOUT = float(os.getenv("AIPLAT_AUTOREVIEW_GIT_TIMEOUT", "30") or "30")

_log = logging.getLogger(__name__)


@dataclass
class DiffResult:
    files: List[str]
    content: str
    total_lines: int
    truncated: bool = False


def load_diff(target: str, *, cwd: Optional[str] = None, timeout: Optional[float] = None) -> DiffResult:
    cmd = _build_git_cmd(target)
    work = (cwd or os.environ.get("GIT_WORK_TREE") or "").strip() or None
    if work and not os.path.isdir(work):
        work = None
    to = _DEFAULT_GIT_TIMEOUT if timeout is None else float(timeout)
    to = max(5.0, min(120.0, to))
    env = os.environ.copy()
    run_cwd = None
    if work:
        # Prefer explicit worktree cwd; drop GIT_* so git does not mix repos.
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        run_cwd = work
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=run_cwd,
            env=env,
            timeout=to,
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "load_diff timed out after %.1fs target=%s cwd=%s",
            to,
            target,
            run_cwd or "(env/process)",
        )
        return DiffResult(files=[], content="", total_lines=0, truncated=True)
    except Exception:
        _log.warning("load_diff failed target=%s", target, exc_info=True)
        return DiffResult(files=[], content="", total_lines=0)

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
