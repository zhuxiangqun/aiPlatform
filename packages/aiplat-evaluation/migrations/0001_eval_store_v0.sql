-- EVAL A3-local A2 — standalone eval store schema (eval.store.v0)
-- Mirrors core EvalStore charter entities; no Central/FDE/Ontology tables.
-- process_split_authorized remains false.

CREATE TABLE IF NOT EXISTS eval_sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '0',
    split TEXT NOT NULL DEFAULT 'dev',
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_tasks (
    id TEXT PRIMARY KEY,
    set_id TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    expected_json TEXT NOT NULL DEFAULT '{}',
    rubric_json TEXT NOT NULL DEFAULT '{}',
    tags_json TEXT NOT NULL DEFAULT '[]',
    hard_negative INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(set_id) REFERENCES eval_sets(id)
);
CREATE INDEX IF NOT EXISTS idx_eval_tasks_set ON eval_tasks(set_id);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    target_kind TEXT NOT NULL DEFAULT 'skill',
    target_ref TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '{}',
    trace_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    versions_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES eval_tasks(id)
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_task ON eval_runs(task_id);

CREATE TABLE IF NOT EXISTS eval_judgments (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    judge_id TEXT NOT NULL DEFAULT '',
    score REAL,
    pass INTEGER,
    reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES eval_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_eval_judgments_run ON eval_judgments(run_id);

CREATE TABLE IF NOT EXISTS eval_labels (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    annotator TEXT NOT NULL DEFAULT '',
    label_json TEXT NOT NULL DEFAULT '{}',
    rationale TEXT NOT NULL DEFAULT '',
    adjudicated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES eval_tasks(id)
);
CREATE INDEX IF NOT EXISTS idx_eval_labels_task ON eval_labels(task_id);

CREATE TABLE IF NOT EXISTS eval_reports (
    id TEXT PRIMARY KEY,
    run_ids_json TEXT NOT NULL DEFAULT '[]',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    slices_json TEXT NOT NULL DEFAULT '{}',
    failures_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_judges (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    calibration_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_gates (
    id TEXT PRIMARY KEY,
    baseline TEXT NOT NULL DEFAULT '',
    candidate TEXT NOT NULL DEFAULT '',
    thresholds_json TEXT NOT NULL DEFAULT '{}',
    decision TEXT NOT NULL DEFAULT 'pending',
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
