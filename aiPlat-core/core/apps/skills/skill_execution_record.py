"""
SkillExecutionRecord — tracking domain skill execution and adoption.

Stored in execution_store SQLite (table: skill_execution_records).
Written by sys_skill_call after each execution.
Aggregated by SkillBindingStats for pass_rate and adopted_count.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time


@dataclass
class SkillExecutionRecord:
    execution_id: str
    skill_name: str
    domain_id: str = ""
    success: bool = True
    adopted: bool = False
    execution_time_ms: float = 0.0
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "skill_name": self.skill_name,
            "domain_id": self.domain_id,
            "success": self.success,
            "adopted": self.adopted,
            "execution_time_ms": self.execution_time_ms,
            "created_at": self.created_at,
        }


class SkillExecutionStore:
    """SQLite-backed store for skill execution records."""

    _table_name = "skill_execution_records"

    @classmethod
    def ensure_table(cls, db_path: str):
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {cls._table_name} (
                execution_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                domain_id TEXT DEFAULT '',
                success INTEGER DEFAULT 1,
                adopted INTEGER DEFAULT 0,
                execution_time_ms REAL DEFAULT 0.0,
                created_at TEXT DEFAULT ''
            )
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_skill_records_domain
            ON {cls._table_name} (domain_id, skill_name)
        """)
        conn.commit()
        conn.close()

    @classmethod
    def insert(cls, db_path: str, record: SkillExecutionRecord):
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(f"""
            INSERT OR REPLACE INTO {cls._table_name}
            (execution_id, skill_name, domain_id, success, adopted, execution_time_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            record.execution_id,
            record.skill_name,
            record.domain_id,
            1 if record.success else 0,
            1 if record.adopted else 0,
            record.execution_time_ms,
            record.created_at,
        ))
        conn.commit()
        conn.close()

    @classmethod
    def get_recent_pass_rate(cls, db_path: str, skill_name: str, limit: int = 20) -> float:
        """Return pass_rate over the last N executions."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute(f"""
            SELECT COALESCE(SUM(success), 0) * 1.0 / MAX(1, COUNT(*))
            FROM (SELECT success FROM {cls._table_name}
                  WHERE skill_name = ?
                  ORDER BY created_at DESC
                  LIMIT ?)
        """, (skill_name, limit)).fetchone()
        conn.close()
        return round(row[0], 3) if row else 0.0

    @classmethod
    def get_adopted_count(cls, db_path: str, domain_id: str, limit: int = 50) -> int:
        """Return number of adopted executions for a domain (last N)."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute(f"""
            SELECT COALESCE(SUM(adopted), 0)
            FROM (SELECT adopted FROM {cls._table_name}
                  WHERE domain_id = ?
                  ORDER BY created_at DESC
                  LIMIT ?)
        """, (domain_id, limit)).fetchone()
        conn.close()
        return row[0] if row else 0
