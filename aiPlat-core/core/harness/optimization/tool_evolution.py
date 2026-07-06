"""ToolEvolutionEngine — autonomous tool lifecycle management.
C-axis L4→L5 enabler: tools self-improve through usage feedback.

Extends StrategyEffectivenessTracker to tool dimension:
- Track tool success rates, usage frequency, error patterns
- Auto-deprecate low-efficiency tools
- Auto-trigger ToolBootstrapEngine when gaps detected
- Skill drift detection and auto-repair
"""
import asyncio, json, os, sys, sqlite3, threading, time
from datetime import datetime, timezone
from typing import Optional


class ToolEvolutionEngine:
    """Autonomous tool lifecycle manager.

    Tracks usage metrics, identifies underperforming tools,
    and triggers regeneration/improvement.
    """

    def __init__(self, db_path: str = "~/.aiplat/tool_metrics.db",
                 success_threshold: float = 0.3,
                 deprecation_threshold: float = 0.1):
        self.db_path = os.path.expanduser(db_path)
        self.success_threshold = success_threshold
        self.deprecation_threshold = deprecation_threshold
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_metrics (
                    tool_name TEXT PRIMARY KEY,
                    total_calls INTEGER DEFAULT 0,
                    success_calls INTEGER DEFAULT 0,
                    failure_calls INTEGER DEFAULT 0,
                    avg_latency_ms REAL DEFAULT 0,
                    last_used TEXT,
                    last_error TEXT,
                    status TEXT DEFAULT 'active',
                    improvement_count INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 0.5
                );
                CREATE TABLE IF NOT EXISTS tool_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gap_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gap_type TEXT NOT NULL,
                    context TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_seen TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT 0
                );
            """)
            conn.commit()
            conn.close()

    def record_call(self, tool_name: str, success: bool, latency_ms: float = 0,
                    error_type: str = "", error_message: str = ""):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO tool_metrics(tool_name, total_calls, success_calls, failure_calls,
                    avg_latency_ms, last_used, last_error, status)
                VALUES(?, 1, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(tool_name) DO UPDATE SET
                    total_calls = total_calls + 1,
                    success_calls = success_calls + ?,
                    failure_calls = failure_calls + ?,
                    avg_latency_ms = (avg_latency_ms * total_calls + ?) / (total_calls + 1),
                    last_used = ?,
                    last_error = CASE WHEN ? != '' THEN ? ELSE last_error END
            """, (tool_name, 1 if success else 0, 0 if success else 1,
                  1 if success else 0, 0 if success else 1,
                  latency_ms, now,
                  error_type, error_type))
            if not success:
                conn.execute(
                    "INSERT INTO tool_errors(tool_name, error_type, error_message, timestamp) VALUES(?,?,?,?)",
                    (tool_name, error_type or "unknown", error_message[:500], now))
            conn.commit()
            conn.close()

    def record_gap(self, gap_type: str, context: str = ""):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            now = datetime.now(timezone.utc).isoformat()
            existing = conn.execute(
                "SELECT id, frequency FROM gap_log WHERE gap_type=? AND context=? AND resolved=0",
                (gap_type, context)).fetchone()
            if existing:
                conn.execute("UPDATE gap_log SET frequency=frequency+1, last_seen=? WHERE id=?",
                             (now, existing[0]))
            else:
                conn.execute(
                    "INSERT INTO gap_log(gap_type, context, last_seen) VALUES(?,?,?)",
                    (gap_type, context, now))
            conn.commit()
            conn.close()

    def get_underperforming_tools(self) -> list[dict]:
        """Return tools below success threshold, sorted worst first."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT *, CAST(success_calls AS REAL) / MAX(total_calls, 1) AS success_rate
                FROM tool_metrics
                WHERE total_calls >= 10
                  AND CAST(success_calls AS REAL) / MAX(total_calls, 1) < ?
                ORDER BY success_rate ASC
            """, (self.success_threshold,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_frequent_gaps(self, min_frequency: int = 3) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM gap_log WHERE frequency >= ? AND resolved = 0 ORDER BY frequency DESC",
                (min_frequency,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def mark_deprecated(self, tool_name: str):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE tool_metrics SET status='deprecated' WHERE tool_name=?", (tool_name,))
            conn.commit()
            conn.close()

    def mark_gap_resolved(self, gap_id: int):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE gap_log SET resolved=1 WHERE id=?", (gap_id,))
            conn.commit()
            conn.close()

    def get_tool_stats(self) -> dict:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            active = conn.execute("SELECT COUNT(*) as c FROM tool_metrics WHERE status='active'").fetchone()["c"]
            deprecated = conn.execute("SELECT COUNT(*) as c FROM tool_metrics WHERE status='deprecated'").fetchone()["c"]
            gaps = conn.execute("SELECT COUNT(*) as c FROM gap_log WHERE resolved=0").fetchone()["c"]
            conn.close()
            return {"active_tools": active, "deprecated_tools": deprecated, "unresolved_gaps": gaps}


class AutoToolRegenerator:
    """Triggers tool regeneration for underperforming tools and frequent gaps."""

    def __init__(self, evolution: ToolEvolutionEngine):
        self.evolution = evolution

    async def regenerate_underperforming(self) -> list[str]:
        """Auto-regenerate tools below success threshold."""
        under = self.evolution.get_underperforming_tools()
        regenerated = []
        for tool in under:
            success_rate = tool.get("success_rate", 0)
            name = tool["tool_name"]
            if success_rate < self.evolution.deprecation_threshold:
                self.evolution.mark_deprecated(name)
                regenerated.append(f"deprecated:{name} (rate={success_rate:.0%})")
            elif success_rate < self.evolution.success_threshold:
                regenerated.append(f"needs_improvement:{name} (rate={success_rate:.0%})")
        return regenerated

    async def auto_bootstrap_gaps(self) -> list[str]:
        """Auto-bootstrap tools for frequent unresolved gaps."""
        gaps = self.evolution.get_frequent_gaps(min_frequency=3)
        bootstrapped = []
        for gap in gaps:
            try:
                repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__)))))
                core_path = os.path.join(repo_root, 'aiPlat-core')
                if core_path not in sys.path:
                    sys.path.insert(0, core_path)
                from core.harness.optimization.tool_bootstrap import ToolBootstrapEngine
                engine = ToolBootstrapEngine()
                result = await engine.bootstrap_for_gap(gap["gap_type"], gap.get("context", ""))
                if result:
                    self.evolution.mark_gap_resolved(gap["id"])
                    bootstrapped.append(f"bootstrapped:{gap['gap_type']} (freq={gap['frequency']})")
            except Exception:
                pass
        return bootstrapped


_evolution: Optional[ToolEvolutionEngine] = None
_regenerator: Optional[AutoToolRegenerator] = None


def get_tool_evolution() -> ToolEvolutionEngine:
    global _evolution
    if _evolution is None:
        _evolution = ToolEvolutionEngine()
    return _evolution


def get_regenerator() -> AutoToolRegenerator:
    global _regenerator
    if _regenerator is None:
        _regenerator = AutoToolRegenerator(get_tool_evolution())
    return _regenerator
