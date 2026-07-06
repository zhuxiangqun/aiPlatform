"""Kanban engine + Cron scheduler — A2-axis L3→L4 enabler.

SQLite-backed task board with state machine, dependency chains,
and configurable timed scheduling.
"""
import asyncio, json, os, sqlite3, threading, time, uuid
from datetime import datetime, timezone
from typing import Optional


class KanbanEngine:
    """SQLite-backed kanban task board.

    State machine: pending → todo → running → blocked → done → archived

    Features:
    - Task dependency chains (depends_on: list of task_ids)
    - Profile-level isolation (profile_id column)
    - Auto-transition upstream tasks when all deps are done
    - Connector hooks for external execution systems
    """

    def __init__(self, db_path: str = "~/.aiplat/kanban.db"):
        self.db_path = os.path.expanduser(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER DEFAULT 5,
                    depends_on TEXT DEFAULT '[]',
                    scheduled_at TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    reason TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_profile ON tasks(profile_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(profile_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_log_task ON task_log(task_id)")
            conn.commit()
            conn.close()

    def create_task(self, profile_id: str, title: str, description: str = "",
                    depends_on: list[str] | None = None, priority: int = 5,
                    scheduled_at: str | None = None, metadata: dict | None = None) -> str:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO tasks(task_id, profile_id, title, description, status, priority, "
                "depends_on, scheduled_at, created_at, metadata) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id, profile_id, title, description, "pending", priority,
                 json.dumps(depends_on or []), scheduled_at, now, json.dumps(metadata or {})))
            conn.execute(
                "INSERT INTO task_log(task_id, to_status, timestamp, reason) VALUES(?,?,?,?)",
                (task_id, "pending", now, "task_created"))
            conn.commit()
            conn.close()
        return task_id

    def transition_task(self, task_id: str, to_status: str, reason: str = "") -> bool:
        valid_transitions = {
            "pending": ["todo"],
            "todo": ["running", "archived"],
            "running": ["done", "blocked", "archived"],
            "blocked": ["todo", "running", "archived"],
            "done": ["archived"],
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                conn.close()
                return False
            current = row[0]
            allowed = valid_transitions.get(current, [])
            if to_status not in allowed:
                conn.close()
                return False

            updates = ["status=?"]
            params: list = [to_status]
            if to_status == "running" and current != "running":
                updates.append("started_at=?")
                params.append(now)
            if to_status in ("done", "archived"):
                updates.append("finished_at=?")
                params.append(now)
            params.append(task_id)

            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id=?",
                tuple(params))
            conn.execute(
                "INSERT INTO task_log(task_id, from_status, to_status, timestamp, reason) VALUES(?,?,?,?,?)",
                (task_id, current, to_status, now, reason))
            conn.commit()
            conn.close()

        # Check if this unblocks dependents
        if to_status == "done":
            self._unblock_dependents(task_id)
        return True

    def _unblock_dependents(self, completed_task_id: str):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            all_tasks = conn.execute(
                "SELECT task_id, depends_on, status FROM tasks WHERE profile_id IN "
                "(SELECT profile_id FROM tasks WHERE task_id=?)",
                (completed_task_id,)).fetchall()
            for row in all_tasks:
                tid = row["task_id"]
                deps = json.loads(row["depends_on"] or "[]")
                status = row["status"]
                if completed_task_id in deps and status == "pending":
                    all_done = True
                    for dep in deps:
                        r = conn.execute("SELECT status FROM tasks WHERE task_id=?", (dep,)).fetchone()
                        if not r or r["status"] != "done":
                            all_done = False
                            break
                    if all_done:
                        now = datetime.now(timezone.utc).isoformat()
                        conn.execute("UPDATE tasks SET status='todo' WHERE task_id=?", (tid,))
                        conn.execute(
                            "INSERT INTO task_log(task_id, from_status, to_status, timestamp, reason) VALUES(?,?,?,?,?)",
                            (tid, "pending", "todo", now, "all_deps_completed"))
            conn.commit()
            conn.close()

    def list_tasks(self, profile_id: str, status: str | None = None) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM tasks WHERE profile_id=?"
            params = [profile_id]
            if status:
                query += " AND status=?"
                params.append(status)
            query += " ORDER BY priority DESC, created_at ASC"
            rows = conn.execute(query, tuple(params)).fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def get_due_scheduled_tasks(self, profile_id: str) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tasks WHERE profile_id=? AND status='pending' "
                "AND scheduled_at IS NOT NULL AND scheduled_at <= ?",
                (profile_id, now)).fetchall()
            conn.close()
            return [dict(row) for row in rows]


class CronScheduler:
    """Cron-like timed scheduler for KanbanEngine tasks.

    Polls at configurable intervals, transitions due tasks from pending→todo,
    and can trigger external execution via hook.
    """

    def __init__(self, kanban: KanbanEngine, poll_interval: int = 60):
        self.kanban = kanban
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._exec_hook = None

    def set_exec_hook(self, hook):
        """Set async callback: hook(kanban, task_dict) -> None"""
        self._exec_hook = hook

    async def start(self):
        self._running = True
        while self._running:
            try:
                for task in self.kanban.get_due_scheduled_tasks("default"):
                    self.kanban.transition_task(task["task_id"], "todo", "scheduler_due")
                for task in self.kanban.list_tasks("default", "todo"):
                    self.kanban.transition_task(task["task_id"], "running", "scheduler_dispatch")
                    if self._exec_hook:
                        try:
                            await self._exec_hook(self.kanban, task)
                        except Exception:
                            self.kanban.transition_task(task["task_id"], "blocked", "exec_hook_failed")
            except Exception:
                pass
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False


# Singleton
_kanban: Optional[KanbanEngine] = None
_scheduler: Optional[CronScheduler] = None


def get_kanban() -> KanbanEngine:
    global _kanban
    if _kanban is None:
        _kanban = KanbanEngine()
    return _kanban


async def get_scheduler(poll_interval: int = 60) -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        kb = get_kanban()
        _scheduler = CronScheduler(kb, poll_interval)
    return _scheduler
