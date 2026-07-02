"""
Database schema migration — extracted from execution_store.py _init_sync().

Contains all 51 schema migrations (v1-v51).
Pure function: takes conn + version params, zero self dependency.
"""
import time
import logging


def run_migrations(conn, current: int, target_version: int) -> int:
    """Apply schema migrations from current → target version."""
    # Local closure — captures conn from outer scope so the migration code
    # can call _set_version(ver) without passing conn explicitly.
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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE graph_runs ADD COLUMN resumed_from_checkpoint_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        conn.execute(

            "CREATE INDEX IF NOT EXISTS idx_graph_runs_parent ON graph_runs(parent_run_id);"

        )


        # executions: trace link

        try:

            conn.execute("ALTER TABLE agent_executions ADD COLUMN trace_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE skill_executions ADD COLUMN trace_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE skill_executions ADD COLUMN metadata_json TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_agent_exec_approval_id ON agent_executions(approval_request_id);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        # syscall_events

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN approval_request_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_syscall_events_approval_id ON syscall_events(approval_request_id);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        _set_version(9)

        current = 9


    # ---- Migration v10: syscall_events span_id linkage ----

    if current < 10:

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN span_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_syscall_events_span_id ON syscall_events(span_id);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE jobs ADD COLUMN lock_owner TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_lock_until ON jobs(lock_until);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE skill_executions ADD COLUMN error_code TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_exec_error_code ON agent_executions(error_code);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_exec_error_code ON skill_executions(error_code);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

            except Exception as e:

                logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)


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

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        # encrypted api key columns (keep legacy api_key for backward compatibility)

        try:

            conn.execute("ALTER TABLE adapters ADD COLUMN api_key_enc TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE adapters ADD COLUMN api_key_kid TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        _set_version(27)

        current = 27


    # ---- Migration v28: prompt_templates (prompt platformization MVP) ----

    if current < 28:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS prompt_templates (

                  template_id TEXT PRIMARY KEY,

                  name TEXT NOT NULL,

                  template TEXT NOT NULL,

                  version TEXT NOT NULL,

                  metadata_json TEXT,

                  created_at REAL NOT NULL,

                  updated_at REAL NOT NULL

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_templates_updated ON prompt_templates(updated_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS prompt_template_versions (

                  id TEXT PRIMARY KEY,

                  template_id TEXT NOT NULL,

                  version TEXT NOT NULL,

                  template TEXT NOT NULL,

                  metadata_json TEXT,

                  created_at REAL NOT NULL

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_template_versions_tid ON prompt_template_versions(template_id);")

            conn.execute(

                "CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_template_versions_unique ON prompt_template_versions(template_id, version);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        _set_version(28)

        current = 28


    # ---- Migration v29: tenant_id columns for executions/syscalls (platformization PR-01) ----

    if current < 29:

        for stmt in [

            "ALTER TABLE agent_executions ADD COLUMN tenant_id TEXT;",

            "ALTER TABLE skill_executions ADD COLUMN tenant_id TEXT;",

            "ALTER TABLE syscall_events ADD COLUMN tenant_id TEXT;",

        ]:

            try:

                conn.execute(stmt)

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_agent_exec_tenant_time ON agent_executions(tenant_id, start_time DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_skill_exec_tenant_time ON skill_executions(tenant_id, start_time DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_syscall_events_tenant_time ON syscall_events(tenant_id, start_time DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(29)

        current = 29


    # ---- Migration v30: session_locks + session_queue (PR-04 session lane) ----

    if current < 30:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS session_locks (

                  tenant_id TEXT,

                  session_id TEXT NOT NULL,

                  run_id TEXT NOT NULL,

                  acquired_at REAL NOT NULL,

                  expires_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, session_id)

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_session_locks_exp ON session_locks(expires_at);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS session_queue (

                  id INTEGER PRIMARY KEY AUTOINCREMENT,

                  tenant_id TEXT,

                  session_id TEXT NOT NULL,

                  run_id TEXT NOT NULL,

                  kind TEXT NOT NULL,

                  target_id TEXT NOT NULL,

                  user_id TEXT,

                  queue_mode TEXT,

                  status TEXT NOT NULL,

                  payload_json TEXT,

                  created_at REAL NOT NULL,

                  UNIQUE(run_id)

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_session_queue_sess_time ON session_queue(tenant_id, session_id, created_at ASC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_session_queue_status_time ON session_queue(status, created_at ASC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(30)

        current = 30


    # ---- Migration v31: approval_requests tenant/actor/run columns (PR-08 approval hub) ----

    if current < 31:

        try:

            conn.execute("ALTER TABLE approval_requests ADD COLUMN tenant_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE approval_requests ADD COLUMN actor_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE approval_requests ADD COLUMN actor_role TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE approval_requests ADD COLUMN session_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE approval_requests ADD COLUMN run_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_tenant_time ON approval_requests(tenant_id, created_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_run_id ON approval_requests(run_id);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(31)

        current = 31


    # ---- Migration v32: enterprise memory fields + pins/blocks (PR-09) ----

    if current < 32:

        # memory_sessions: tenant_id

        try:

            conn.execute("ALTER TABLE memory_sessions ADD COLUMN tenant_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_sess_tenant_time ON memory_sessions(tenant_id, updated_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        # memory_messages: tenant_id + sensitivity + source_run_id

        try:

            conn.execute("ALTER TABLE memory_messages ADD COLUMN tenant_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE memory_messages ADD COLUMN sensitivity TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE memory_messages ADD COLUMN source_run_id TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_mem_msg_tenant_sess_time ON memory_messages(tenant_id, session_id, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_msg_source_run ON memory_messages(source_run_id);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        # memory_pins: allow pinning important messages (tenant-scoped)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS memory_pins (

                  tenant_id TEXT,

                  session_id TEXT NOT NULL,

                  message_id TEXT NOT NULL,

                  created_by TEXT,

                  note TEXT,

                  created_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, message_id)

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_pins_sess_time ON memory_pins(tenant_id, session_id, created_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        # memory_blocks: allow blocking patterns for injection/PII safety (tenant-scoped)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS memory_blocks (

                  id TEXT PRIMARY KEY,

                  tenant_id TEXT,

                  session_id TEXT,

                  pattern TEXT NOT NULL,

                  reason TEXT,

                  created_by TEXT,

                  created_at REAL NOT NULL

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_blocks_tenant_time ON memory_blocks(tenant_id, created_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)


        _set_version(32)

        current = 32


    # ---- Migration v33: release rollouts + metrics snapshots (PR-10) ----

    if current < 33:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS release_rollouts (

                  tenant_id TEXT,

                  target_type TEXT NOT NULL,

                  target_id TEXT NOT NULL,

                  candidate_id TEXT NOT NULL,

                  mode TEXT NOT NULL,              -- all|percentage

                  percentage INTEGER,             -- 0-100 (for percentage mode)

                  include_actor_ids_json TEXT,

                  exclude_actor_ids_json TEXT,

                  enabled INTEGER NOT NULL DEFAULT 1,

                  metadata_json TEXT,

                  created_at REAL NOT NULL,

                  updated_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, target_type, target_id)

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_release_rollouts_candidate ON release_rollouts(candidate_id);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_release_rollouts_tenant_time ON release_rollouts(tenant_id, updated_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS release_metrics_snapshots (

                  id TEXT PRIMARY KEY,

                  tenant_id TEXT,

                  candidate_id TEXT NOT NULL,

                  metric_key TEXT NOT NULL,

                  value REAL NOT NULL,

                  window_start REAL,

                  window_end REAL,

                  metadata_json TEXT,

                  created_at REAL NOT NULL

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_release_metrics_candidate_time ON release_metrics_snapshots(candidate_id, created_at DESC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_release_metrics_tenant_time ON release_metrics_snapshots(tenant_id, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(33)

        current = 33


    # ---- Migration v34: plugins + plugin runs (PR-11) ----

    if current < 34:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS plugins (

                  tenant_id TEXT,

                  plugin_id TEXT NOT NULL,

                  name TEXT,

                  version TEXT,

                  enabled INTEGER NOT NULL DEFAULT 0,

                  manifest_json TEXT,

                  metadata_json TEXT,

                  created_at REAL NOT NULL,

                  updated_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, plugin_id)

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_plugins_tenant_time ON plugins(tenant_id, updated_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS plugin_runs (

                  run_id TEXT PRIMARY KEY,

                  tenant_id TEXT,

                  plugin_id TEXT NOT NULL,

                  status TEXT NOT NULL, -- queued|running|completed|failed|waiting_approval

                  trace_id TEXT,

                  approval_request_id TEXT,

                  input_json TEXT,

                  output_json TEXT,

                  error TEXT,

                  created_at REAL NOT NULL,

                  updated_at REAL NOT NULL

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_plugin_runs_tenant_time ON plugin_runs(tenant_id, created_at DESC);")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_plugin_runs_plugin_time ON plugin_runs(plugin_id, created_at DESC);")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_plugin_runs_approval ON plugin_runs(approval_request_id);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(34)

        current = 34


    # ---- Migration v35: tenant quotas + usage ledger (PR-12) ----

    if current < 35:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS tenant_quotas (

                  tenant_id TEXT PRIMARY KEY,

                  version INTEGER NOT NULL,

                  quota_json TEXT,

                  updated_at REAL NOT NULL

                );

                """

            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_quotas_updated ON tenant_quotas(updated_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS tenant_usage_ledger (

                  tenant_id TEXT,

                  day TEXT NOT NULL,           -- YYYY-MM-DD (UTC)

                  metric_key TEXT NOT NULL,    -- tool_calls|llm_total_tokens|runs_started|external_access

                  value REAL NOT NULL,

                  updated_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, day, metric_key)

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_usage_tenant_day ON tenant_usage_ledger(tenant_id, day DESC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_usage_metric_day ON tenant_usage_ledger(metric_key, day DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(35)

        current = 35


    # ---- Migration v36: connector delivery attempts + DLQ (PR-12 connectors) ----

    if current < 36:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS connector_delivery_attempts (

                  id TEXT PRIMARY KEY,

                  connector TEXT NOT NULL,     -- slack|feishu|teams|webhook

                  tenant_id TEXT,

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

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_cda_tenant_time ON connector_delivery_attempts(tenant_id, created_at DESC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_cda_run_time ON connector_delivery_attempts(run_id, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS connector_delivery_dlq (

                  id TEXT PRIMARY KEY,

                  connector TEXT NOT NULL,

                  tenant_id TEXT,

                  run_id TEXT,

                  url TEXT,

                  payload_json TEXT,

                  attempts INTEGER NOT NULL,

                  error TEXT,

                  status TEXT NOT NULL,        -- pending|resolved

                  created_at REAL NOT NULL,

                  resolved_at REAL

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_cdlq_status_time ON connector_delivery_dlq(status, created_at DESC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_cdlq_tenant_time ON connector_delivery_dlq(tenant_id, created_at DESC);"

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_cdlq_run_time ON connector_delivery_dlq(run_id, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(36)

        current = 36


    # ---- Migration v37: plugin versions (P0 plugins standardization) ----

    if current < 37:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS plugin_versions (

                  tenant_id TEXT,

                  plugin_id TEXT NOT NULL,

                  version TEXT NOT NULL,

                  manifest_json TEXT,

                  metadata_json TEXT,

                  created_at REAL NOT NULL,

                  PRIMARY KEY(tenant_id, plugin_id, version)

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_plugin_versions_tenant_plugin_time ON plugin_versions(tenant_id, plugin_id, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(37)

        current = 37


    # ---- Migration v38: onboarding evidence runs (P0 onboarding wizard) ----

    if current < 38:

        try:

            conn.execute(

                """

                CREATE TABLE IF NOT EXISTS onboarding_evidence (

                  id TEXT PRIMARY KEY,

                  tenant_id TEXT,

                  step_key TEXT NOT NULL,

                  action TEXT NOT NULL,

                  status TEXT NOT NULL,

                  input_json TEXT,

                  output_json TEXT,

                  links_json TEXT,

                  approval_request_id TEXT,

                  created_at REAL NOT NULL

                );

                """

            )

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_onboarding_evidence_tenant_step_time ON onboarding_evidence(tenant_id, step_key, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(38)

        current = 38


    # ---- Migration v39: audit_logs add change_id ----

    if current < 39:

        try:

            conn.execute("ALTER TABLE audit_logs ADD COLUMN change_id TEXT;")

        except Exception as e:

            # already exists / legacy db without audit_logs

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_change ON audit_logs(change_id, created_at DESC);")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(39)

        current = 39


    # ---- Migration v40: syscall_events composite indexes for observability queries ----

    if current < 40:

        # Many observability endpoints filter by kind+name+time window, and often by tenant_id.

        # These composite indexes significantly reduce scan cost for routing_explain/strict_eval/metrics.

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_syscall_events_kind_name_time "

                "ON syscall_events(kind, name, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_syscall_events_tenant_kind_name_time "

                "ON syscall_events(tenant_id, kind, name, created_at DESC);"

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(40)

        current = 40


    # ---- Migration v41: skill eval suites/runs/results (skill-creator style eval loop) ----

    if current < 41:

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS skill_eval_suites (

              suite_id TEXT PRIMARY KEY,

              tenant_id TEXT,

              scope TEXT,

              target_skill_id TEXT,

              name TEXT,

              description TEXT,

              config_json TEXT,

              created_at REAL NOT NULL,

              updated_at REAL NOT NULL

            );

            """

        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_eval_suites_tenant_time ON skill_eval_suites(tenant_id, updated_at DESC);")

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS skill_eval_runs (

              run_id TEXT PRIMARY KEY,

              suite_id TEXT NOT NULL,

              tenant_id TEXT,

              mode TEXT,

              status TEXT,

              metrics_json TEXT,

              error TEXT,

              created_at REAL NOT NULL,

              updated_at REAL NOT NULL

            );

            """

        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_eval_runs_suite_time ON skill_eval_runs(suite_id, updated_at DESC);")

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS skill_eval_results (

              id TEXT PRIMARY KEY,

              run_id TEXT NOT NULL,

              query_index INTEGER,

              query_text TEXT,

              expected TEXT,

              selected_kind TEXT,

              selected_skill_id TEXT,

              selected_score REAL,

              candidates_json TEXT,

              ok INTEGER,

              created_at REAL NOT NULL

            );

            """

        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_eval_results_run ON skill_eval_results(run_id, query_index);")

        _set_version(41)

        current = 41


    # ---- Migration v42: entropy ledger (production readiness §10) ----

    if current < 42:

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS entropy_ledger (

              id TEXT PRIMARY KEY,

              project_id TEXT,

              agent_id TEXT,

              drift_type TEXT NOT NULL,

              severity TEXT DEFAULT 'warning',

              description TEXT,

              detected_at REAL NOT NULL,

              resolved_at REAL,

              drift_count INTEGER DEFAULT 1,

              source_file TEXT,

              source_line INTEGER

            );

            """

        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_entropy_project ON entropy_ledger(project_id, detected_at DESC);")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_entropy_agent ON entropy_ledger(agent_id, detected_at DESC);")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_entropy_unresolved ON entropy_ledger(project_id) WHERE resolved_at IS NULL;")

        _set_version(42)

        current = 42


    # ---- Migration v43: prompt app templates + test cases + eval runs ----

    if current < 43:

        conn.executescript("""

            CREATE TABLE IF NOT EXISTS prompt_app_templates (

                id              TEXT PRIMARY KEY,

                name            TEXT NOT NULL,

                category        TEXT NOT NULL DEFAULT '',

                tags            TEXT DEFAULT '[]',

                system_prompt   TEXT NOT NULL DEFAULT '',

                user_prompt     TEXT NOT NULL DEFAULT '',

                assistant_prompt TEXT NOT NULL DEFAULT '',

                variables       TEXT DEFAULT '[]',

                version         TEXT NOT NULL DEFAULT '1.0.0',

                status          TEXT NOT NULL DEFAULT 'draft',

                metadata_json   TEXT DEFAULT '{}',

                created_at      REAL NOT NULL,

                updated_at      REAL NOT NULL

            );

            CREATE INDEX IF NOT EXISTS idx_prompt_app_cat ON prompt_app_templates(category);


            CREATE TABLE IF NOT EXISTS prompt_app_categories (

                name            TEXT PRIMARY KEY,

                display_order   INTEGER DEFAULT 0,

                icon            TEXT DEFAULT '',

                parent          TEXT DEFAULT '',

                created_at      REAL NOT NULL

            );


            CREATE TABLE IF NOT EXISTS prompt_test_cases (

                id              TEXT PRIMARY KEY,

                template_id     TEXT NOT NULL,

                name            TEXT NOT NULL DEFAULT '',

                variables       TEXT NOT NULL DEFAULT '{}',

                expected_keys   TEXT DEFAULT '',

                created_at      REAL NOT NULL,

                FOREIGN KEY (template_id) REFERENCES prompt_app_templates(id)

            );

            CREATE INDEX IF NOT EXISTS idx_prompt_tc_tid ON prompt_test_cases(template_id);


            CREATE TABLE IF NOT EXISTS prompt_eval_runs (

                id              TEXT PRIMARY KEY,

                template_id     TEXT NOT NULL,

                version_a       TEXT NOT NULL,

                version_b       TEXT NOT NULL,

                model           TEXT NOT NULL DEFAULT 'deepseek-chat',

                status          TEXT NOT NULL DEFAULT 'pending',

                total_cases     INTEGER DEFAULT 0,

                a_wins          INTEGER DEFAULT 0,

                b_wins          INTEGER DEFAULT 0,

                draws           INTEGER DEFAULT 0,

                avg_score_a     REAL DEFAULT 0.0,

                avg_score_b     REAL DEFAULT 0.0,

                results_json    TEXT DEFAULT '[]',

                created_at      REAL NOT NULL,

                finished_at     REAL

            );

            CREATE INDEX IF NOT EXISTS idx_prompt_er_tid ON prompt_eval_runs(template_id);

        """)

        _set_version(43)

        current = 43


    # ---- Migration v44: prompt app instances ----

    if current < 44:

        conn.executescript("""

            CREATE TABLE IF NOT EXISTS prompt_app_instances (

                id                  TEXT PRIMARY KEY,

                name                TEXT NOT NULL,

                source_template_id  TEXT NOT NULL,

                system_prompt       TEXT DEFAULT '',

                user_prompt         TEXT DEFAULT '',

                assistant_prompt    TEXT DEFAULT '',

                variables           TEXT DEFAULT '[]',

                status              TEXT DEFAULT 'draft',

                created_at          REAL NOT NULL,

                updated_at          REAL NOT NULL

            );

            CREATE INDEX IF NOT EXISTS idx_prompt_app_instances_tid ON prompt_app_instances(source_template_id);

        """)

        _set_version(44)

        current = 44


    # ---- Migration v45: add examples + constraints to app templates ----

    if current < 45:

        try:

            conn.execute("ALTER TABLE prompt_app_templates ADD COLUMN examples TEXT DEFAULT '';")

        except sqlite3.OperationalError:

            pass  # column already exists

        try:

            conn.execute("ALTER TABLE prompt_app_templates ADD COLUMN constraints TEXT DEFAULT '';")

        except sqlite3.OperationalError:

            pass

        _set_version(45)

        current = 45


    # ---- Migration v46: scenario tags ----

    if current < 46:

        conn.executescript("""

            CREATE TABLE IF NOT EXISTS prompt_scenario_tags (

                name         TEXT PRIMARY KEY,

                category     TEXT NOT NULL DEFAULT "",

                parent       TEXT DEFAULT "",

                display_order INTEGER DEFAULT 0,

                created_at   REAL NOT NULL

            );

            ALTER TABLE prompt_app_templates ADD COLUMN scenario_tags TEXT DEFAULT '[]';

        """)

        _set_version(46)

        current = 46


    # ---- Migration v47: syscall_events token & cost tracking ----

    if current < 47:

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN input_tokens INTEGER DEFAULT 0;")

        except sqlite3.OperationalError:

            pass

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN output_tokens INTEGER DEFAULT 0;")

        except sqlite3.OperationalError:

            pass

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN cost REAL DEFAULT 0.0;")

        except sqlite3.OperationalError:

            pass

        conn.execute(

            "CREATE INDEX IF NOT EXISTS idx_syscall_events_tokens ON syscall_events(kind, input_tokens, output_tokens);"

        )

        _set_version(47)

        current = 47


    # ---- Migration v48: syscall_events parent_span_id linkage ----

    if current < 48:

        try:

            conn.execute("ALTER TABLE syscall_events ADD COLUMN parent_span_id TEXT;")

        except sqlite3.OperationalError:

            pass

        try:

            conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_syscall_events_parent_span ON syscall_events(parent_span_id);"

            )

        except sqlite3.OperationalError:

            pass

        _set_version(48)

        current = 48


    # ---- Migration v49: import_audits table ----

    if current < 49:

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS import_audits (

              id INTEGER PRIMARY KEY AUTOINCREMENT,

              skill_id TEXT NOT NULL,

              skill_name TEXT,

              source_type TEXT,

              pattern TEXT,

              adapted INTEGER DEFAULT 0,

              lint_errors INTEGER DEFAULT 0,

              lint_warnings INTEGER DEFAULT 0,

              details_json TEXT,

              created_at REAL NOT NULL

            );

            """

        )

        conn.execute(

            "CREATE INDEX IF NOT EXISTS idx_import_audits_skill ON import_audits(skill_id, created_at DESC);"

        )

        _set_version(49)

        current = 49


    # ---- Migration v50: memory relevance_decay + updated_at ----

    if current < 50:

        try:

            conn.execute("ALTER TABLE long_term_memories ADD COLUMN updated_at REAL NOT NULL DEFAULT 0;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE long_term_memories ADD COLUMN relevance_decay REAL NOT NULL DEFAULT 1.0;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(50)

        current = 50


    # ---- Migration v51: audit_logs tamper-evidence (hash chain) ----

    if current < 51:

        try:

            conn.execute("ALTER TABLE audit_logs ADD COLUMN entry_hash TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        try:

            conn.execute("ALTER TABLE audit_logs ADD COLUMN prev_hash TEXT;")

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        _set_version(51)

        current = 51


    # If legacy db exists with tables but without meta, upgrade meta to current

    if current < target_version:

        _set_version(target_version)


    # Ensure idempotency indexes exist (even when schema_version already current)

    try:

        conn.execute(

            "CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_runs_resume_unique "

            "ON graph_runs(parent_run_id, resumed_from_checkpoint_id) "

            "WHERE resumed_from_checkpoint_id IS NOT NULL;"

        )

    except Exception as e:

        logging.debug(str(e), exc_info=True)


    return current
