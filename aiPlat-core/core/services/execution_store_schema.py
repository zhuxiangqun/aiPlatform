"""
Execution Store DDL — all CREATE TABLE / CREATE INDEX / schema migration SQL.

Extracted from execution_store.py init() (per audit 1.8 structural debt split).
Referenced by ExecutionStore._run_migrations().

ARCHITECTURE (P0-A3 resolved 2026-08-18): core stores tenant_quotas; platform
api/routers/quota.py is the business API. Storage in core + business in platform
matches app→platform→core dependency rule. Not deprecated.
"""

from __future__ import annotations
import logging

PRAGMAS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA foreign_keys=ON;",
]

META_TABLES = [
    "CREATE TABLE IF NOT EXISTS aiplat_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);",
    "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);",
]

CORE_TABLES = [
    # ── Tenant ──
    """CREATE TABLE IF NOT EXISTS tenant_quotas (
      tenant_id TEXT PRIMARY KEY, version INTEGER, quota_json TEXT NOT NULL,
      updated_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_tenant_quotas_updated ON tenant_quotas(updated_at DESC);",
    """CREATE TABLE IF NOT EXISTS tenant_usage (
      tenant_id TEXT NOT NULL, metric_key TEXT NOT NULL, amount REAL,
      day TEXT NOT NULL, updated_at REAL NOT NULL,
      PRIMARY KEY (tenant_id, metric_key, day)
    );""",
    "CREATE INDEX IF NOT EXISTS idx_tenant_usage_day ON tenant_usage(day);",
    """CREATE TABLE IF NOT EXISTS tenant_policies (
      tenant_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL, version INTEGER,
      updated_at REAL NOT NULL
    );""",

    # ── Sessions ──
    """CREATE TABLE IF NOT EXISTS session_lock (
      tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
      acquired_at REAL NOT NULL, PRIMARY KEY (tenant_id, session_id)
    );""",
    """CREATE TABLE IF NOT EXISTS session_queue (
      tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
      enqueued_at REAL NOT NULL, PRIMARY KEY (tenant_id, run_id)
    );""",
    "CREATE INDEX IF NOT EXISTS idx_session_queue_time ON session_queue(enqueued_at);",

    # ── Runs ──
    """CREATE TABLE IF NOT EXISTS runs (
      run_id TEXT PRIMARY KEY, status TEXT, phase TEXT, iteration INTEGER DEFAULT 0,
      max_iterations INTEGER DEFAULT 100, tokens_used INTEGER DEFAULT 0,
      tokens_budget INTEGER DEFAULT 100000, error TEXT, output TEXT, metadata_json TEXT,
      parent_run_id TEXT, request_id TEXT, tenant_id TEXT, user_id TEXT,
      session_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
      started_at REAL, finished_at REAL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_runs_tenant ON runs(tenant_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_runs_request_id ON runs(request_id);",
    "CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(tenant_id, session_id);",

    # ── Run Events ──
    """CREATE TABLE IF NOT EXISTS run_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, seq INTEGER,
      event_type TEXT NOT NULL, trace_id TEXT, tenant_id TEXT, payload_json TEXT,
      created_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, seq);",
    "CREATE INDEX IF NOT EXISTS idx_run_events_type ON run_events(run_id, event_type);",

    # ── Learning Artifacts ──
    """CREATE TABLE IF NOT EXISTS learning_artifacts (
      artifact_id TEXT PRIMARY KEY, target_type TEXT, target_id TEXT,
      kind TEXT NOT NULL, version TEXT, status TEXT, payload TEXT,
      metadata_json TEXT, trace_id TEXT, run_id TEXT, tenant_id TEXT,
      created_at REAL NOT NULL, updated_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_learning_target ON learning_artifacts(target_type, target_id, kind);",
    "CREATE INDEX IF NOT EXISTS idx_learning_run ON learning_artifacts(run_id, created_at);",
]

SYS_TABLES = [
    # ── Syscall Events ──
    """CREATE TABLE IF NOT EXISTS syscall_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, span_id TEXT, parent_span_id TEXT,
      run_id TEXT, kind TEXT, name TEXT, status TEXT, target_type TEXT,
      target_id TEXT, tenant_id TEXT, user_id TEXT, session_id TEXT,
      start_time REAL, end_time REAL, duration_ms REAL, args_json TEXT,
      result_json TEXT, error TEXT, error_code TEXT, approval_request_id TEXT,
      created_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_syscall_trace ON syscall_events(trace_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_syscall_run ON syscall_events(run_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_syscall_kind_time ON syscall_events(kind, created_at);",
]

AUDIT_TABLES = [
    """CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, kind TEXT,
      status TEXT, tenant_id TEXT, actor_id TEXT, actor_role TEXT,
      resource_type TEXT, resource_id TEXT, detail_json TEXT,
      payload_json TEXT, created_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_logs(tenant_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action, created_at);",
]

CONNECTOR_TABLES = [
    """CREATE TABLE IF NOT EXISTS connector_delivery (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
      run_id TEXT, connector TEXT, attempt INTEGER DEFAULT 1,
      status TEXT, payload_json TEXT, result_json TEXT,
      error TEXT, created_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_conn_deliv_tenant ON connector_delivery(tenant_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_conn_deliv_run ON connector_delivery(run_id);",

    """CREATE TABLE IF NOT EXISTS connector_delivery_dlq (
      dlq_id TEXT PRIMARY KEY, tenant_id TEXT, run_id TEXT,
      connector TEXT, attempts INTEGER, last_error TEXT,
      payload_json TEXT, created_at REAL NOT NULL, resolved INTEGER DEFAULT 0
    );""",
    "CREATE INDEX IF NOT EXISTS idx_dlq_tenant ON connector_delivery_dlq(tenant_id, resolved);",
]

GRAPH_TABLES = [
    """CREATE TABLE IF NOT EXISTS graph_runs (
      run_id TEXT PRIMARY KEY, graph_name TEXT NOT NULL,
      status TEXT, start_time REAL NOT NULL, end_time REAL,
      duration_ms REAL, trace_id TEXT, initial_state_json TEXT,
      final_state_json TEXT, summary_json TEXT
    );""",
    """CREATE TABLE IF NOT EXISTS graph_checkpoints (
      checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
      step INTEGER NOT NULL, state_json TEXT NOT NULL,
      created_at REAL NOT NULL,
      FOREIGN KEY(run_id) REFERENCES graph_runs(run_id) ON DELETE CASCADE
    );""",
    "CREATE INDEX IF NOT EXISTS idx_graph_runs_name_time ON graph_runs(graph_name, start_time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_graph_cp_run ON graph_checkpoints(run_id, step);",
]

TRACE_TABLES = [
    """CREATE TABLE IF NOT EXISTS traces (
      trace_id TEXT PRIMARY KEY, name TEXT NOT NULL,
      status TEXT, start_time REAL NOT NULL, end_time REAL,
      duration_ms REAL, attributes_json TEXT
    );""",
    "CREATE INDEX IF NOT EXISTS idx_traces_time ON traces(start_time DESC);",

    """CREATE TABLE IF NOT EXISTS spans (
      span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, parent_span_id TEXT,
      name TEXT NOT NULL, status TEXT, start_time REAL NOT NULL,
      end_time REAL, duration_ms REAL, attributes_json TEXT,
      events_json TEXT,
      FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
    );""",
    "CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, start_time);",
]

# Tables present in init() but not yet migrated to schema module.
# These are covered by execute_schema() as best-effort CREATE IF NOT EXISTS.
REMAINING_TABLES = [
    "CREATE TABLE IF NOT EXISTS adapters (id TEXT PRIMARY KEY, name TEXT, provider TEXT, model TEXT, config_json TEXT, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS agent_executions (id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, status TEXT NOT NULL, input_json TEXT, output_json TEXT, error TEXT, start_time REAL, end_time REAL, duration_ms INTEGER, created_at REAL NOT NULL);",
    "CREATE TABLE IF NOT EXISTS approval_requests (request_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, operation TEXT NOT NULL, details TEXT, rule_id TEXT, rule_type TEXT, status TEXT NOT NULL, amount REAL, batch_size INTEGER, is_first_time INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL, metadata_json TEXT, result_json TEXT);",
    "CREATE TABLE IF NOT EXISTS gateway_pairings (pairing_id TEXT PRIMARY KEY, token_id TEXT, service_name TEXT, endpoint TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS gateway_tokens (token_id TEXT PRIMARY KEY, name TEXT, token_hash TEXT, scopes TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS global_settings (key TEXT PRIMARY KEY, value_json TEXT, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, type TEXT, status TEXT, schedule TEXT, config_json TEXT, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS job_runs (run_id TEXT PRIMARY KEY, job_id TEXT, status TEXT, started_at REAL, finished_at REAL, output_json TEXT, error TEXT);",
    "CREATE TABLE IF NOT EXISTS job_delivery_attempts (attempt_id TEXT PRIMARY KEY, job_run_id TEXT, connector TEXT, attempt INTEGER, status TEXT, payload_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS job_delivery_dlq (dlq_id TEXT PRIMARY KEY, job_run_id TEXT, connector TEXT, attempts INTEGER, last_error TEXT, payload_json TEXT, created_at REAL, resolved INTEGER DEFAULT 0);",
    "CREATE TABLE IF NOT EXISTS long_term_memories (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, key TEXT, content TEXT NOT NULL, metadata_json TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL DEFAULT 0, relevance_decay REAL NOT NULL DEFAULT 1.0);",
    "CREATE TABLE IF NOT EXISTS memory_blocks (block_id TEXT PRIMARY KEY, session_id TEXT, block_type TEXT, content TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS memory_messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, metadata_json TEXT, trace_id TEXT, run_id TEXT, created_at REAL NOT NULL, FOREIGN KEY(session_id) REFERENCES memory_sessions(id) ON DELETE CASCADE);",
    "CREATE TABLE IF NOT EXISTS memory_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, agent_type TEXT, session_type TEXT, status TEXT, metadata_json TEXT, message_count INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL);",
    "CREATE TABLE IF NOT EXISTS onboarding_evidence (evidence_id TEXT PRIMARY KEY, tenant_id TEXT, step TEXT, status TEXT, detail_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS package_versions (version_id TEXT PRIMARY KEY, package_id TEXT, version TEXT, manifest_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS package_installs (install_id TEXT PRIMARY KEY, package_id TEXT, version TEXT, target TEXT, status TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS plugins (plugin_id TEXT PRIMARY KEY, name TEXT, version TEXT, manifest_json TEXT, enabled INTEGER DEFAULT 1, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS plugin_versions (version_id TEXT PRIMARY KEY, plugin_id TEXT, version TEXT, config_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS plugin_runs (run_id TEXT PRIMARY KEY, plugin_id TEXT, action TEXT, status TEXT, input_json TEXT, output_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS prompt_templates (template_id TEXT PRIMARY KEY, name TEXT, version TEXT, content TEXT, metadata_json TEXT, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS prompt_template_versions (version_id TEXT PRIMARY KEY, template_id TEXT, version TEXT, content TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS release_metrics_snapshots (snapshot_id TEXT PRIMARY KEY, release_id TEXT, metric_name TEXT, metric_value REAL, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS release_rollouts (rollout_id TEXT PRIMARY KEY, release_id TEXT, channel TEXT, percentage REAL, status TEXT, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS request_dedup (request_id TEXT PRIMARY KEY, run_id TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_eval_suites (suite_id TEXT PRIMARY KEY, name TEXT, config_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_eval_runs (run_id TEXT PRIMARY KEY, suite_id TEXT, skill_id TEXT, status TEXT, results_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_eval_results (result_id TEXT PRIMARY KEY, run_id TEXT, suite_id TEXT, skill_id TEXT, metric_name TEXT, metric_value REAL, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_executions (id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, status TEXT NOT NULL, input_json TEXT, output_json TEXT, error TEXT, start_time REAL, end_time REAL, duration_ms INTEGER, user_id TEXT, created_at REAL NOT NULL);",
    "CREATE TABLE IF NOT EXISTS skill_packs (pack_id TEXT PRIMARY KEY, name TEXT, description TEXT, version TEXT, manifest_json TEXT, created_at REAL, updated_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_pack_versions (version_id TEXT PRIMARY KEY, pack_id TEXT, version TEXT, config_json TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS skill_pack_installs (install_id TEXT PRIMARY KEY, pack_id TEXT, version TEXT, target TEXT, status TEXT, created_at REAL);",
    "CREATE TABLE IF NOT EXISTS tenant_usage_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT, metric_key TEXT, amount REAL, day TEXT, run_id TEXT, created_at REAL);",
]

ALL_TABLES = (
    PRAGMAS
    + META_TABLES
    # All other tables are created by migration steps in execution_store.py:_init_sync().
    # Keeping their definitions here creates schema conflicts: execute_schema() creates
    # old-style tables first, then migration steps' CREATE TABLE IF NOT EXISTS are skipped,
    # but subsequent ALTER TABLE / CREATE INDEX steps reference columns that don't exist.
)


def execute_schema(conn):
    """Execute all DDL statements on a SQLite connection (idempotent)."""
    for sql in ALL_TABLES:
        try:
            conn.execute(sql)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    conn.commit()


__all__ = ["ALL_TABLES", "execute_schema"]
