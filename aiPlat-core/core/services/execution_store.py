"""
ExecutionStore (SQLite)

用于持久化 agent/skill 的执行记录与历史查询。

目标（P0 最小可用）：
- 替代 core/server.py 的全局内存 dict（_agent_executions/_agent_history/_skill_executions）
- 服务重启后仍可查询 execution_id 与 history
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import sqlite3
import time
import uuid
import anyio


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


@dataclass(frozen=True)
class ExecutionStoreConfig:
    db_path: str
    retention_days: Optional[int] = None
    max_rows_per_entity: Optional[int] = None
    prune_on_start: bool = True
    vacuum_on_prune: bool = False


class ExecutionStore:
    CURRENT_SCHEMA_VERSION = 27

    def __init__(self, config: ExecutionStoreConfig):
        self._config = config
        self._init_once_lock = anyio.Lock()
        self._inited = False

    async def init(self) -> None:
        """Init database and run schema migrations (idempotent)."""
        async with self._init_once_lock:
            if self._inited:
                return

            db_path = self._config.db_path
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

            def _init_sync():
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA foreign_keys=ON;")

                    # Meta tables for schema versioning
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS aiplat_meta (
                          k TEXT PRIMARY KEY,
                          v TEXT NOT NULL
                        );
                        """
                    )
                    try:
                        conn.execute(
                            """
                            DELETE FROM syscall_events
                            WHERE id IN (
                              SELECT id FROM syscall_events
                              ORDER BY created_at DESC
                              LIMIT -1 OFFSET ?
                            );
                            """,
                            (int(max_rows),),
                        )
                    except Exception:
                        pass
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                          version INTEGER PRIMARY KEY,
                          applied_at REAL NOT NULL
                        );
                        """
                    )

                    cur = conn.execute("SELECT v FROM aiplat_meta WHERE k='schema_version'").fetchone()
                    current = int(cur[0]) if cur else 0

                    def _set_version(ver: int) -> None:
                        conn.execute(
                            "INSERT INTO aiplat_meta(k,v) VALUES('schema_version', ?) "
                            "ON CONFLICT(k) DO UPDATE SET v=excluded.v;",
                            (str(ver),),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?);",
                            (ver, time.time()),
                        )

                    # ---- Migration v1: executions tables ----
                    if current < 1:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS agent_executions (
                              id TEXT PRIMARY KEY,
                              agent_id TEXT NOT NULL,
                              status TEXT NOT NULL,
                              input_json TEXT,
                              output_json TEXT,
                              error TEXT,
                              start_time REAL,
                              end_time REAL,
                              duration_ms INTEGER,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_agent_exec_agent_id_time ON agent_executions(agent_id, start_time DESC);"
                        )

                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS skill_executions (
                              id TEXT PRIMARY KEY,
                              skill_id TEXT NOT NULL,
                              status TEXT NOT NULL,
                              input_json TEXT,
                              output_json TEXT,
                              error TEXT,
                              start_time REAL,
                              end_time REAL,
                              duration_ms INTEGER,
                              user_id TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_skill_exec_skill_id_time ON skill_executions(skill_id, start_time DESC);"
                        )
                        _set_version(1)
                        current = 1

                    # ---- Migration v2: graph runs + checkpoints ----
                    if current < 2:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS graph_runs (
                              run_id TEXT PRIMARY KEY,
                              graph_name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              trace_id TEXT,
                              initial_state_json TEXT,
                              final_state_json TEXT,
                              summary_json TEXT
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_runs_name_time ON graph_runs(graph_name, start_time DESC);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS graph_checkpoints (
                              checkpoint_id TEXT PRIMARY KEY,
                              run_id TEXT NOT NULL,
                              step INTEGER NOT NULL,
                              state_json TEXT NOT NULL,
                              created_at REAL NOT NULL,
                              FOREIGN KEY(run_id) REFERENCES graph_runs(run_id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_ckpt_run_step ON graph_checkpoints(run_id, step);"
                        )
                        _set_version(2)
                        current = 2

                    # ---- Migration v3: traces + spans ----
                    if current < 3:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS traces (
                              trace_id TEXT PRIMARY KEY,
                              name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              attributes_json TEXT
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_traces_time ON traces(start_time DESC);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS spans (
                              span_id TEXT PRIMARY KEY,
                              trace_id TEXT NOT NULL,
                              parent_span_id TEXT,
                              name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              attributes_json TEXT,
                              events_json TEXT,
                              FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);"
                        )
                        _set_version(3)
                        current = 3

                    # ---- Migration v4: resume links + execution<->trace link ----
                    if current < 4:
                        # graph_runs: resume lineage
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN parent_run_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN resumed_from_checkpoint_id TEXT;")
                        except Exception:
                            pass
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_runs_parent ON graph_runs(parent_run_id);"
                        )

                        # executions: trace link
                        try:
                            conn.execute("ALTER TABLE agent_executions ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE skill_executions ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_agent_exec_trace_id ON agent_executions(trace_id);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_skill_exec_trace_id ON skill_executions(trace_id);"
                        )

                        _set_version(4)
                        current = 4

                    # ---- Migration v5: graph_runs trace_id index ----
                    if current < 5:
                        # Some DBs were created before trace_id column existed.
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_runs_trace ON graph_runs(trace_id);")
                        _set_version(5)
                        current = 5

                    # ---- Migration v6: syscall events audit table ----
                    if current < 6:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS syscall_events (
                              id TEXT PRIMARY KEY,
                              trace_id TEXT,
                              run_id TEXT,
                              kind TEXT NOT NULL,          -- llm|tool|skill
                              name TEXT NOT NULL,          -- tool name / skill name / llm operation name
                              status TEXT NOT NULL,        -- success|failed
                              start_time REAL,
                              end_time REAL,
                              duration_ms REAL,
                              args_json TEXT,
                              result_json TEXT,
                              error TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_syscall_events_trace ON syscall_events(trace_id, start_time DESC);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_syscall_events_run ON syscall_events(run_id, start_time DESC);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_syscall_events_kind ON syscall_events(kind, start_time DESC);"
                        )
                        _set_version(6)
                        current = 6

                    # ---- Migration v7: agent_executions metadata_json ----
                    if current < 7:
                        try:
                            conn.execute("ALTER TABLE agent_executions ADD COLUMN metadata_json TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE skill_executions ADD COLUMN metadata_json TEXT;")
                        except Exception:
                            pass
                        _set_version(7)
                        current = 7

                    # ---- Migration v8: approval requests persistence ----
                    if current < 8:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS approval_requests (
                              request_id TEXT PRIMARY KEY,
                              user_id TEXT NOT NULL,
                              operation TEXT NOT NULL,
                              details TEXT,
                              rule_id TEXT,
                              rule_type TEXT,
                              status TEXT NOT NULL,
                              amount REAL,
                              batch_size INTEGER,
                              is_first_time INTEGER,
                              created_at REAL NOT NULL,
                              updated_at REAL NOT NULL,
                              expires_at REAL,
                              metadata_json TEXT,
                              result_json TEXT
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_status_time ON approval_requests(status, created_at DESC);")
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_user_time ON approval_requests(user_id, created_at DESC);")
                        _set_version(8)
                        current = 8

                    # ---- Migration v9: approval_request_id linkage columns ----
                    if current < 9:
                        # agent_executions
                        try:
                            conn.execute("ALTER TABLE agent_executions ADD COLUMN approval_request_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_agent_exec_approval_id ON agent_executions(approval_request_id);"
                            )
                        except Exception:
                            pass

                        # syscall_events
                        try:
                            conn.execute("ALTER TABLE syscall_events ADD COLUMN approval_request_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_syscall_events_approval_id ON syscall_events(approval_request_id);"
                            )
                        except Exception:
                            pass

                        _set_version(9)
                        current = 9

                    # ---- Migration v10: syscall_events span_id linkage ----
                    if current < 10:
                        try:
                            conn.execute("ALTER TABLE syscall_events ADD COLUMN span_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_syscall_events_span_id ON syscall_events(span_id);")
                        except Exception:
                            pass
                        _set_version(10)
                        current = 10

                    # ---- Migration v11: learning_artifacts (Phase 6 placeholder) ----
                    if current < 11:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS learning_artifacts (
                              artifact_id TEXT PRIMARY KEY,
                              kind TEXT NOT NULL,
                              target_type TEXT NOT NULL,
                              target_id TEXT NOT NULL,
                              version TEXT NOT NULL,
                              status TEXT NOT NULL,
                              trace_id TEXT,
                              run_id TEXT,
                              payload_json TEXT,
                              metadata_json TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_learning_artifacts_target ON learning_artifacts(target_type, target_id, created_at DESC);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_learning_artifacts_trace ON learning_artifacts(trace_id, created_at DESC);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_learning_artifacts_run ON learning_artifacts(run_id, created_at DESC);"
                        )
                        _set_version(11)
                        current = 11

                    # ---- Migration v12: jobs + job_runs (Roadmap-3: Jobs/Cron) ----
                    if current < 12:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS jobs (
                              id TEXT PRIMARY KEY,
                              name TEXT NOT NULL,
                              enabled INTEGER NOT NULL,
                              cron TEXT NOT NULL,
                              timezone TEXT,
                              kind TEXT NOT NULL,           -- agent|skill|tool|graph
                              target_id TEXT NOT NULL,
                              user_id TEXT,
                              session_id TEXT,
                              payload_json TEXT,
                              options_json TEXT,
                              delivery_json TEXT,
                              last_run_at REAL,
                              next_run_at REAL,
                              created_at REAL NOT NULL,
                              updated_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON jobs(enabled, next_run_at);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_jobs_kind_target ON jobs(kind, target_id);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS job_runs (
                              id TEXT PRIMARY KEY,
                              job_id TEXT NOT NULL,
                              scheduled_for REAL,
                              started_at REAL,
                              finished_at REAL,
                              status TEXT NOT NULL,          -- running|completed|failed|cancelled
                              trace_id TEXT,
                              run_id TEXT,
                              error TEXT,
                              result_json TEXT,
                              created_at REAL NOT NULL,
                              FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_job_runs_job_time ON job_runs(job_id, created_at DESC);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_job_runs_trace ON job_runs(trace_id, created_at DESC);"
                        )
                        _set_version(12)
                        current = 12

                    # ---- Migration v13: jobs locking fields (Roadmap-3 hardening) ----
                    if current < 13:
                        # Best-effort columns for leaderless locking.
                        # If multiple schedulers are running, they will contend on (lock_until, lock_owner).
                        try:
                            conn.execute("ALTER TABLE jobs ADD COLUMN lock_until REAL;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE jobs ADD COLUMN lock_owner TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_lock_until ON jobs(lock_until);")
                        except Exception:
                            pass
                        _set_version(13)
                        current = 13

                    # ---- Migration v14: skill_packs + long_term_memories (Roadmap-4 minimal) ----
                    if current < 14:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS skill_packs (
                              id TEXT PRIMARY KEY,
                              name TEXT NOT NULL,
                              description TEXT,
                              manifest_json TEXT,
                              created_at REAL NOT NULL,
                              updated_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_packs_name ON skill_packs(name);")

                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS long_term_memories (
                              id TEXT PRIMARY KEY,
                              user_id TEXT NOT NULL,
                              key TEXT,
                              content TEXT NOT NULL,
                              metadata_json TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_ltm_user_time ON long_term_memories(user_id, created_at DESC);")
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_ltm_key ON long_term_memories(key);")

                        _set_version(14)
                        current = 14

                    # ---- Migration v15: long_term_memories FTS (Roadmap-4 hardening) ----
                    if current < 15:
                        # Optional FTS index for faster search. Best-effort: if SQLite lacks fts5, ignore.
                        try:
                            conn.execute(
                                """
                                CREATE VIRTUAL TABLE IF NOT EXISTS long_term_memories_fts
                                USING fts5(
                                  id UNINDEXED,
                                  user_id UNINDEXED,
                                  key,
                                  content
                                );
                                """
                            )
                        except Exception:
                            pass
                        _set_version(15)
                        current = 15

                    # ---- Migration v16: skill_pack_versions + installs (Roadmap-4 minimal release/install) ----
                    if current < 16:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS skill_pack_versions (
                              id TEXT PRIMARY KEY,
                              pack_id TEXT NOT NULL,
                              version TEXT NOT NULL,
                              manifest_json TEXT,
                              created_at REAL NOT NULL,
                              UNIQUE(pack_id, version),
                              FOREIGN KEY(pack_id) REFERENCES skill_packs(id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_spv_pack_time ON skill_pack_versions(pack_id, created_at DESC);")
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS skill_pack_installs (
                              id TEXT PRIMARY KEY,
                              pack_id TEXT NOT NULL,
                              version TEXT,
                              scope TEXT NOT NULL,      -- engine|workspace
                              installed_at REAL NOT NULL,
                              metadata_json TEXT,
                              FOREIGN KEY(pack_id) REFERENCES skill_packs(id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_spi_scope_time ON skill_pack_installs(scope, installed_at DESC);")
                        _set_version(16)
                        current = 16

                    # ---- Migration v17: error_code columns for executions (Roadmap-0 hardening) ----
                    if current < 17:
                        try:
                            conn.execute("ALTER TABLE agent_executions ADD COLUMN error_code TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE skill_executions ADD COLUMN error_code TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_exec_error_code ON agent_executions(error_code);")
                        except Exception:
                            pass
                        try:
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_exec_error_code ON skill_executions(error_code);")
                        except Exception:
                            pass
                        _set_version(17)
                        current = 17

                    # ---- Migration v18: persistent session memory + FTS (Roadmap-4 session search) ----
                    if current < 18:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS memory_sessions (
                              id TEXT PRIMARY KEY,
                              user_id TEXT NOT NULL,
                              agent_type TEXT,
                              session_type TEXT,
                              status TEXT,
                              metadata_json TEXT,
                              message_count INTEGER NOT NULL DEFAULT 0,
                              created_at REAL NOT NULL,
                              updated_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_sess_user_time ON memory_sessions(user_id, updated_at DESC);")
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS memory_messages (
                              id TEXT PRIMARY KEY,
                              session_id TEXT NOT NULL,
                              user_id TEXT NOT NULL,
                              role TEXT NOT NULL,
                              content TEXT NOT NULL,
                              metadata_json TEXT,
                              trace_id TEXT,
                              run_id TEXT,
                              created_at REAL NOT NULL,
                              FOREIGN KEY(session_id) REFERENCES memory_sessions(id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_msg_session_time ON memory_messages(session_id, created_at DESC);")
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_msg_user_time ON memory_messages(user_id, created_at DESC);")
                        # Best-effort FTS: not all sqlite builds support fts5.
                        try:
                            conn.execute(
                                """
                                CREATE VIRTUAL TABLE IF NOT EXISTS memory_messages_fts
                                USING fts5(
                                  id UNINDEXED,
                                  user_id UNINDEXED,
                                  session_id UNINDEXED,
                                  role UNINDEXED,
                                  content
                                );
                                """
                            )
                        except Exception:
                            pass
                        _set_version(18)
                        current = 18

                    # ---- Migration v19: job delivery attempts + DLQ (Roadmap-3 hardening) ----
                    if current < 19:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS job_delivery_attempts (
                              id TEXT PRIMARY KEY,
                              job_id TEXT NOT NULL,
                              run_id TEXT,
                              attempt INTEGER NOT NULL,
                              url TEXT,
                              status TEXT NOT NULL,        -- success|failed
                              response_status INTEGER,
                              error TEXT,
                              payload_json TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_jda_job_time ON job_delivery_attempts(job_id, created_at DESC);")
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_jda_run_time ON job_delivery_attempts(run_id, created_at DESC);")

                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS job_delivery_dlq (
                              id TEXT PRIMARY KEY,
                              job_id TEXT NOT NULL,
                              run_id TEXT,
                              url TEXT,
                              delivery_json TEXT,
                              payload_json TEXT,
                              attempts INTEGER NOT NULL,
                              error TEXT,
                              status TEXT NOT NULL,        -- pending|resolved
                              created_at REAL NOT NULL,
                              resolved_at REAL
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_jdlq_status_time ON job_delivery_dlq(status, created_at DESC);")
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_jdlq_job_time ON job_delivery_dlq(job_id, created_at DESC);")
                        _set_version(19)
                        current = 19

                    # ---- Migration v20: gateway pairings + tokens (Roadmap-3/4 channels) ----
                    if current < 20:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS gateway_pairings (
                              id TEXT PRIMARY KEY,
                              channel TEXT NOT NULL,
                              channel_user_id TEXT NOT NULL,
                              user_id TEXT NOT NULL,
                              session_id TEXT,
                              tenant_id TEXT,
                              metadata_json TEXT,
                              created_at REAL NOT NULL,
                              updated_at REAL NOT NULL,
                              UNIQUE(channel, channel_user_id)
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_gw_pair_channel_user ON gateway_pairings(channel, channel_user_id);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS gateway_tokens (
                              id TEXT PRIMARY KEY,
                              name TEXT NOT NULL,
                              token_sha256 TEXT NOT NULL,
                              tenant_id TEXT,
                              enabled INTEGER NOT NULL,
                              created_at REAL NOT NULL,
                              metadata_json TEXT
                            );
                            """
                        )
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_gw_tokens_enabled ON gateway_tokens(enabled, created_at DESC);")
                        _set_version(20)
                        current = 20

                    # ---- Migration v21: syscall_events dimensions (Roadmap-0/Roadmap-2) ----
                    if current < 21:
                        # Extend syscall_events for better aggregation/search:
                        # - error_code: normalized machine code
                        # - target_type/target_id: link to agent/skill/tool when known
                        # - user_id/session_id: link to identity (best-effort)
                        for stmt in [
                            "ALTER TABLE syscall_events ADD COLUMN error_code TEXT;",
                            "ALTER TABLE syscall_events ADD COLUMN target_type TEXT;",
                            "ALTER TABLE syscall_events ADD COLUMN target_id TEXT;",
                            "ALTER TABLE syscall_events ADD COLUMN user_id TEXT;",
                            "ALTER TABLE syscall_events ADD COLUMN session_id TEXT;",
                        ]:
                            try:
                                conn.execute(stmt)
                            except Exception:
                                pass
                        try:
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_syscall_events_error_code ON syscall_events(error_code, created_at DESC);"
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_syscall_events_target ON syscall_events(target_type, target_id, created_at DESC);"
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_syscall_events_user_sess ON syscall_events(user_id, session_id, created_at DESC);"
                            )
                        except Exception:
                            pass
                        _set_version(21)
                        current = 21

                    # ---- Migration v22: run_events + request_dedup (platform execution contract) ----
                    if current < 22:
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS run_events (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                  run_id TEXT NOT NULL,
                                  seq INTEGER NOT NULL,
                                  tenant_id TEXT,
                                  trace_id TEXT,
                                  type TEXT NOT NULL,
                                  payload_json TEXT,
                                  created_at REAL NOT NULL,
                                  UNIQUE(run_id, seq)
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_events_run_seq ON run_events(run_id, seq);")
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_run_events_time ON run_events(created_at DESC);"
                            )
                        except Exception:
                            pass
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS request_dedup (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                  tenant_id TEXT,
                                  request_id TEXT NOT NULL,
                                  run_id TEXT NOT NULL,
                                  created_at REAL NOT NULL,
                                  UNIQUE(tenant_id, request_id)
                                );
                                """
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_request_dedup_request ON request_dedup(request_id, created_at DESC);"
                            )
                        except Exception:
                            pass
                        _set_version(22)
                        current = 22

                    # ---- Migration v23: audit_logs (enterprise governance) ----
                    if current < 23:
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS audit_logs (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                  tenant_id TEXT,
                                  actor_id TEXT,
                                  actor_role TEXT,
                                  action TEXT NOT NULL,
                                  resource_type TEXT,
                                  resource_id TEXT,
                                  request_id TEXT,
                                  run_id TEXT,
                                  trace_id TEXT,
                                  status TEXT,
                                  detail_json TEXT,
                                  created_at REAL NOT NULL
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs(created_at DESC);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_time ON audit_logs(tenant_id, created_at DESC);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time ON audit_logs(action, created_at DESC);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_time ON audit_logs(actor_id, created_at DESC);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_run ON audit_logs(run_id, created_at DESC);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_request ON audit_logs(request_id, created_at DESC);")
                        except Exception:
                            pass
                        _set_version(23)
                        current = 23

                    # ---- Migration v24: tenant_policies (policy-as-code) ----
                    if current < 24:
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS tenant_policies (
                                  tenant_id TEXT PRIMARY KEY,
                                  version INTEGER NOT NULL,
                                  policy_json TEXT NOT NULL,
                                  updated_at REAL NOT NULL
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_policies_updated ON tenant_policies(updated_at DESC);")
                        except Exception:
                            pass
                        _set_version(24)
                        current = 24

                    # ---- Migration v25: packages registry (publish/install) ----
                    if current < 25:
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS package_versions (
                                  id TEXT PRIMARY KEY,
                                  package_name TEXT NOT NULL,
                                  version TEXT NOT NULL,
                                  manifest_json TEXT,
                                  artifact_path TEXT,
                                  artifact_sha256 TEXT,
                                  approval_request_id TEXT,
                                  created_at REAL NOT NULL,
                                  UNIQUE(package_name, version)
                                );
                                """
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_pkg_versions_name_time ON package_versions(package_name, created_at DESC);"
                            )
                        except Exception:
                            pass
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS package_installs (
                                  id TEXT PRIMARY KEY,
                                  package_name TEXT NOT NULL,
                                  version TEXT,
                                  scope TEXT NOT NULL,      -- engine|workspace
                                  installed_at REAL NOT NULL,
                                  metadata_json TEXT,
                                  approval_request_id TEXT
                                );
                                """
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_pkg_installs_scope_time ON package_installs(scope, installed_at DESC);"
                            )
                            conn.execute(
                                "CREATE INDEX IF NOT EXISTS idx_pkg_installs_name_time ON package_installs(package_name, installed_at DESC);"
                            )
                        except Exception:
                            pass
                        _set_version(25)
                        current = 25

                    # ---- Migration v26: adapters registry (persist LLM adapter configs) ----
                    if current < 26:
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS adapters (
                                  adapter_id TEXT PRIMARY KEY,
                                  name TEXT NOT NULL,
                                  provider TEXT NOT NULL,
                                  description TEXT,
                                  status TEXT NOT NULL,
                                  api_key TEXT,
                                  api_base_url TEXT,
                                  organization_id TEXT,
                                  models_json TEXT,
                                  rate_limit_json TEXT,
                                  retry_config_json TEXT,
                                  metadata_json TEXT,
                                  created_at REAL NOT NULL,
                                  updated_at REAL NOT NULL
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_adapters_provider ON adapters(provider);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_adapters_status ON adapters(status);")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_adapters_updated ON adapters(updated_at DESC);")
                        except Exception:
                            pass
                        _set_version(26)
                        current = 26

                    # ---- Migration v27: global_settings + tenants + encrypted adapter secrets ----
                    if current < 27:
                        # global settings (e.g., default llm routing)
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS global_settings (
                                  key TEXT PRIMARY KEY,
                                  value_json TEXT NOT NULL,
                                  updated_at REAL NOT NULL
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_global_settings_updated ON global_settings(updated_at DESC);")
                        except Exception:
                            pass

                        # tenants (minimal registry; policy-as-code uses tenant_id)
                        try:
                            conn.execute(
                                """
                                CREATE TABLE IF NOT EXISTS tenants (
                                  tenant_id TEXT PRIMARY KEY,
                                  name TEXT,
                                  metadata_json TEXT,
                                  created_at REAL NOT NULL,
                                  updated_at REAL NOT NULL
                                );
                                """
                            )
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_tenants_updated ON tenants(updated_at DESC);")
                        except Exception:
                            pass

                        # encrypted api key columns (keep legacy api_key for backward compatibility)
                        try:
                            conn.execute("ALTER TABLE adapters ADD COLUMN api_key_enc TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE adapters ADD COLUMN api_key_kid TEXT;")
                        except Exception:
                            pass

                        _set_version(27)
                        current = 27

                    # If legacy db exists with tables but without meta, upgrade meta to current
                    if current < self.CURRENT_SCHEMA_VERSION:
                        _set_version(self.CURRENT_SCHEMA_VERSION)

                    # Ensure idempotency indexes exist (even when schema_version already current)
                    try:
                        conn.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_runs_resume_unique "
                            "ON graph_runs(parent_run_id, resumed_from_checkpoint_id) "
                            "WHERE resumed_from_checkpoint_id IS NOT NULL;"
                        )
                    except Exception:
                        pass

                    conn.commit()
                finally:
                    conn.close()

            await anyio.to_thread.run_sync(_init_sync)
            self._inited = True

            # Optional retention pruning on start (best effort)
            if self._config.prune_on_start and (self._config.retention_days or self._config.max_rows_per_entity):
                try:
                    await self.prune()
                except Exception:
                    pass

    async def get_schema_version(self) -> int:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> int:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT v FROM aiplat_meta WHERE k='schema_version'").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_syscall_event_stats(
        self,
        *,
        window_hours: int = 24,
        top_n: int = 10,
        kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Roadmap-0/2/3 observability: basic aggregated syscall stats (best-effort).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                now = time.time()
                since = now - float(max(int(window_hours), 1)) * 3600.0
                where = "WHERE created_at >= ?"
                params: List[Any] = [since]
                if kind:
                    where += " AND kind = ?"
                    params.append(str(kind))

                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM syscall_events {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)

                by_kind = {
                    r["kind"]: int(r["c"])
                    for r in conn.execute(
                        f"SELECT kind, COUNT(1) AS c FROM syscall_events {where} GROUP BY kind;", params
                    ).fetchall()
                }
                by_status = {
                    r["status"]: int(r["c"])
                    for r in conn.execute(
                        f"SELECT status, COUNT(1) AS c FROM syscall_events {where} GROUP BY status;", params
                    ).fetchall()
                }

                top_names = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT kind, name, COUNT(1) AS count, AVG(duration_ms) AS avg_ms
                        FROM syscall_events
                        {where}
                        GROUP BY kind, name
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]
                top_failed = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT kind, name, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND status = 'failed'
                        GROUP BY kind, name
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]

                top_error_codes = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT error_code, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND error_code IS NOT NULL AND error_code != ''
                        GROUP BY error_code
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]
                top_failed_error_codes = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT error_code, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND status = 'failed' AND error_code IS NOT NULL AND error_code != ''
                        GROUP BY error_code
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]

                # Last N hours failure trend (hourly buckets).
                trend = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT
                          strftime('%Y-%m-%d %H:00:00', datetime(created_at, 'unixepoch')) AS bucket,
                          COUNT(1) AS failed
                        FROM syscall_events
                        {where} AND status = 'failed'
                        GROUP BY bucket
                        ORDER BY bucket ASC;
                        """,
                        params,
                    ).fetchall()
                ]

                return {
                    "window_hours": int(window_hours),
                    "since": since,
                    "total": total,
                    "by_kind": by_kind,
                    "by_status": by_status,
                    "top_names": top_names,
                    "top_failed": top_failed,
                    "top_error_codes": top_error_codes,
                    "top_failed_error_codes": top_failed_error_codes,
                    "failed_trend_hourly": trend,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def prune(self, now_ts: Optional[float] = None) -> Dict[str, int]:
        """
        清理历史数据（best-effort）。

        - retention_days：按 created_at/start_time 做时间删除
        - max_rows_per_entity：按 start_time/created_at 限制最大行数（每个 agent_id/skill_id/graph_name 维度）
        """
        await self.init()
        db_path = self._config.db_path
        retention_days = self._config.retention_days
        max_rows = self._config.max_rows_per_entity
        now_ts = float(now_ts or time.time())
        cutoff = now_ts - float(retention_days or 0) * 86400.0

        def _sync() -> Dict[str, int]:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
                deleted = {"agent_executions": 0, "skill_executions": 0, "graph_runs": 0, "graph_checkpoints": 0, "traces": 0, "spans": 0, "syscall_events": 0}

                if retention_days is not None:
                    cur = conn.execute("DELETE FROM agent_executions WHERE created_at < ?", (cutoff,))
                    deleted["agent_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM skill_executions WHERE created_at < ?", (cutoff,))
                    deleted["skill_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM graph_runs WHERE start_time < ?", (cutoff,))
                    deleted["graph_runs"] += cur.rowcount or 0
                    try:
                        cur = conn.execute("DELETE FROM syscall_events WHERE created_at < ?", (cutoff,))
                        deleted["syscall_events"] += cur.rowcount or 0
                    except Exception:
                        pass
                    # graph_checkpoints cascades via FK
                    cur = conn.execute("DELETE FROM traces WHERE start_time < ?", (cutoff,))
                    deleted["traces"] += cur.rowcount or 0
                    # spans cascades via FK

                if max_rows is not None and max_rows > 0:
                    # Keep only last N per agent_id
                    conn.execute(
                        """
                        DELETE FROM agent_executions
                        WHERE id IN (
                          SELECT id FROM (
                            SELECT
                              id,
                              ROW_NUMBER() OVER (PARTITION BY agent_id ORDER BY start_time DESC) AS rn
                            FROM agent_executions
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N per skill_id
                    conn.execute(
                        """
                        DELETE FROM skill_executions
                        WHERE id IN (
                          SELECT id FROM (
                            SELECT
                              id,
                              ROW_NUMBER() OVER (PARTITION BY skill_id ORDER BY start_time DESC) AS rn
                            FROM skill_executions
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N per graph_name (delete runs; cascades checkpoints)
                    conn.execute(
                        """
                        DELETE FROM graph_runs
                        WHERE run_id IN (
                          SELECT run_id FROM (
                            SELECT
                              run_id,
                              ROW_NUMBER() OVER (PARTITION BY graph_name ORDER BY start_time DESC) AS rn
                            FROM graph_runs
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N traces overall (no entity dimension yet)
                    conn.execute(
                        """
                        DELETE FROM traces
                        WHERE trace_id IN (
                          SELECT trace_id FROM (
                            SELECT
                              trace_id,
                              ROW_NUMBER() OVER (ORDER BY start_time DESC) AS rn
                            FROM traces
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )

                conn.commit()
                if self._config.vacuum_on_prune:
                    conn.execute("VACUUM;")
                return deleted
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Graph (trace/checkpoint) ====================

    async def start_graph_run(
        self,
        graph_name: str,
        run_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None,
        parent_run_id: Optional[str] = None,
        resumed_from_checkpoint_id: Optional[str] = None,
    ) -> str:
        await self.init()
        db_path = self._config.db_path
        run_id = run_id or str(uuid.uuid4())
        start_time = float(start_time or time.time())
        initial_state_json = _json_dumps(initial_state or {})
        trace_id = None
        try:
            meta = initial_state.get("metadata") if isinstance((initial_state or {}).get("metadata"), dict) else {}
            trace_id = meta.get("trace_id")
        except Exception:
            trace_id = None

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO graph_runs(run_id, graph_name, status, start_time, trace_id, initial_state_json, parent_run_id, resumed_from_checkpoint_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      graph_name=excluded.graph_name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      trace_id=excluded.trace_id,
                      initial_state_json=excluded.initial_state_json,
                      parent_run_id=excluded.parent_run_id,
                      resumed_from_checkpoint_id=excluded.resumed_from_checkpoint_id;
                    """,
                    (run_id, graph_name, "running", start_time, trace_id, initial_state_json, parent_run_id, resumed_from_checkpoint_id),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return run_id

    async def finish_graph_run(
        self,
        run_id: str,
        status: str = "completed",
        final_state: Optional[Dict[str, Any]] = None,
        summary: Optional[Dict[str, Any]] = None,
        end_time: Optional[float] = None,
    ) -> None:
        await self.init()
        db_path = self._config.db_path
        end_time = float(end_time or time.time())
        final_state_json = _json_dumps(final_state or {})
        summary_json = _json_dumps(summary or {})
        trace_id = None
        try:
            meta = final_state.get("metadata") if isinstance((final_state or {}).get("metadata"), dict) else {}
            trace_id = meta.get("trace_id")
        except Exception:
            trace_id = None

        def _sync():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT start_time FROM graph_runs WHERE run_id=?", (run_id,)).fetchone()
                start_time = float(row["start_time"]) if row else end_time
                duration_ms = (end_time - start_time) * 1000.0
                conn.execute(
                    """
                    UPDATE graph_runs
                    SET status=?, end_time=?, duration_ms=?, final_state_json=?, summary_json=?, trace_id=COALESCE(?, trace_id)
                    WHERE run_id=?;
                    """,
                    (status, end_time, duration_ms, final_state_json, summary_json, trace_id, run_id),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def add_graph_checkpoint(
        self,
        run_id: str,
        step: int,
        state: Dict[str, Any],
        checkpoint_id: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> str:
        await self.init()
        db_path = self._config.db_path
        checkpoint_id = checkpoint_id or str(uuid.uuid4())
        created_at = float(created_at or time.time())
        state_json = _json_dumps(state or {})

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO graph_checkpoints(checkpoint_id, run_id, step, state_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(checkpoint_id) DO UPDATE SET
                      run_id=excluded.run_id,
                      step=excluded.step,
                      state_json=excluded.state_json,
                      created_at=excluded.created_at;
                    """,
                    (checkpoint_id, run_id, int(step), state_json, created_at),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return checkpoint_id

    async def list_graph_checkpoints(self, run_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=?
                    ORDER BY step ASC
                    LIMIT ? OFFSET ?;
                    """,
                    (run_id, int(limit), int(offset)),
                ).fetchall()
                return [
                    {
                        "checkpoint_id": r["checkpoint_id"],
                        "run_id": r["run_id"],
                        "step": r["step"],
                        "state": _json_loads(r["state_json"]),
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_graph_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM graph_runs WHERE run_id=?", (run_id,)).fetchone()
                if not row:
                    return None
                return {
                    "run_id": row["run_id"],
                    "graph_name": row["graph_name"],
                    "status": row["status"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "initial_state": _json_loads(row["initial_state_json"]),
                    "final_state": _json_loads(row["final_state_json"]),
                    "summary": _json_loads(row["summary_json"]),
                    "parent_run_id": row["parent_run_id"] if "parent_run_id" in row.keys() else None,
                    "resumed_from_checkpoint_id": row["resumed_from_checkpoint_id"] if "resumed_from_checkpoint_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_graph_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        graph_name: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List graph_runs with basic filters."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if graph_name:
                    clauses.append("graph_name=?")
                    params.append(graph_name)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM graph_runs {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT run_id, graph_name, status, start_time, end_time, duration_ms, trace_id,
                           parent_run_id, resumed_from_checkpoint_id
                    FROM graph_runs
                    {where_sql}
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()

                items = []
                for r in rows:
                    items.append(
                        {
                            "run_id": r["run_id"],
                            "graph_name": r["graph_name"],
                            "status": r["status"],
                            "start_time": r["start_time"],
                            "end_time": r["end_time"],
                            "duration_ms": r["duration_ms"],
                            "trace_id": r["trace_id"] if "trace_id" in r.keys() else None,
                            "parent_run_id": r["parent_run_id"],
                            "resumed_from_checkpoint_id": r["resumed_from_checkpoint_id"],
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Trace ====================

    async def upsert_trace(self, trace: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            trace.get("trace_id"),
            trace.get("name") or "",
            trace.get("status"),
            float(trace.get("start_time") or time.time()),
            trace.get("end_time"),
            trace.get("duration_ms"),
            _json_dumps(trace.get("attributes") or {}),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO traces(trace_id, name, status, start_time, end_time, duration_ms, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                      name=excluded.name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      attributes_json=excluded.attributes_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def upsert_span(self, span: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            span.get("span_id"),
            span.get("trace_id"),
            span.get("parent_span_id"),
            span.get("name") or "",
            span.get("status"),
            float(span.get("start_time") or time.time()),
            span.get("end_time"),
            span.get("duration_ms"),
            _json_dumps(span.get("attributes") or {}),
            _json_dumps(span.get("events") or []),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO spans(span_id, trace_id, parent_span_id, name, status, start_time, end_time, duration_ms, attributes_json, events_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(span_id) DO UPDATE SET
                      trace_id=excluded.trace_id,
                      parent_span_id=excluded.parent_span_id,
                      name=excluded.name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      attributes_json=excluded.attributes_json,
                      events_json=excluded.events_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_trace(self, trace_id: str, include_spans: bool = True) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
                if not row:
                    return None
                trace = {
                    "trace_id": row["trace_id"],
                    "name": row["name"],
                    "status": row["status"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "attributes": _json_loads(row["attributes_json"]) or {},
                }
                if include_spans:
                    spans = conn.execute(
                        "SELECT * FROM spans WHERE trace_id=? ORDER BY start_time ASC",
                        (trace_id,),
                    ).fetchall()
                    trace["spans"] = [
                        {
                            "span_id": s["span_id"],
                            "trace_id": s["trace_id"],
                            "parent_span_id": s["parent_span_id"],
                            "name": s["name"],
                            "status": s["status"],
                            "start_time": s["start_time"],
                            "end_time": s["end_time"],
                            "duration_ms": s["duration_ms"],
                            "attributes": _json_loads(s["attributes_json"]) or {},
                            "events": _json_loads(s["events_json"]) or [],
                        }
                        for s in spans
                    ]
                return trace
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_traces(self, limit: int = 100, offset: int = 0, status: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                if status:
                    total = conn.execute("SELECT COUNT(1) AS c FROM traces WHERE status=?", (status,)).fetchone()["c"]
                    rows = conn.execute(
                        "SELECT * FROM traces WHERE status=? ORDER BY start_time DESC LIMIT ? OFFSET ?",
                        (status, int(limit), int(offset)),
                    ).fetchall()
                else:
                    total = conn.execute("SELECT COUNT(1) AS c FROM traces").fetchone()["c"]
                    rows = conn.execute(
                        "SELECT * FROM traces ORDER BY start_time DESC LIMIT ? OFFSET ?",
                        (int(limit), int(offset)),
                    ).fetchall()
                items = [
                    {
                        "trace_id": r["trace_id"],
                        "name": r["name"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "attributes": _json_loads(r["attributes_json"]) or {},
                    }
                    for r in rows
                ]
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Graph restore/resume helpers ====================

    async def get_graph_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT checkpoint_id, run_id, step, state_json, created_at FROM graph_checkpoints WHERE checkpoint_id=?",
                    (checkpoint_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_graph_checkpoint_by_step(self, run_id: str, step: int) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=? AND step=?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (run_id, int(step)),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_latest_graph_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=?
                    ORDER BY step DESC, created_at DESC
                    LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def resume_graph_run(
        self,
        parent_run_id: str,
        checkpoint_id: str,
        new_run_id: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        从 checkpoint 创建一个新的 graph_run（用于“可恢复执行”的语义），并返回新 run 的初始 state。
        注意：此方法仅提供“恢复状态+建档”；实际执行由上层组件决定。
        """
        await self.init()
        parent = await self.get_graph_run(parent_run_id)
        ckpt = await self.get_graph_checkpoint(checkpoint_id)
        if not parent or not ckpt:
            return None
        if ckpt["run_id"] != parent_run_id:
            return None

        # Idempotency: if already resumed from this checkpoint, return existing run
        db_path = self._config.db_path

        def _find_existing() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT run_id, graph_name, initial_state_json
                    FROM graph_runs
                    WHERE parent_run_id=? AND resumed_from_checkpoint_id=?
                    ORDER BY start_time DESC
                    LIMIT 1
                    """,
                    (parent_run_id, checkpoint_id),
                ).fetchone()
                if not row:
                    return None
                return {
                    "run_id": row["run_id"],
                    "graph_name": row["graph_name"],
                    "state": _json_loads(row["initial_state_json"]) or {},
                }
            finally:
                conn.close()

        existing = await anyio.to_thread.run_sync(_find_existing)
        if existing:
            return {
                "run_id": existing["run_id"],
                "graph_name": existing["graph_name"],
                "checkpoint_id": checkpoint_id,
                "state": existing["state"],
            }

        restored_state = ckpt.get("state") if isinstance(ckpt.get("state"), dict) else {}
        # Ensure restored state can be correlated to new run id (for callbacks / persistence)
        try:
            meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
            meta["graph_run_id"] = new_run_id or meta.get("graph_run_id")
            meta["parent_run_id"] = parent_run_id
            meta["resumed_from_checkpoint_id"] = checkpoint_id
            restored_state["metadata"] = meta
        except Exception:
            pass
        run_id = await self.start_graph_run(
            graph_name=parent["graph_name"],
            run_id=new_run_id,
            initial_state=restored_state,
            start_time=start_time,
            parent_run_id=parent_run_id,
            resumed_from_checkpoint_id=checkpoint_id,
        )
        # Update graph_run_id to the actual run_id if generated by store
        try:
            meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
            meta["graph_run_id"] = run_id
            restored_state["metadata"] = meta
        except Exception:
            pass
        return {"run_id": run_id, "graph_name": parent["graph_name"], "checkpoint_id": checkpoint_id, "state": restored_state}

    # ==================== execution <-> trace link queries ====================

    async def get_trace_id_by_execution_id(self, execution_id: str) -> Optional[str]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[str]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT trace_id FROM agent_executions WHERE id=?", (execution_id,)).fetchone()
                if row and row["trace_id"]:
                    return row["trace_id"]
                row = conn.execute("SELECT trace_id FROM skill_executions WHERE id=?", (execution_id,)).fetchone()
                if row and row["trace_id"]:
                    return row["trace_id"]
                return None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_executions_by_trace_id(self, trace_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                agent_rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE trace_id=?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (trace_id, int(limit), int(offset)),
                ).fetchall()
                skill_rows = conn.execute(
                    """
                    SELECT * FROM skill_executions
                    WHERE trace_id=?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (trace_id, int(limit), int(offset)),
                ).fetchall()

                agents = [
                    {
                        "execution_id": r["id"],
                        "agent_id": r["agent_id"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "trace_id": r["trace_id"],
                        "error": r["error"],
                        "error_code": r["error_code"] if "error_code" in r.keys() else None,
                        "metadata": _json_loads(r["metadata_json"]) if "metadata_json" in r.keys() else None,
                    }
                    for r in agent_rows
                ]
                skills = [
                    {
                        "execution_id": r["id"],
                        "skill_id": r["skill_id"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "trace_id": r["trace_id"],
                        "user_id": r["user_id"],
                        "error": r["error"],
                        "error_code": r["error_code"] if "error_code" in r.keys() else None,
                        "metadata": _json_loads(r["metadata_json"]) if "metadata_json" in r.keys() else None,
                    }
                    for r in skill_rows
                ]
                return {"agent_executions": agents, "skill_executions": skills}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Syscall Events (Audit) ====================

    async def add_syscall_event(self, event: Dict[str, Any]) -> None:
        """Append a syscall audit event (best-effort)."""
        await self.init()
        db_path = self._config.db_path

        # Best-effort normalize error_code for aggregation.
        error_code = event.get("error_code")
        if not error_code:
            try:
                # Prefer structured error object.
                err_obj = event.get("error") if isinstance(event.get("error"), dict) else None
                if isinstance(err_obj, dict) and err_obj.get("code"):
                    error_code = err_obj.get("code")
                else:
                    err_str = event.get("error")
                    if isinstance(err_str, str) and err_str.strip():
                        # Map common cases; fallback to uppercase token.
                        m = err_str.strip().upper().replace(" ", "_")
                        error_code = m[:64]
            except Exception:
                error_code = None

        payload = (
            event.get("id") or str(uuid.uuid4()),
            event.get("trace_id"),
            event.get("span_id"),
            event.get("run_id"),
            event.get("kind") or "",
            event.get("name") or "",
            event.get("status") or "",
            event.get("start_time"),
            event.get("end_time"),
            event.get("duration_ms"),
            _json_dumps(event.get("args") or {}),
            _json_dumps(event.get("result") or {}),
            event.get("error") if isinstance(event.get("error"), str) else _json_dumps(event.get("error") or None),
            error_code,
            event.get("target_type"),
            event.get("target_id"),
            event.get("user_id"),
            event.get("session_id"),
            event.get("approval_request_id"),
            float(event.get("created_at") or time.time()),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO syscall_events(
                      id, trace_id, span_id, run_id, kind, name, status, start_time, end_time, duration_ms,
                      args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                      approval_request_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def list_syscall_events(
        self,
        limit: int = 100,
        offset: int = 0,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        error_contains: Optional[str] = None,
        error_code: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List syscall events with basic filters (best-effort; no FTS)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                if span_id:
                    clauses.append("span_id=?")
                    params.append(span_id)
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                if kind:
                    clauses.append("kind=?")
                    params.append(kind)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if name:
                    clauses.append("name LIKE ?")
                    params.append(f"%{name}%")
                if error_contains:
                    clauses.append("error LIKE ?")
                    params.append(f"%{error_contains}%")
                if error_code:
                    clauses.append("error_code=?")
                    params.append(error_code)
                if target_type:
                    clauses.append("target_type=?")
                    params.append(target_type)
                if target_id:
                    clauses.append("target_id=?")
                    params.append(target_id)
                if approval_request_id:
                    clauses.append("approval_request_id=?")
                    params.append(approval_request_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM syscall_events {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM syscall_events
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()

                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "trace_id": r["trace_id"],
                            "span_id": r["span_id"] if "span_id" in r.keys() else None,
                            "run_id": r["run_id"],
                            "kind": r["kind"],
                            "name": r["name"],
                            "status": r["status"],
                            "start_time": r["start_time"],
                            "end_time": r["end_time"],
                            "duration_ms": r["duration_ms"],
                            "args": _json_loads(r["args_json"]) or {},
                            "result": _json_loads(r["result_json"]) or {},
                            "error": r["error"],
                            "error_code": r["error_code"] if "error_code" in r.keys() else None,
                            "target_type": r["target_type"] if "target_type" in r.keys() else None,
                            "target_id": r["target_id"] if "target_id" in r.keys() else None,
                            "user_id": r["user_id"] if "user_id" in r.keys() else None,
                            "session_id": r["session_id"] if "session_id" in r.keys() else None,
                            "approval_request_id": r["approval_request_id"] if "approval_request_id" in r.keys() else None,
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Runs / Run events (platform contract) ====================

    async def get_run_id_for_request(self, *, request_id: str, tenant_id: Optional[str] = None) -> Optional[str]:
        """Return existing run_id for a (tenant_id, request_id) pair."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[str]:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT run_id FROM request_dedup WHERE request_id=? AND (tenant_id=? OR tenant_id IS NULL OR ? IS NULL) LIMIT 1",
                    (request_id, tenant_id, tenant_id),
                ).fetchone()
                return str(row[0]) if row and row[0] else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def remember_request_run_id(self, *, request_id: str, run_id: str, tenant_id: Optional[str] = None) -> None:
        """Insert request_id -> run_id mapping (best-effort, idempotent)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO request_dedup(tenant_id, request_id, run_id, created_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(tenant_id, request_id) DO NOTHING;
                    """,
                    (tenant_id, request_id, run_id, float(time.time())),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def append_run_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Append an event and return its seq."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> int:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM run_events WHERE run_id=?", (run_id,)).fetchone()
                next_seq = int(row["m"] if row else 0) + 1
                conn.execute(
                    """
                    INSERT INTO run_events(run_id, seq, tenant_id, trace_id, type, payload_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        next_seq,
                        tenant_id,
                        trace_id,
                        str(event_type),
                        _json_dumps(payload or {}),
                        float(time.time()),
                    ),
                )
                conn.commit()
                return next_seq
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_run_events(
        self,
        *,
        run_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT seq, type, payload_json, trace_id, tenant_id, created_at
                    FROM run_events
                    WHERE run_id=? AND seq > ?
                    ORDER BY seq ASC
                    LIMIT ?;
                    """,
                    (run_id, int(after_seq), int(limit)),
                ).fetchall()
                items = []
                last_seq = int(after_seq)
                for r in rows:
                    last_seq = int(r["seq"])
                    items.append(
                        {
                            "seq": int(r["seq"]),
                            "type": r["type"],
                            "payload": _json_loads(r["payload_json"]) or {},
                            "trace_id": r["trace_id"],
                            "tenant_id": r["tenant_id"],
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "after_seq": int(after_seq), "last_seq": last_seq}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_run_summary(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Best-effort unified run view across agent/skill/tool executions.
        Assumption: execution_id == run_id (post v2).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                # agent
                row = conn.execute("SELECT * FROM agent_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                if row:
                    meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                    meta = meta or {}
                    err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                    return {
                        "run_id": row["id"],
                        "kind": "agent",
                        "target_type": "agent",
                        "target_id": row["agent_id"],
                        "trace_id": row["trace_id"],
                        "status": row["status"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "error_code": row["error_code"],
                        "error_message": row["error"] if "error" in row.keys() else None,
                        "error": err_obj or None,
                        "user_id": meta.get("user_id"),
                        "session_id": meta.get("session_id") or (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                    }
                # skill
                row = conn.execute("SELECT * FROM skill_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                if row:
                    meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                    meta = meta or {}
                    err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                    return {
                        "run_id": row["id"],
                        "kind": "skill",
                        "target_type": "skill",
                        "target_id": row["skill_id"],
                        "trace_id": row["trace_id"],
                        "status": row["status"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "error_code": row["error_code"],
                        "error_message": row["error"] if "error" in row.keys() else None,
                        "error": err_obj or None,
                        "user_id": row["user_id"] if "user_id" in row.keys() else meta.get("user_id"),
                        "session_id": meta.get("session_id") or (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                    }
                # tool
                # NOTE: tool_executions is not a guaranteed table in all schema versions.
                # Prefer reconstructing a best-effort summary from run_events.
                try:
                    row = conn.execute("SELECT * FROM tool_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                    if row:
                        meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                        meta = meta or {}
                        err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                        return {
                            "run_id": row["id"],
                            "kind": "tool",
                            "target_type": "tool",
                            "target_id": row["tool_name"],
                            "trace_id": row["trace_id"],
                            "status": row["status"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "error_code": row["error_code"],
                            "error_message": row["error"] if "error" in row.keys() else None,
                            "error": err_obj or None,
                            "user_id": row["user_id"] if "user_id" in row.keys() else meta.get("user_id"),
                            "session_id": row["session_id"] if "session_id" in row.keys() else (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                        }
                except Exception:
                    pass

                # Fallback: build run summary from run_events (run_start/run_end).
                try:
                    start = conn.execute(
                        "SELECT seq, trace_id, tenant_id, payload_json, created_at FROM run_events WHERE run_id=? AND type='run_start' ORDER BY seq ASC LIMIT 1",
                        (run_id,),
                    ).fetchone()
                    if start:
                        start_payload = _json_loads(start["payload_json"]) or {}
                        kind = str(start_payload.get("kind") or "unknown")
                        trace_id = start["trace_id"]
                        tenant_id = start["tenant_id"]
                        start_time = start["created_at"]
                        end = conn.execute(
                            "SELECT seq, payload_json, created_at FROM run_events WHERE run_id=? AND type='run_end' ORDER BY seq DESC LIMIT 1",
                            (run_id,),
                        ).fetchone()
                        end_payload = _json_loads(end["payload_json"]) or {} if end else {}
                        status = str(end_payload.get("status") or "running") if end else "running"
                        end_time = end["created_at"] if end else None
                        target_id = (
                            start_payload.get("agent_id")
                            or start_payload.get("skill_id")
                            or start_payload.get("tool_name")
                            or end_payload.get("tool_name")
                            or end_payload.get("agent_id")
                            or end_payload.get("skill_id")
                        )
                        session_id = (
                            start_payload.get("session_id")
                            or (start_payload.get("context") or {}).get("session_id")
                            if isinstance(start_payload.get("context"), dict)
                            else None
                        )
                        user_id = start_payload.get("user_id")
                        return {
                            "run_id": run_id,
                            "kind": kind,
                            "target_type": kind,
                            "target_id": target_id,
                            "trace_id": trace_id,
                            "status": status,
                            "start_time": start_time,
                            "end_time": end_time,
                            "error_code": None,
                            "error_message": end_payload.get("error"),
                            "error": None,
                            "user_id": user_id,
                            "session_id": session_id,
                            "tenant_id": tenant_id,
                        }
                except Exception:
                    pass
                return None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Audit Logs (enterprise governance) ====================

    async def add_audit_log(
        self,
        *,
        action: str,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
    ) -> None:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, actor_role, action, resource_type, resource_id,
                      request_id, run_id, trace_id, status, detail_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        tenant_id,
                        actor_id,
                        actor_role,
                        str(action),
                        resource_type,
                        resource_id,
                        request_id,
                        run_id,
                        trace_id,
                        status,
                        _json_dumps(detail or {}),
                        float(created_at if created_at is not None else time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def list_audit_logs(
        self,
        *,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
        created_after: Optional[float] = None,
        created_before: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["1=1"]
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if actor_id:
                    clauses.append("actor_id=?")
                    params.append(str(actor_id))
                if action:
                    clauses.append("action=?")
                    params.append(str(action))
                if resource_type:
                    clauses.append("resource_type=?")
                    params.append(str(resource_type))
                if resource_id:
                    clauses.append("resource_id=?")
                    params.append(str(resource_id))
                if request_id:
                    clauses.append("request_id=?")
                    params.append(str(request_id))
                if run_id:
                    clauses.append("run_id=?")
                    params.append(str(run_id))
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(str(trace_id))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                if created_after is not None:
                    clauses.append("created_at>=?")
                    params.append(float(created_after))
                if created_before is not None:
                    clauses.append("created_at<=?")
                    params.append(float(created_before))
                where = " AND ".join(clauses)
                total = conn.execute(f"SELECT COUNT(1) FROM audit_logs WHERE {where}", params).fetchone()[0]
                rows = conn.execute(
                    f"""
                    SELECT id, tenant_id, actor_id, actor_role, action, resource_type, resource_id,
                           request_id, run_id, trace_id, status, detail_json, created_at
                    FROM audit_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params, int(limit), int(offset)],
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "tenant_id": r["tenant_id"],
                            "actor_id": r["actor_id"],
                            "actor_role": r["actor_role"],
                            "action": r["action"],
                            "resource_type": r["resource_type"],
                            "resource_id": r["resource_id"],
                            "request_id": r["request_id"],
                            "run_id": r["run_id"],
                            "trace_id": r["trace_id"],
                            "status": r["status"],
                            "detail": _json_loads(r["detail_json"]) or {},
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "total": int(total), "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Tenant Policies (policy-as-code) ====================

    async def get_tenant_policy(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT tenant_id, version, policy_json, updated_at FROM tenant_policies WHERE tenant_id=? LIMIT 1",
                    (str(tenant_id),),
                ).fetchone()
                if not row:
                    return None
                return {
                    "tenant_id": row["tenant_id"],
                    "version": int(row["version"]),
                    "policy": _json_loads(row["policy_json"]) or {},
                    "updated_at": row["updated_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def upsert_tenant_policy(self, *, tenant_id: str, policy: Dict[str, Any], version: Optional[int] = None) -> Dict[str, Any]:
        """
        Upsert a tenant policy.
        If version is provided, treat it as optimistic concurrency: update only when current version matches.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                current = conn.execute(
                    "SELECT version FROM tenant_policies WHERE tenant_id=? LIMIT 1", (str(tenant_id),)
                ).fetchone()
                cur_ver = int(current["version"]) if current else 0
                if version is not None and current and int(version) != cur_ver:
                    raise ValueError("version_conflict")
                next_ver = cur_ver + 1
                now = float(time.time())
                conn.execute(
                    """
                    INSERT INTO tenant_policies(tenant_id, version, policy_json, updated_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                      version=excluded.version,
                      policy_json=excluded.policy_json,
                      updated_at=excluded.updated_at;
                    """,
                    (str(tenant_id), int(next_ver), _json_dumps(policy or {}), now),
                )
                conn.commit()
                return {"tenant_id": str(tenant_id), "version": int(next_ver), "policy": policy or {}, "updated_at": now}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_tenant_policies(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = conn.execute("SELECT COUNT(1) FROM tenant_policies").fetchone()[0]
                rows = conn.execute(
                    """
                    SELECT tenant_id, version, policy_json, updated_at
                    FROM tenant_policies
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (int(limit), int(offset)),
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "tenant_id": r["tenant_id"],
                            "version": int(r["version"]),
                            "policy": _json_loads(r["policy_json"]) or {},
                            "updated_at": r["updated_at"],
                        }
                    )
                return {"items": items, "total": int(total), "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Approval Requests ====================

    async def upsert_approval_request(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            record.get("request_id"),
            record.get("user_id"),
            record.get("operation"),
            record.get("details"),
            record.get("rule_id"),
            record.get("rule_type"),
            record.get("status"),
            record.get("amount"),
            record.get("batch_size"),
            1 if record.get("is_first_time") else 0,
            float(record.get("created_at") or time.time()),
            float(record.get("updated_at") or time.time()),
            record.get("expires_at"),
            _json_dumps(record.get("metadata") or {}),
            _json_dumps(record.get("result") or {}),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO approval_requests(
                      request_id, user_id, operation, details, rule_id, rule_type, status,
                      amount, batch_size, is_first_time, created_at, updated_at, expires_at,
                      metadata_json, result_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(request_id) DO UPDATE SET
                      user_id=excluded.user_id,
                      operation=excluded.operation,
                      details=excluded.details,
                      rule_id=excluded.rule_id,
                      rule_type=excluded.rule_type,
                      status=excluded.status,
                      amount=excluded.amount,
                      batch_size=excluded.batch_size,
                      is_first_time=excluded.is_first_time,
                      created_at=excluded.created_at,
                      updated_at=excluded.updated_at,
                      expires_at=excluded.expires_at,
                      metadata_json=excluded.metadata_json,
                      result_json=excluded.result_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_approval_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM approval_requests WHERE request_id=?", (request_id,)).fetchone()
                if not row:
                    return None
                return {
                    "request_id": row["request_id"],
                    "user_id": row["user_id"],
                    "operation": row["operation"],
                    "details": row["details"],
                    "rule_id": row["rule_id"],
                    "rule_type": row["rule_type"],
                    "status": row["status"],
                    "amount": row["amount"],
                    "batch_size": row["batch_size"],
                    "is_first_time": bool(row["is_first_time"] or 0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "expires_at": row["expires_at"],
                    "metadata": _json_loads(row["metadata_json"]) or {},
                    "result": _json_loads(row["result_json"]) or None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_approval_requests(
        self,
        *,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        include_related_counts: bool = False,
        order_by: str = "created_at",
        order_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if user_id:
                    clauses.append("user_id=?")
                    params.append(user_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM approval_requests {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)

                # Ordering: whitelist to avoid SQL injection
                _order_dir = "DESC" if str(order_dir).lower() in ("desc", "d", "-1") else "ASC"
                _order_by = str(order_by or "created_at").lower()
                allowed_order_by = {"created_at", "updated_at", "expires_at", "user_id", "operation", "status"}
                sql_order_by = "created_at" if _order_by not in allowed_order_by else _order_by

                # If ordering by priority_score, we sort in python after enrichment.
                if _order_by == "priority_score":
                    fetch_n = min(max(int(limit) + int(offset), 200), 2000)
                    rows = conn.execute(
                        f"""
                        SELECT * FROM approval_requests
                        {where_sql}
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        tuple(params + [fetch_n]),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM approval_requests
                        {where_sql}
                        ORDER BY {sql_order_by} {_order_dir}
                        LIMIT ? OFFSET ?
                        """,
                        tuple(params + [int(limit), int(offset)]),
                    ).fetchall()

                items = []
                now_ts = time.time()
                for r in rows:
                    item = {
                        "request_id": r["request_id"],
                        "user_id": r["user_id"],
                        "operation": r["operation"],
                        "details": r["details"],
                        "rule_id": r["rule_id"],
                        "rule_type": r["rule_type"],
                        "status": r["status"],
                        "amount": r["amount"],
                        "batch_size": r["batch_size"],
                        "is_first_time": bool(r["is_first_time"] or 0),
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "expires_at": r["expires_at"],
                        "metadata": _json_loads(r["metadata_json"]) or {},
                        "result": _json_loads(r["result_json"]) or None,
                    }

                    # Derived metrics for queueing / SLA
                    try:
                        item["age_seconds"] = max(0.0, float(now_ts - float(r["created_at"] or now_ts)))
                    except Exception:
                        item["age_seconds"] = 0.0
                    try:
                        if r["expires_at"] is not None:
                            item["expires_in_seconds"] = float(r["expires_at"] - now_ts)
                        else:
                            item["expires_in_seconds"] = None
                    except Exception:
                        item["expires_in_seconds"] = None

                    if include_related_counts:
                        try:
                            aid = r["request_id"]
                            c1 = conn.execute(
                                "SELECT COUNT(1) AS c FROM syscall_events WHERE approval_request_id=?",
                                (aid,),
                            ).fetchone()
                            c2 = conn.execute(
                                "SELECT COUNT(1) AS c FROM agent_executions WHERE approval_request_id=?",
                                (aid,),
                            ).fetchone()
                            item["related_counts"] = {
                                "syscall_events": int(c1["c"] if c1 else 0),
                                "agent_executions": int(c2["c"] if c2 else 0),
                            }
                        except Exception:
                            item["related_counts"] = {"syscall_events": 0, "agent_executions": 0}

                    # Priority score: higher means more urgent
                    # Heuristic: age + impact + danger (prefer tool metadata.risk_weight when available)
                    meta = item.get("metadata") or {}
                    danger_weight = 0.0
                    try:
                        if isinstance(meta, dict) and "risk_weight" in meta:
                            danger_weight = float(meta.get("risk_weight") or 0.0)
                        else:
                            op = str(item.get("operation") or "")
                            if op.startswith("tool:"):
                                t = op.split(":", 1)[1]
                                if t in ("database", "database_write"):
                                    danger_weight = 50.0
                                elif t in ("code", "code_execution"):
                                    danger_weight = 40.0
                                elif t in ("file_operations", "file_write"):
                                    danger_weight = 30.0
                                else:
                                    danger_weight = 10.0
                    except Exception:
                        danger_weight = 0.0
                    age_hours = float(item.get("age_seconds") or 0.0) / 3600.0
                    rel = item.get("related_counts") or {"syscall_events": 0, "agent_executions": 0}
                    impact = float(rel.get("syscall_events", 0)) * 5.0 + float(rel.get("agent_executions", 0)) * 2.0
                    item["priority_score"] = danger_weight + impact + age_hours

                    items.append(item)

                if _order_by == "priority_score":
                    reverse = True if _order_dir == "DESC" else False
                    items.sort(key=lambda x: float(x.get("priority_score") or 0.0), reverse=reverse)
                    items = items[int(offset) : int(offset) + int(limit)]
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Agent ====================

    async def upsert_agent_execution(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        meta = record.get("metadata") or {}
        error_code = record.get("error_code")
        if not error_code:
            try:
                if isinstance(meta, dict) and isinstance(meta.get("error_detail"), dict):
                    error_code = meta.get("error_detail", {}).get("code")
            except Exception:
                error_code = None

        payload = (
            record.get("id"),
            record.get("agent_id"),
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            error_code,
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("trace_id"),
            _json_dumps(meta),
            record.get("approval_request_id"),
            time.time(),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO agent_executions
                      (id, agent_id, status, input_json, output_json, error, error_code, start_time, end_time, duration_ms, trace_id, metadata_json, approval_request_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      agent_id=excluded.agent_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      error_code=excluded.error_code,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      trace_id=excluded.trace_id,
                      metadata_json=excluded.metadata_json,
                      approval_request_id=excluded.approval_request_id;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_agent_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM agent_executions WHERE id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "error_code": row["error_code"] if "error_code" in row.keys() else None,
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                    "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_agent_executions_by_approval_request_id(
        self,
        approval_request_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List agent executions associated with an approval_request_id."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute(
                    "SELECT COUNT(1) AS c FROM agent_executions WHERE approval_request_id = ?",
                    (approval_request_id,),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE approval_request_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (approval_request_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                            "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Phase 6 (placeholder): learning artifacts (evaluation/feedback/evolution)
    # ---------------------------------------------------------------------

    async def upsert_learning_artifact(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            record.get("artifact_id"),
            record.get("kind") or "",
            record.get("target_type") or "",
            record.get("target_id") or "",
            record.get("version") or "",
            record.get("status") or "draft",
            record.get("trace_id"),
            record.get("run_id"),
            _json_dumps(record.get("payload") or {}),
            _json_dumps(record.get("metadata") or {}),
            float(record.get("created_at") or time.time()),
        )

        def _sync() -> None:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO learning_artifacts(
                      artifact_id, kind, target_type, target_id, version, status,
                      trace_id, run_id, payload_json, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(artifact_id) DO UPDATE SET
                      kind=excluded.kind,
                      target_type=excluded.target_type,
                      target_id=excluded.target_id,
                      version=excluded.version,
                      status=excluded.status,
                      trace_id=excluded.trace_id,
                      run_id=excluded.run_id,
                      payload_json=excluded.payload_json,
                      metadata_json=excluded.metadata_json,
                      created_at=excluded.created_at;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_learning_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM learning_artifacts WHERE artifact_id=?",
                    (artifact_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "artifact_id": row["artifact_id"],
                    "kind": row["kind"],
                    "target_type": row["target_type"],
                    "target_id": row["target_id"],
                    "version": row["version"],
                    "status": row["status"],
                    "trace_id": row["trace_id"],
                    "run_id": row["run_id"],
                    "payload": _json_loads(row["payload_json"]),
                    "metadata": _json_loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_learning_artifacts(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses: List[str] = []
                params: List[Any] = []
                if target_type:
                    clauses.append("target_type=?")
                    params.append(target_type)
                if target_id:
                    clauses.append("target_id=?")
                    params.append(target_id)
                if kind:
                    clauses.append("kind=?")
                    params.append(kind)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(
                    f"SELECT COUNT(1) AS c FROM learning_artifacts {where};",
                    tuple(params),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT * FROM learning_artifacts
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "artifact_id": row["artifact_id"],
                            "kind": row["kind"],
                            "target_type": row["target_type"],
                            "target_id": row["target_id"],
                            "version": row["version"],
                            "status": row["status"],
                            "trace_id": row["trace_id"],
                            "run_id": row["run_id"],
                            "payload": _json_loads(row["payload_json"]),
                            "metadata": _json_loads(row["metadata_json"]),
                            "created_at": row["created_at"],
                        }
                    )
                return {"total": total, "items": items, "limit": limit, "offset": offset}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_agent_history(self, agent_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = conn.execute(
                    "SELECT COUNT(1) AS c FROM agent_executions WHERE agent_id = ?",
                    (agent_id,),
                ).fetchone()["c"]
                rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE agent_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (agent_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                            "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Skill ====================

    async def upsert_skill_execution(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        meta = record.get("metadata") or {}
        error_code = record.get("error_code")
        if not error_code:
            try:
                if isinstance(meta, dict) and isinstance(meta.get("error_detail"), dict):
                    error_code = meta.get("error_detail", {}).get("code")
            except Exception:
                error_code = None

        payload = (
            record.get("id"),
            record.get("skill_id"),
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            error_code,
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("user_id"),
            record.get("trace_id"),
            _json_dumps(meta),
            time.time(),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO skill_executions
                      (id, skill_id, status, input_json, output_json, error, error_code, start_time, end_time, duration_ms, user_id, trace_id, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      skill_id=excluded.skill_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      error_code=excluded.error_code,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      user_id=excluded.user_id,
                      trace_id=excluded.trace_id,
                      metadata_json=excluded.metadata_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_skill_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM skill_executions WHERE id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "skill_id": row["skill_id"],
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "error_code": row["error_code"] if "error_code" in row.keys() else None,
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "user_id": row["user_id"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_skill_executions(self, skill_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = conn.execute(
                    "SELECT COUNT(1) AS c FROM skill_executions WHERE skill_id = ?",
                    (skill_id,),
                ).fetchone()["c"]
                rows = conn.execute(
                    """
                    SELECT * FROM skill_executions
                    WHERE skill_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (skill_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "skill_id": row["skill_id"],
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "user_id": row["user_id"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Roadmap-3: Jobs/Cron (minimal scheduler persistence)
    # ---------------------------------------------------------------------

    async def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            payload = {
                "id": job.get("id") or f"job-{uuid.uuid4().hex[:12]}",
                "name": str(job.get("name") or ""),
                "enabled": 1 if bool(job.get("enabled", True)) else 0,
                "cron": str(job.get("cron") or "* * * * *"),
                "timezone": job.get("timezone"),
                "kind": str(job.get("kind") or "agent"),
                "target_id": str(job.get("target_id") or ""),
                "user_id": job.get("user_id"),
                "session_id": job.get("session_id"),
                "payload_json": _json_dumps(job.get("payload") or {}),
                "options_json": _json_dumps(job.get("options") or {}),
                "delivery_json": _json_dumps(job.get("delivery") or {}),
                "last_run_at": job.get("last_run_at"),
                "next_run_at": job.get("next_run_at"),
                "created_at": job.get("created_at") or now,
                "updated_at": job.get("updated_at") or now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO jobs(
                      id,name,enabled,cron,timezone,kind,target_id,user_id,session_id,
                      payload_json,options_json,delivery_json,last_run_at,next_run_at,created_at,updated_at
                    ) VALUES(
                      :id,:name,:enabled,:cron,:timezone,:kind,:target_id,:user_id,:session_id,
                      :payload_json,:options_json,:delivery_json,:last_run_at,:next_run_at,:created_at,:updated_at
                    );
                    """,
                    payload,
                )
                conn.commit()
                return payload
            finally:
                conn.close()

        rec = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(rec)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return None
                return dict(row)
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(row) if row else None

    async def list_jobs(self, *, limit: int = 100, offset: int = 0, enabled: Optional[bool] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if enabled is not None:
                    where = "WHERE enabled = ?"
                    args.append(1 if enabled else 0)

                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM jobs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM jobs
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        return {
            "items": [self._job_row_to_obj(r) for r in (res.get("items") or [])],
            "total": int(res.get("total") or 0),
            "limit": int(limit),
            "offset": int(offset),
        }

    async def update_job(self, job_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                now = time.time()
                updated = dict(cur)
                for k in ("name", "cron", "timezone", "kind", "target_id", "user_id", "session_id", "last_run_at", "next_run_at"):
                    if k in patch:
                        updated[k] = patch.get(k)
                if "enabled" in patch:
                    updated["enabled"] = 1 if bool(patch.get("enabled")) else 0
                if "payload" in patch:
                    updated["payload_json"] = _json_dumps(patch.get("payload") or {})
                if "options" in patch:
                    updated["options_json"] = _json_dumps(patch.get("options") or {})
                if "delivery" in patch:
                    updated["delivery_json"] = _json_dumps(patch.get("delivery") or {})
                updated["updated_at"] = now

                conn.execute(
                    """
                    UPDATE jobs SET
                      name=:name,
                      enabled=:enabled,
                      cron=:cron,
                      timezone=:timezone,
                      kind=:kind,
                      target_id=:target_id,
                      user_id=:user_id,
                      session_id=:session_id,
                      payload_json=:payload_json,
                      options_json=:options_json,
                      delivery_json=:delivery_json,
                      last_run_at=:last_run_at,
                      next_run_at=:next_run_at,
                      updated_at=:updated_at
                    WHERE id=:id;
                    """,
                    {**updated, "id": job_id},
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(row) if row else None

    async def delete_job(self, job_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM jobs WHERE id = ?;", (job_id,))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_due_jobs(self, *, now_ts: float, limit: int = 20) -> List[Dict[str, Any]]:
        """List enabled jobs whose next_run_at <= now_ts."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE enabled = 1
                      AND next_run_at IS NOT NULL
                      AND next_run_at <= ?
                      AND (lock_until IS NULL OR lock_until <= ?)
                    ORDER BY next_run_at ASC
                    LIMIT ?;
                    """,
                    (float(now_ts), float(now_ts), int(limit)),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        return [self._job_row_to_obj(r) for r in rows]

    async def acquire_job_lock(self, job_id: str, *, owner: str, ttl_seconds: float = 300.0) -> bool:
        """
        Leaderless lock:
        - Acquire succeeds if lock is absent or expired.
        - Lock auto-expires by lock_until (TTL).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                now = time.time()
                lock_until = now + float(ttl_seconds)
                cur = conn.execute(
                    """
                    UPDATE jobs
                    SET lock_until = ?, lock_owner = ?, updated_at = ?
                    WHERE id = ?
                      AND (lock_until IS NULL OR lock_until <= ?);
                    """,
                    (float(lock_until), str(owner), float(now), str(job_id), float(now)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def release_job_lock(self, job_id: str, *, owner: str) -> None:
        """Release lock if owned by `owner` (best-effort)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            conn = sqlite3.connect(db_path)
            try:
                now = time.time()
                conn.execute(
                    """
                    UPDATE jobs
                    SET lock_until = NULL, lock_owner = NULL, updated_at = ?
                    WHERE id = ? AND lock_owner = ?;
                    """,
                    (float(now), str(job_id), str(owner)),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def create_job_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            payload = {
                "id": run.get("id") or f"jobrun-{uuid.uuid4().hex[:12]}",
                "job_id": str(run.get("job_id") or ""),
                "scheduled_for": run.get("scheduled_for"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "status": str(run.get("status") or "running"),
                "trace_id": run.get("trace_id"),
                "run_id": run.get("run_id"),
                "error": run.get("error"),
                "result_json": _json_dumps(run.get("result") or {}),
                "created_at": run.get("created_at") or now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO job_runs(
                      id,job_id,scheduled_for,started_at,finished_at,status,trace_id,run_id,error,result_json,created_at
                    ) VALUES(
                      :id,:job_id,:scheduled_for,:started_at,:finished_at,:status,:trace_id,:run_id,:error,:result_json,:created_at
                    );
                    """,
                    payload,
                )
                conn.commit()
                return payload
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row)

    async def finish_job_run(self, run_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                updated = dict(cur)
                for k in ("scheduled_for", "started_at", "finished_at", "status", "trace_id", "run_id", "error"):
                    if k in patch:
                        updated[k] = patch.get(k)
                if "result" in patch:
                    updated["result_json"] = _json_dumps(patch.get("result") or {})
                conn.execute(
                    """
                    UPDATE job_runs SET
                      scheduled_for=:scheduled_for,
                      started_at=:started_at,
                      finished_at=:finished_at,
                      status=:status,
                      trace_id=:trace_id,
                      run_id=:run_id,
                      error=:error,
                      result_json=:result_json
                    WHERE id=:id;
                    """,
                    {**updated, "id": run_id},
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row) if row else None

    async def list_job_runs(self, *, job_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM job_runs WHERE job_id = ?;", (job_id,)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM job_runs
                    WHERE job_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (job_id, int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        return {
            "items": [self._job_run_row_to_obj(r) for r in (res.get("items") or [])],
            "total": int(res.get("total") or 0),
            "limit": int(limit),
            "offset": int(offset),
        }

    async def get_job_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_runs WHERE id = ?", (str(run_id),)).fetchone()
                if not row:
                    return None
                return dict(row)
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row) if row else None

    # ---------------------------------------------------------------------
    # Roadmap-4: Skill Packs + Long-term Memory (minimal)
    # ---------------------------------------------------------------------

    async def create_skill_pack(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": pack.get("id") or f"sp-{uuid.uuid4().hex[:12]}",
                "name": str(pack.get("name") or ""),
                "description": pack.get("description"),
                "manifest_json": _json_dumps(pack.get("manifest") or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "INSERT INTO skill_packs(id,name,description,manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,?);",
                    (rec["id"], rec["name"], rec["description"], rec["manifest_json"], rec["created_at"], rec["updated_at"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def get_skill_pack(self, pack_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_skill_packs(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM skill_packs;").fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM skill_packs ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    (int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r.get("description"),
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    # ==================== Job Delivery Attempts / DLQ (Roadmap-3) ====================

    async def add_job_delivery_attempt(
        self,
        *,
        job_id: str,
        run_id: Optional[str],
        attempt: int,
        url: Optional[str],
        status: str,
        response_status: Optional[int] = None,
        error: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"jda-{uuid.uuid4().hex[:12]}",
                "job_id": str(job_id),
                "run_id": str(run_id) if run_id else None,
                "attempt": int(attempt),
                "url": str(url) if url else None,
                "status": str(status),
                "response_status": int(response_status) if response_status is not None else None,
                "error": str(error) if error else None,
                "payload_json": _json_dumps(payload or {}),
                "created_at": now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO job_delivery_attempts(
                      id, job_id, run_id, attempt, url, status, response_status, error, payload_json, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["job_id"],
                        rec["run_id"],
                        rec["attempt"],
                        rec["url"],
                        rec["status"],
                        rec["response_status"],
                        rec["error"],
                        rec["payload_json"],
                        rec["created_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "payload": _json_loads(row.get("payload_json")) or {}}

    async def enqueue_job_delivery_dlq(
        self,
        *,
        job_id: str,
        run_id: Optional[str],
        url: Optional[str],
        delivery: Optional[Dict[str, Any]],
        payload: Optional[Dict[str, Any]],
        attempts: int,
        error: Optional[str],
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"dlq-{uuid.uuid4().hex[:12]}",
                "job_id": str(job_id),
                "run_id": str(run_id) if run_id else None,
                "url": str(url) if url else None,
                "delivery_json": _json_dumps(delivery or {}),
                "payload_json": _json_dumps(payload or {}),
                "attempts": int(attempts),
                "error": str(error) if error else None,
                "status": "pending",
                "created_at": now,
                "resolved_at": None,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO job_delivery_dlq(
                      id, job_id, run_id, url, delivery_json, payload_json, attempts, error, status, created_at, resolved_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["job_id"],
                        rec["run_id"],
                        rec["url"],
                        rec["delivery_json"],
                        rec["payload_json"],
                        rec["attempts"],
                        rec["error"],
                        rec["status"],
                        rec["created_at"],
                        rec["resolved_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            **row,
            "delivery": _json_loads(row.get("delivery_json")) or {},
            "payload": _json_loads(row.get("payload_json")) or {},
        }

    async def list_job_delivery_dlq(
        self,
        *,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if status:
                    clauses.append("status = ?")
                    params.append(str(status))
                if job_id:
                    clauses.append("job_id = ?")
                    params.append(str(job_id))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM job_delivery_dlq {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM job_delivery_dlq {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    **r,
                    "delivery": _json_loads(r.get("delivery_json")) or {},
                    "payload": _json_loads(r.get("payload_json")) or {},
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_job_delivery_dlq_item(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_delivery_dlq WHERE id = ?;", (str(dlq_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        r = await anyio.to_thread.run_sync(_sync)
        if not r:
            return None
        return {**r, "delivery": _json_loads(r.get("delivery_json")) or {}, "payload": _json_loads(r.get("payload_json")) or {}}

    async def mark_job_delivery_dlq_resolved(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute(
                    "UPDATE job_delivery_dlq SET status='resolved', resolved_at=? WHERE id=?;",
                    (time.time(), str(dlq_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def delete_job_delivery_dlq_item(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM job_delivery_dlq WHERE id=?;", (str(dlq_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    # ==================== Gateway Pairings / Tokens (Roadmap-3) ====================

    async def upsert_gateway_pairing(
        self,
        *,
        channel: str,
        channel_user_id: str,
        user_id: str,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"gwp-{uuid.uuid4().hex[:12]}",
                "channel": str(channel or "default"),
                "channel_user_id": str(channel_user_id),
                "user_id": str(user_id or "system"),
                "session_id": str(session_id) if session_id else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO gateway_pairings(
                      id, channel, channel_user_id, user_id, session_id, tenant_id, metadata_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(channel, channel_user_id) DO UPDATE SET
                      user_id=excluded.user_id,
                      session_id=excluded.session_id,
                      tenant_id=excluded.tenant_id,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["id"],
                        rec["channel"],
                        rec["channel_user_id"],
                        rec["user_id"],
                        rec["session_id"],
                        rec["tenant_id"],
                        rec["metadata_json"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (rec["channel"], rec["channel_user_id"]),
                ).fetchone()
                return dict(row) if row else rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def resolve_gateway_pairing(self, *, channel: str, channel_user_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (str(channel or "default"), str(channel_user_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_gateway_pairings(
        self,
        *,
        channel: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if channel:
                    clauses.append("channel=?")
                    params.append(str(channel))
                if user_id:
                    clauses.append("user_id=?")
                    params.append(str(user_id))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM gateway_pairings {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM gateway_pairings {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_gateway_pairing(self, *, channel: str, channel_user_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute(
                    "DELETE FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (str(channel or "default"), str(channel_user_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def create_gateway_token(
        self,
        *,
        name: str,
        token: str,
        tenant_id: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        import hashlib

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"gwt-{uuid.uuid4().hex[:12]}",
                "name": str(name or "token"),
                "token_sha256": hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "enabled": 1 if enabled else 0,
                "created_at": now,
                "metadata_json": _json_dumps(metadata or {}),
            }
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO gateway_tokens(id,name,token_sha256,tenant_id,enabled,created_at,metadata_json)
                    VALUES(?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["name"],
                        rec["token_sha256"],
                        rec["tenant_id"],
                        rec["enabled"],
                        rec["created_at"],
                        rec["metadata_json"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def validate_gateway_token(self, *, token: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path
        import hashlib

        def _sync() -> Optional[Dict[str, Any]]:
            sha = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM gateway_tokens WHERE enabled=1 AND token_sha256=? ORDER BY created_at DESC LIMIT 1;",
                    (sha,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_gateway_tokens(self, *, limit: int = 100, offset: int = 0, enabled: Optional[bool] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if enabled is not None:
                    clauses.append("enabled = ?")
                    params.append(1 if enabled else 0)
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM gateway_tokens {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM gateway_tokens {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            # Never return token_sha256 to callers by default.
            rr = dict(r)
            rr.pop("token_sha256", None)
            items.append({**rr, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_gateway_token(self, *, token_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM gateway_tokens WHERE id=?;", (str(token_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def update_skill_pack(self, pack_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                now = time.time()
                name = str(patch.get("name") or cur.get("name") or "")
                desc = patch.get("description") if "description" in patch else cur.get("description")
                manifest = _json_dumps(patch.get("manifest") if "manifest" in patch else (_json_loads(cur.get("manifest_json")) or {}))
                conn.execute(
                    "UPDATE skill_packs SET name=?, description=?, manifest_json=?, updated_at=? WHERE id=?;",
                    (name, desc, manifest, float(now), str(pack_id)),
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def delete_skill_pack(self, pack_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM skill_packs WHERE id = ?;", (str(pack_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def publish_skill_pack_version(self, *, pack_id: str, version: str) -> Dict[str, Any]:
        """
        Publish an immutable version snapshot for a skill pack.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                pack = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not pack:
                    raise ValueError("Skill pack not found")
                rec = {
                    "id": f"spv-{uuid.uuid4().hex[:12]}",
                    "pack_id": str(pack_id),
                    "version": str(version),
                    "manifest_json": pack["manifest_json"],
                    "created_at": now,
                }
                conn.execute(
                    "INSERT INTO skill_pack_versions(id,pack_id,version,manifest_json,created_at) VALUES(?,?,?,?,?);",
                    (rec["id"], rec["pack_id"], rec["version"], rec["manifest_json"], rec["created_at"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
        }

    async def list_skill_pack_versions(self, *, pack_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM skill_pack_versions WHERE pack_id = ?;", (str(pack_id),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM skill_pack_versions WHERE pack_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (str(pack_id), int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "pack_id": r["pack_id"],
                    "version": r["version"],
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "created_at": r.get("created_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_skill_pack_version(self, *, pack_id: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM skill_pack_versions WHERE pack_id = ? AND version = ?;",
                    (str(pack_id), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
        }

    async def install_skill_pack(self, *, pack_id: str, version: Optional[str], scope: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"spi-{uuid.uuid4().hex[:12]}",
                "pack_id": str(pack_id),
                "version": str(version) if version is not None else None,
                "scope": str(scope or "workspace"),
                "installed_at": now,
                "metadata_json": _json_dumps(metadata or {}),
            }
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                # ensure pack exists
                pack = conn.execute("SELECT 1 FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not pack:
                    raise ValueError("Skill pack not found")
                # ensure version exists if provided
                if rec["version"]:
                    v = conn.execute(
                        "SELECT 1 FROM skill_pack_versions WHERE pack_id = ? AND version = ?;",
                        (str(pack_id), str(rec["version"])),
                    ).fetchone()
                    if not v:
                        raise ValueError("Skill pack version not found")
                conn.execute(
                    "INSERT INTO skill_pack_installs(id,pack_id,version,scope,installed_at,metadata_json) VALUES(?,?,?,?,?,?);",
                    (rec["id"], rec["pack_id"], rec["version"], rec["scope"], rec["installed_at"], rec["metadata_json"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row.get("version"),
            "scope": row.get("scope"),
            "installed_at": row.get("installed_at"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
        }

    async def list_skill_pack_installs(self, *, scope: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if scope:
                    where = "WHERE scope = ?"
                    args.append(str(scope))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM skill_pack_installs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM skill_pack_installs {where} ORDER BY installed_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "pack_id": r["pack_id"],
                    "version": r.get("version"),
                    "scope": r.get("scope"),
                    "installed_at": r.get("installed_at"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    # ---------------------------------------------------------------------
    # Roadmap-P0: packages registry (publish/install)
    # ---------------------------------------------------------------------

    async def publish_package_version(
        self,
        *,
        package_name: str,
        version: str,
        manifest: Dict[str, Any],
        artifact_path: Optional[str] = None,
        artifact_sha256: Optional[str] = None,
        approval_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"pkgv-{uuid.uuid4().hex[:12]}",
                "package_name": str(package_name),
                "version": str(version),
                "manifest_json": _json_dumps(manifest or {}),
                "artifact_path": str(artifact_path) if artifact_path else None,
                "artifact_sha256": str(artifact_sha256) if artifact_sha256 else None,
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "created_at": now,
            }
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO package_versions(
                      id, package_name, version, manifest_json, artifact_path, artifact_sha256, approval_request_id, created_at
                    ) VALUES(?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["package_name"],
                        rec["version"],
                        rec["manifest_json"],
                        rec["artifact_path"],
                        rec["artifact_sha256"],
                        rec["approval_request_id"],
                        rec["created_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "artifact_path": row.get("artifact_path"),
            "artifact_sha256": row.get("artifact_sha256"),
            "approval_request_id": row.get("approval_request_id"),
            "created_at": row.get("created_at"),
        }

    async def list_package_versions(self, *, package_name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM package_versions WHERE package_name = ?;", (str(package_name),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM package_versions WHERE package_name = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (str(package_name), int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items: List[Dict[str, Any]] = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "package_name": r["package_name"],
                    "version": r["version"],
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "artifact_path": r.get("artifact_path"),
                    "artifact_sha256": r.get("artifact_sha256"),
                    "approval_request_id": r.get("approval_request_id"),
                    "created_at": r.get("created_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_package_version(self, *, package_name: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM package_versions WHERE package_name = ? AND version = ?;",
                    (str(package_name), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "artifact_path": row.get("artifact_path"),
            "artifact_sha256": row.get("artifact_sha256"),
            "approval_request_id": row.get("approval_request_id"),
            "created_at": row.get("created_at"),
        }

    async def record_package_install(
        self,
        *,
        package_name: str,
        version: Optional[str],
        scope: str,
        metadata: Optional[Dict[str, Any]] = None,
        approval_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"pkgi-{uuid.uuid4().hex[:12]}",
                "package_name": str(package_name),
                "version": str(version) if version is not None else None,
                "scope": str(scope or "workspace"),
                "installed_at": now,
                "metadata_json": _json_dumps(metadata or {}),
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
            }
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                if rec["version"]:
                    v = conn.execute(
                        "SELECT 1 FROM package_versions WHERE package_name = ? AND version = ?;",
                        (str(package_name), str(rec["version"])),
                    ).fetchone()
                    if not v:
                        raise ValueError("Package version not found")
                conn.execute(
                    "INSERT INTO package_installs(id,package_name,version,scope,installed_at,metadata_json,approval_request_id) VALUES(?,?,?,?,?,?,?);",
                    (
                        rec["id"],
                        rec["package_name"],
                        rec["version"],
                        rec["scope"],
                        rec["installed_at"],
                        rec["metadata_json"],
                        rec["approval_request_id"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row.get("version"),
            "scope": row.get("scope"),
            "installed_at": row.get("installed_at"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "approval_request_id": row.get("approval_request_id"),
        }

    async def list_package_installs(self, *, scope: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if scope:
                    where = "WHERE scope = ?"
                    args.append(str(scope))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM package_installs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM package_installs {where} ORDER BY installed_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items: List[Dict[str, Any]] = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "package_name": r["package_name"],
                    "version": r.get("version"),
                    "scope": r.get("scope"),
                    "installed_at": r.get("installed_at"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "approval_request_id": r.get("approval_request_id"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    # ---------------------------------------------------------------------
    # Adapters Registry (persist LLM adapter configs)
    # ---------------------------------------------------------------------

    async def upsert_adapter(self, record: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = dict(record or {})
            adapter_id = str(rec.get("adapter_id") or rec.get("id") or "")
            if not adapter_id:
                adapter_id = f"adapter-{uuid.uuid4().hex[:8]}"
            rec["adapter_id"] = adapter_id
            rec.setdefault("status", "active")
            rec.setdefault("created_at", now)
            rec["updated_at"] = now

            # Encrypt api_key at rest when configured.
            api_key_plain = str(rec.get("api_key") or "")
            api_key_enc = None
            api_key_kid = None
            try:
                from core.harness.infrastructure.crypto.secretbox import encrypt_str, is_configured

                if api_key_plain and is_configured():
                    api_key_enc = encrypt_str(api_key_plain)
                    api_key_kid = "fernet:v1"
                    api_key_plain = ""  # avoid storing plaintext
            except Exception:
                # fail-open: keep legacy plaintext
                pass

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO adapters(
                      adapter_id, name, provider, description, status,
                      api_key, api_base_url, organization_id,
                      api_key_enc, api_key_kid,
                      models_json, rate_limit_json, retry_config_json, metadata_json,
                      created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(adapter_id) DO UPDATE SET
                      name=excluded.name,
                      provider=excluded.provider,
                      description=excluded.description,
                      status=excluded.status,
                      api_key=excluded.api_key,
                      api_key_enc=excluded.api_key_enc,
                      api_key_kid=excluded.api_key_kid,
                      api_base_url=excluded.api_base_url,
                      organization_id=excluded.organization_id,
                      models_json=excluded.models_json,
                      rate_limit_json=excluded.rate_limit_json,
                      retry_config_json=excluded.retry_config_json,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        adapter_id,
                        str(rec.get("name") or ""),
                        str(rec.get("provider") or ""),
                        str(rec.get("description") or ""),
                        str(rec.get("status") or "active"),
                        str(api_key_plain or ""),
                        str(rec.get("api_base_url") or ""),
                        str(rec.get("organization_id") or "") or None,
                        api_key_enc,
                        api_key_kid,
                        _json_dumps(rec.get("models") or []),
                        _json_dumps(rec.get("rate_limit") or {}),
                        _json_dumps(rec.get("retry_config") or {}),
                        _json_dumps(rec.get("metadata") or {}),
                        float(rec.get("created_at") or now),
                        float(now),
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM adapters WHERE adapter_id=?;", (adapter_id,)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        api_key = row.get("api_key")
        try:
            from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

            if row.get("api_key_enc") and is_configured():
                api_key = decrypt_str(row.get("api_key_enc"))
        except Exception:
            pass
        return {
            "adapter_id": row.get("adapter_id"),
            "name": row.get("name"),
            "provider": row.get("provider"),
            "description": row.get("description"),
            "status": row.get("status"),
            "api_key": api_key,
            "api_base_url": row.get("api_base_url"),
            "organization_id": row.get("organization_id"),
            "models": _json_loads(row.get("models_json")) or [],
            "rate_limit": _json_loads(row.get("rate_limit_json")) or {},
            "retry_config": _json_loads(row.get("retry_config_json")) or {},
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def get_adapter(self, adapter_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM adapters WHERE adapter_id=?;", (str(adapter_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        api_key = row.get("api_key")
        try:
            from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

            if row.get("api_key_enc") and is_configured():
                api_key = decrypt_str(row.get("api_key_enc"))
        except Exception:
            pass
        return {
            "adapter_id": row.get("adapter_id"),
            "name": row.get("name"),
            "provider": row.get("provider"),
            "description": row.get("description"),
            "status": row.get("status"),
            "api_key": api_key,
            "api_base_url": row.get("api_base_url"),
            "organization_id": row.get("organization_id"),
            "models": _json_loads(row.get("models_json")) or [],
            "rate_limit": _json_loads(row.get("rate_limit_json")) or {},
            "retry_config": _json_loads(row.get("retry_config_json")) or {},
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_adapters(self, *, provider: Optional[str] = None, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if provider:
                    clauses.append("provider=?")
                    params.append(str(provider))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM adapters {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM adapters {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "adapter_id": r.get("adapter_id"),
                    "name": r.get("name"),
                    "provider": r.get("provider"),
                    "description": r.get("description"),
                    "status": r.get("status"),
                    "api_base_url": r.get("api_base_url"),
                    "models": _json_loads(r.get("models_json")) or [],
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_adapter(self, adapter_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM adapters WHERE adapter_id=?;", (str(adapter_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_adapter_secrets_status(self) -> Dict[str, Any]:
        """
        Returns counts of encrypted/plaintext adapter secrets stored at rest.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = int(conn.execute("SELECT COUNT(1) AS c FROM adapters;").fetchone()["c"])
                enc = int(conn.execute("SELECT COUNT(1) AS c FROM adapters WHERE api_key_enc IS NOT NULL AND api_key_enc != '';").fetchone()["c"])
                plain = int(conn.execute("SELECT COUNT(1) AS c FROM adapters WHERE api_key IS NOT NULL AND api_key != '';").fetchone()["c"])
                return {"total": total, "encrypted": enc, "plaintext": plain}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def migrate_adapter_secrets_to_encrypted(self) -> Dict[str, Any]:
        """
        Encrypt any legacy plaintext api_key into api_key_enc and clear api_key.
        Requires AIPLAT_SECRET_KEY configured; otherwise raises.
        """
        await self.init()
        db_path = self._config.db_path

        from core.harness.infrastructure.crypto.secretbox import encrypt_str, is_configured

        if not is_configured():
            raise RuntimeError("AIPLAT_SECRET_KEY is not set")

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            updated = 0
            skipped = 0
            try:
                rows = conn.execute(
                    "SELECT adapter_id, api_key, api_key_enc FROM adapters WHERE api_key IS NOT NULL AND api_key != '';"
                ).fetchall()
                for r in rows:
                    aid = r["adapter_id"]
                    api_key = r["api_key"] or ""
                    api_key_enc = r["api_key_enc"]
                    if api_key_enc:
                        skipped += 1
                        continue
                    enc = encrypt_str(str(api_key))
                    conn.execute(
                        "UPDATE adapters SET api_key_enc=?, api_key_kid=?, api_key='' WHERE adapter_id=?;",
                        (enc, "fernet:v1", str(aid)),
                    )
                    updated += 1
                conn.commit()
            finally:
                conn.close()
            return {"updated": updated, "skipped": skipped, "scanned": len(rows)}

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Global settings
    # ---------------------------------------------------------------------

    async def upsert_global_setting(self, *, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO global_settings(key, value_json, updated_at)
                    VALUES(?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at;
                    """,
                    (str(key), _json_dumps(value or {}), float(now)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM global_settings WHERE key=?;", (str(key),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {"key": row.get("key"), "value": _json_loads(row.get("value_json")) or {}, "updated_at": row.get("updated_at")}

    async def get_global_setting(self, *, key: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM global_settings WHERE key=?;", (str(key),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {"key": row.get("key"), "value": _json_loads(row.get("value_json")) or {}, "updated_at": row.get("updated_at")}

    # ---------------------------------------------------------------------
    # Tenants (minimal registry)
    # ---------------------------------------------------------------------

    async def upsert_tenant(self, *, tenant_id: str, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row0 = conn.execute("SELECT tenant_id, created_at FROM tenants WHERE tenant_id=?;", (str(tenant_id),)).fetchone()
                created_at = float(row0["created_at"]) if row0 and row0.get("created_at") else float(now)
                conn.execute(
                    """
                    INSERT INTO tenants(tenant_id, name, metadata_json, created_at, updated_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                      name=excluded.name,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (str(tenant_id), str(name or tenant_id), _json_dumps(metadata or {}), created_at, float(now)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM tenants WHERE tenant_id=?;", (str(tenant_id),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "tenant_id": row.get("tenant_id"),
            "name": row.get("name"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_tenants(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = int(conn.execute("SELECT COUNT(1) FROM tenants;").fetchone()[0])
                rows = conn.execute("SELECT * FROM tenants ORDER BY updated_at DESC LIMIT ? OFFSET ?;", (int(limit), int(offset))).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "tenant_id": r.get("tenant_id"),
                    "name": r.get("name"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}
    async def add_long_term_memory(self, *, user_id: str, content: str, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"ltm-{uuid.uuid4().hex[:12]}",
                "user_id": str(user_id or "system"),
                "key": str(key) if key is not None else None,
                "content": str(content or ""),
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "INSERT INTO long_term_memories(id,user_id,key,content,metadata_json,created_at) VALUES(?,?,?,?,?,?);",
                    (rec["id"], rec["user_id"], rec["key"], rec["content"], rec["metadata_json"], rec["created_at"]),
                )
                # Best-effort: keep FTS in sync if available.
                try:
                    conn.execute(
                        "INSERT INTO long_term_memories_fts(id,user_id,key,content) VALUES(?,?,?,?);",
                        (rec["id"], rec["user_id"], rec["key"], rec["content"]),
                    )
                except Exception:
                    pass
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "key": row.get("key"),
            "content": row.get("content"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
        }

    async def search_long_term_memory(self, *, user_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                uid = str(user_id or "system")
                # Prefer FTS when available; fallback to LIKE.
                try:
                    # Basic query escaping for quotes.
                    q_fts = str(query or "").replace('"', '""').strip()
                    if q_fts:
                        rows = conn.execute(
                            """
                            SELECT m.* FROM long_term_memories m
                            JOIN (
                              SELECT id FROM long_term_memories_fts
                              WHERE long_term_memories_fts MATCH ?
                                AND user_id = ?
                              LIMIT ?
                            ) f ON f.id = m.id
                            ORDER BY m.created_at DESC;
                            """,
                            (q_fts, uid, int(limit)),
                        ).fetchall()
                        return [dict(r) for r in rows]
                except Exception:
                    pass

                q = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT * FROM long_term_memories
                    WHERE user_id = ? AND (content LIKE ? OR key LIKE ?)
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (uid, q, q, int(limit)),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "key": r.get("key"),
                    "content": r.get("content"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "created_at": r.get("created_at"),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Roadmap-4: persistent session memory + cross-session search (FTS)
    # ------------------------------------------------------------------

    async def create_memory_session(
        self,
        *,
        user_id: str,
        agent_type: str = "default",
        session_type: str = "session",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            sid = str(session_id) if session_id else f"sess-{uuid.uuid4().hex[:10]}"
            rec = {
                "id": sid,
                "user_id": str(user_id or "system"),
                "agent_type": str(agent_type or "default"),
                "session_type": str(session_type or "session"),
                "status": "active",
                "metadata_json": _json_dumps(metadata or {}),
                "message_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO memory_sessions(id,user_id,agent_type,session_type,status,metadata_json,message_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                      user_id=excluded.user_id,
                      agent_type=excluded.agent_type,
                      session_type=excluded.session_type,
                      status=excluded.status,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["id"],
                        rec["user_id"],
                        rec["agent_type"],
                        rec["session_type"],
                        rec["status"],
                        rec["metadata_json"],
                        rec["message_count"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def add_memory_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            mid = f"msg-{uuid.uuid4().hex[:12]}"
            rec = {
                "id": mid,
                "session_id": str(session_id or "default"),
                "user_id": str(user_id or "system"),
                "role": str(role or "user"),
                "content": str(content or ""),
                "metadata_json": _json_dumps(metadata or {}),
                "trace_id": str(trace_id) if trace_id else None,
                "run_id": str(run_id) if run_id else None,
                "created_at": now,
            }
            conn = sqlite3.connect(db_path)
            try:
                # Ensure session exists (idempotent).
                conn.execute(
                    """
                    INSERT INTO memory_sessions(id,user_id,agent_type,session_type,status,metadata_json,message_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at;
                    """,
                    (
                        rec["session_id"],
                        rec["user_id"],
                        "default",
                        "session",
                        "active",
                        "{}",
                        0,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO memory_messages(id,session_id,user_id,role,content,metadata_json,trace_id,run_id,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["session_id"],
                        rec["user_id"],
                        rec["role"],
                        rec["content"],
                        rec["metadata_json"],
                        rec["trace_id"],
                        rec["run_id"],
                        rec["created_at"],
                    ),
                )
                # best-effort: sync FTS
                try:
                    conn.execute(
                        "INSERT INTO memory_messages_fts(id,user_id,session_id,role,content) VALUES(?,?,?,?,?);",
                        (rec["id"], rec["user_id"], rec["session_id"], rec["role"], rec["content"]),
                    )
                except Exception:
                    pass
                conn.execute(
                    "UPDATE memory_sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?;",
                    (now, rec["session_id"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_memory_sessions(self, *, user_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if user_id:
                    where = "WHERE user_id = ?"
                    args.append(str(user_id))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM memory_sessions {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM memory_sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_memory_session(self, *, session_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM memory_sessions WHERE id = ?;", (str(session_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def delete_memory_session(self, *, session_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute("DELETE FROM memory_sessions WHERE id = ?;", (str(session_id),))
                conn.execute("DELETE FROM memory_messages WHERE session_id = ?;", (str(session_id),))
                try:
                    conn.execute("DELETE FROM memory_messages_fts WHERE session_id = ?;", (str(session_id),))
                except Exception:
                    pass
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def list_memory_messages(
        self, *, session_id: str, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute(
                    "SELECT COUNT(1) AS c FROM memory_messages WHERE session_id = ?;", (str(session_id),)
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM memory_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?;
                    """,
                    (str(session_id), int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def search_memory_messages(
        self,
        *,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                uid = str(user_id) if user_id else None
                q = str(query or "").strip()
                # Prefer FTS when available; fallback to LIKE.
                try:
                    if q:
                        q_fts = q.replace('"', '""')
                        where_uid = "AND user_id = ?" if uid else ""
                        params: List[Any] = [q_fts]
                        if uid:
                            params.append(uid)
                        params.extend([int(limit), int(offset)])
                        rows = conn.execute(
                            f"""
                            SELECT * FROM memory_messages_fts
                            WHERE memory_messages_fts MATCH ?
                              {where_uid}
                            LIMIT ? OFFSET ?;
                            """,
                            params,
                        ).fetchall()
                        # FTS table already carries content; hydrate minimal fields.
                        items = []
                        for r in rows:
                            items.append(
                                {
                                    "id": r["id"],
                                    "user_id": r["user_id"],
                                    "session_id": r["session_id"],
                                    "role": r["role"],
                                    "content": r["content"][:200],
                                    "score": 1.0,
                                }
                            )
                        return {"items": items, "total": len(items)}
                except Exception:
                    pass

                if not q:
                    return {"items": [], "total": 0}
                like = f"%{q}%"
                where = "WHERE content LIKE ?"
                params2: List[Any] = [like]
                if uid:
                    where += " AND user_id = ?"
                    params2.append(uid)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM memory_messages {where};", params2).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT id,user_id,session_id,role,content FROM memory_messages
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params2, int(limit), int(offset)],
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "user_id": r["user_id"],
                            "session_id": r["session_id"],
                            "role": r["role"],
                            "content": str(r["content"] or "")[:200],
                            "score": 1.0,
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    def _job_row_to_obj(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "enabled": bool(int(row.get("enabled") or 0)),
            "cron": row.get("cron"),
            "timezone": row.get("timezone"),
            "kind": row.get("kind"),
            "target_id": row.get("target_id"),
            "user_id": row.get("user_id"),
            "session_id": row.get("session_id"),
            "payload": _json_loads(row.get("payload_json")) or {},
            "options": _json_loads(row.get("options_json")) or {},
            "delivery": _json_loads(row.get("delivery_json")) or {},
            "last_run_at": row.get("last_run_at"),
            "next_run_at": row.get("next_run_at"),
            "lock_until": row.get("lock_until"),
            "lock_owner": row.get("lock_owner"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _job_run_row_to_obj(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "job_id": row.get("job_id"),
            "scheduled_for": row.get("scheduled_for"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "status": row.get("status"),
            "trace_id": row.get("trace_id"),
            "run_id": row.get("run_id"),
            "error": row.get("error"),
            "result": _json_loads(row.get("result_json")) or {},
            "created_at": row.get("created_at"),
        }


_execution_store: Optional[ExecutionStore] = None


def get_execution_store(db_path: Optional[str] = None) -> ExecutionStore:
    """Process-wide singleton."""
    global _execution_store
    desired_path = db_path or os.environ.get("AIPLAT_EXECUTION_DB_PATH", "data/aiplat_executions.sqlite3")
    # If caller/env changes db_path within the same process (common in tests),
    # re-create the singleton so it points at the correct database.
    if _execution_store is not None:
        try:
            if str(getattr(getattr(_execution_store, "_config", None), "db_path", "")) != str(desired_path):
                _execution_store = None
        except Exception:
            _execution_store = None

    if _execution_store is None:
        db_path = desired_path
        def _int_env(name: str) -> Optional[int]:
            v = os.environ.get(name)
            if v is None or str(v).strip() == "":
                return None
            try:
                return int(str(v).strip())
            except Exception:
                return None

        retention_days = _int_env("AIPLAT_EXECUTION_DB_RETENTION_DAYS")
        max_rows = _int_env("AIPLAT_EXECUTION_DB_MAX_ROWS_PER_ENTITY")
        prune_on_start = os.environ.get("AIPLAT_EXECUTION_DB_PRUNE_ON_START", "true").lower() not in ("0", "false", "no")
        vacuum_on_prune = os.environ.get("AIPLAT_EXECUTION_DB_VACUUM_ON_PRUNE", "false").lower() in ("1", "true", "yes")

        _execution_store = ExecutionStore(
            ExecutionStoreConfig(
                db_path=db_path,
                retention_days=retention_days,
                max_rows_per_entity=max_rows,
                prune_on_start=prune_on_start,
                vacuum_on_prune=vacuum_on_prune,
            )
        )
    return _execution_store
