"""
Apply mature refinements — cron job triggered daily at 3:30 AM.

Reads refinement_candidates table for suggestions with vote_count ≥ 3,
backs up AGENT.md, appends to ## AUTO_REFINED block, marks as applied.

Safety: never overwrites existing AGENT.md content — only appends.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time as _time
from pathlib import Path

logger = logging.getLogger("aiplat.refinement")


async def apply_mature_refinements() -> dict:
    """Apply suggestions that have been verified by ≥3 pipeline runs.

    Returns:
        {"applied": N, "backups": ["path1", ...], "errors": M}
    """
    db = os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")
    if not os.path.isfile(db):
        return {"applied": 0, "backups": [], "errors": 0}

    conn = sqlite3.connect(db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT * FROM refinement_candidates
            WHERE status = 'pending' AND vote_count >= 3
            ORDER BY confidence DESC LIMIT 5
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"applied": 0, "backups": [], "errors": 0}

    result = {"applied": 0, "backups": [], "errors": 0}
    conn = sqlite3.connect(db, timeout=5.0)
    try:
        for row in rows:
            try:
                target = row["target_model"]
                suggestion = row["suggestion_text"]
                vote = row["vote_count"]

                # Find AGENT.md path
                agent_paths = [
                    os.path.expanduser(f"~/.aiplat/agents/{target}/AGENT.md"),
                    os.path.join(os.getcwd(), f"agents/{target}/AGENT.md"),
                ]
                target_path = None
                for p in agent_paths:
                    if os.path.isfile(p):
                        target_path = p
                        break

                if not target_path:
                    logger.debug("AGENT.md not found for %s, skipping", target)
                    result["errors"] += 1
                    continue

                # Backup
                now_str = _time.strftime("%Y%m%d%H%M%S")
                backup = f"{target_path}.bak_{now_str}"
                shutil.copy2(target_path, backup)
                result["backups"].append(backup)

                # Append to AUTO_REFINED block
                with open(target_path, "a", encoding="utf-8") as f:
                    f.write(f"\n\n## AUTO_REFINED (AI Generated — Verified {vote} times)\n")
                    f.write(f"> {suggestion}\n")

                # Mark applied
                conn.execute(
                    "UPDATE refinement_candidates SET status = 'applied' WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                result["applied"] += 1
                logger.info("Applied refinement to %s (backup: %s)", target_path, backup)

            except Exception as e:
                logger.warning("Failed to apply refinement %s: %s", row.get("id"), str(e)[:200])
                result["errors"] += 1
    finally:
        conn.close()

    return result
