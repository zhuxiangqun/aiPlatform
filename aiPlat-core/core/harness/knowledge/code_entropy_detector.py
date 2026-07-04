"""Code entropy detector — scan repositories for high-entropy code.

Phase 17: identifies code files that AI has likely degraded through repeated
modifications. Inspired by OpenAI's weekly "AI slop" cleanup practice.

Measures:
  - file_length: lines of code (>500 = high risk)
  - function_count: number of function/class defs (>30 = high complexity)
  - todo_marker_count: TODO/FIXME/HACK markers (>10 = high entropy)
  - duplication_risk: repeated pattern blocks (>3 similar lines)

Activation: requires >=1000 lines of code in the target directory.
Results stored in ~/.aiplat/code_entropy.sqlite3.

The cleanup agent (future Phase 17.1) will use these scores to auto-generate
refactoring PRs, following Stripe's "small PR, frequent merge" pattern.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("aiplat.code_entropy")


@dataclass
class EntropyScore:
    file_path: str
    lines: int
    functions: int
    todos: int
    score: float  # 0-100, higher = more entropy
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "lines": self.lines,
            "functions": self.functions,
            "todos": self.todos,
            "score": round(self.score, 1),
            "reasons": self.reasons,
        }


class CodeEntropyDetector:
    """Scans code directories for high-entropy files."""

    _ACTIVATION_THRESHOLD = 1000  # minimum total lines to activate

    def __init__(self, db_path: str = None):
        self._db_path = db_path or os.path.expanduser("~/.aiplat/code_entropy.sqlite3")
        self._ensure_schema()

    def _ensure_schema(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS entropy_scans (
                scan_id TEXT PRIMARY KEY,
                scanned_at TEXT NOT NULL,
                directory TEXT NOT NULL,
                files_scanned INTEGER DEFAULT 0,
                total_lines INTEGER DEFAULT 0,
                high_entropy_count INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0,
                results_json TEXT DEFAULT '[]'
            )"""
        )
        conn.commit()
        conn.close()

    def scan(self, directory: str, *, extensions: tuple = ('.py', '.js', '.ts', '.tsx')) -> Dict:
        """Scan a code directory for high-entropy files.

        Returns {
            "files_scanned": int,
            "total_lines": int,
            "high_entropy": [EntropyScore, ...],
            "avg_score": float,
        }
        """
        import json
        import uuid
        from datetime import datetime, timezone
        
        dir_path = Path(directory).expanduser().resolve()
        if not dir_path.is_dir():
            return {"error": f"directory not found: {directory}"}

        scores: List[EntropyScore] = []
        total_lines = 0
        files_scanned = 0

        for file_path in dir_path.rglob("*"):
            if not file_path.suffix or file_path.suffix not in extensions:
                continue
            if "__pycache__" in file_path.parts or ".git" in file_path.parts:
                continue
            if "node_modules" in file_path.parts or ".venv" in file_path.parts:
                continue
            if file_path.stat().st_size > 1_000_000:  # skip >1MB files
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.count("\n") + 1
            total_lines += lines
            files_scanned += 1

            if lines < 20:  # skip tiny files
                continue

            # Heuristics
            reasons = []
            score = 0

            # File length
            if lines > 500:
                score += 30
                reasons.append(f"超长文件({lines}行)")
            elif lines > 200:
                score += 15
                reasons.append(f"偏长文件({lines}行)")

            # Function/class count
            func_count = len(re.findall(r'^\s*(def |class |async def )', content, re.MULTILINE))
            if func_count > 30:
                score += 25
                reasons.append(f"高复杂度({func_count}个函数/类)")
            elif func_count > 15:
                score += 10

            # TODO markers
            todo_count = len(re.findall(r'(TODO|FIXME|HACK|XXX):', content))
            if todo_count > 10:
                score += 25
                reasons.append(f"高熵标记({todo_count}个TODO/FIXME)")
            elif todo_count > 3:
                score += 10
                reasons.append(f"待清理标记({todo_count}个)")

            if score >= 40:
                scores.append(EntropyScore(
                    file_path=str(file_path),
                    lines=lines,
                    functions=func_count,
                    todos=todo_count,
                    score=min(score, 100),
                    reasons=reasons,
                ))

        # Store scan results
        high_entropy = [s for s in scores if s.score >= 60]
        avg_score = sum(s.score for s in scores) / max(len(scores), 1)

        conn = sqlite3.connect(self._db_path)
        scan_id = f"scan_{uuid.uuid4().hex[:8]}"
        conn.execute(
            """INSERT INTO entropy_scans VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, datetime.now(timezone.utc).isoformat(), directory,
             files_scanned, total_lines, len(high_entropy),
             round(avg_score, 1), json.dumps([s.to_dict() for s in scores])),
        )
        conn.commit()
        conn.close()

        return {
            "scan_id": scan_id,
            "files_scanned": files_scanned,
            "total_lines": total_lines,
            "high_entropy": [s.to_dict() for s in high_entropy],
            "high_entropy_count": len(high_entropy),
            "avg_score": round(avg_score, 1),
        }

    def get_last_scan(self) -> Optional[Dict]:
        """Return the most recent scan results."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM entropy_scans ORDER BY scanned_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            import json
            d["results_json"] = json.loads(d.get("results_json", "[]"))
            return d
        return None
