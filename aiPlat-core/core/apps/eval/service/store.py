"""EVAL_V1 E2 — EvalStore (SQLite) for charter §5.3 entities.

Canonical persistence for eval_sets / tasks / runs / judgments / labels /
reports / judges / gates. Does not replace code-review-gold JSONL yet;
migration helpers import gold YAML into sets+tasks.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

STORE_SCHEMA_VERSION = "eval.store.v0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def default_db_path(*, tenant_id: str = "") -> Path:
    from core.utils.paths import get_aiplat_data_dir

    tid = (tenant_id or "").strip() or "default"
    root = Path(get_aiplat_data_dir(f"eval/tenants/{tid}"))
    root.mkdir(parents=True, exist_ok=True)
    override = (os.getenv("AIPLAT_EVAL_STORE_DB") or "").strip()
    if override:
        p = Path(override).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return root / "eval_store.v0.sqlite3"


def _dumps(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False)


def _loads(raw: Any, default: Any = None) -> Any:
    if raw is None or raw == "":
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return {} if default is None else default


_SCHEMA_SQL = """
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
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class EvalStore:
    """SQLite-backed EVAL_V1 store (tenant-scoped file)."""

    def __init__(self, db_path: Optional[Path | str] = None, *, tenant_id: str = ""):
        self.db_path = Path(db_path) if db_path else default_db_path(tenant_id=tenant_id)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO eval_store_meta(key, value) VALUES (?, ?)",
                ("schema_version", STORE_SCHEMA_VERSION),
            )
            conn.commit()

    def health(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        with self._connect() as conn:
            for table in (
                "eval_sets",
                "eval_tasks",
                "eval_runs",
                "eval_judgments",
                "eval_labels",
                "eval_reports",
                "eval_judges",
                "eval_gates",
            ):
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            ver = conn.execute(
                "SELECT value FROM eval_store_meta WHERE key='schema_version'"
            ).fetchone()
        return {
            "ok": True,
            "schema_version": (ver["value"] if ver else STORE_SCHEMA_VERSION),
            "db_path": str(self.db_path),
            "counts": counts,
        }

    # ── sets ──────────────────────────────────────────────

    def create_set(
        self,
        *,
        name: str,
        version: str = "0",
        split: str = "dev",
        meta: Optional[Dict[str, Any]] = None,
        set_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = set_id or _new_id("set")
        now = _now()
        meta = meta or {}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO eval_sets(id, name, version, split, meta_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, name, version, split, _dumps(meta), now, now),
            )
            conn.commit()
        return self.get_set(sid) or {"id": sid}

    def get_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_sets WHERE id=?", (set_id,)).fetchone()
        return self._row_set(row) if row else None

    def list_sets(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM eval_sets ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [self._row_set(r) for r in rows]

    @staticmethod
    def _row_set(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "version": row["version"],
            "split": row["split"],
            "meta": _loads(row["meta_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ── tasks ─────────────────────────────────────────────

    def create_task(
        self,
        *,
        set_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        expected: Optional[Dict[str, Any]] = None,
        rubric: Optional[Dict[str, Any]] = None,
        tags: Optional[Sequence[str]] = None,
        hard_negative: bool = False,
        source: str = "",
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tid = task_id or _new_id("task")
        now = _now()
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM eval_sets WHERE id=?", (set_id,)).fetchone():
                raise ValueError(f"unknown set_id: {set_id}")
            conn.execute(
                "INSERT INTO eval_tasks(id, set_id, input_json, expected_json, rubric_json, "
                "tags_json, hard_negative, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tid,
                    set_id,
                    _dumps(input_data or {}),
                    _dumps(expected or {}),
                    _dumps(rubric or {}),
                    _dumps(list(tags or [])),
                    1 if hard_negative else 0,
                    source or "",
                    now,
                ),
            )
            conn.commit()
        return self.get_task(tid) or {"id": tid}

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_tasks WHERE id=?", (task_id,)).fetchone()
        return self._row_task(row) if row else None

    def list_tasks(self, *, set_id: str = "", limit: int = 500) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), 5000))
        with self._connect() as conn:
            if set_id:
                rows = conn.execute(
                    "SELECT * FROM eval_tasks WHERE set_id=? ORDER BY created_at LIMIT ?",
                    (set_id, lim),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM eval_tasks ORDER BY created_at LIMIT ?", (lim,)
                ).fetchall()
        return [self._row_task(r) for r in rows]

    @staticmethod
    def _row_task(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "set_id": row["set_id"],
            "input": _loads(row["input_json"]),
            "expected": _loads(row["expected_json"]),
            "rubric": _loads(row["rubric_json"]),
            "tags": _loads(row["tags_json"], []),
            "hard_negative": bool(row["hard_negative"]),
            "source": row["source"],
            "created_at": row["created_at"],
        }

    # ── runs / judgments / labels (minimal write) ─────────

    def create_run(
        self,
        *,
        task_id: str,
        target_kind: str = "skill",
        target_ref: str = "",
        model: str = "",
        params: Optional[Dict[str, Any]] = None,
        status: str = "pending",
        versions: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rid = run_id or _new_id("run")
        now = _now()
        versions = versions or {}
        # Charter: dataset / judge / prompt / model / code commit
        for key in ("dataset", "judge", "prompt", "model", "code_commit"):
            versions.setdefault(key, "")
        if model and not versions.get("model"):
            versions["model"] = model
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM eval_tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError(f"unknown task_id: {task_id}")
            conn.execute(
                "INSERT INTO eval_runs(id, task_id, target_kind, target_ref, model, params_json, "
                "trace_json, status, versions_json, created_at) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)",
                (
                    rid,
                    task_id,
                    target_kind,
                    target_ref,
                    model,
                    _dumps(params or {}),
                    status,
                    _dumps(versions),
                    now,
                ),
            )
            conn.commit()
        return self.get_run(rid) or {"id": rid}

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "target_kind": row["target_kind"],
            "target_ref": row["target_ref"],
            "model": row["model"],
            "params": _loads(row["params_json"]),
            "trace": _loads(row["trace_json"]),
            "status": row["status"],
            "versions": _loads(row["versions_json"]),
            "created_at": row["created_at"],
        }

    def create_label(
        self,
        *,
        task_id: str,
        annotator: str,
        label: Optional[Dict[str, Any]] = None,
        rationale: str = "",
        adjudicated: bool = False,
        label_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lid = label_id or _new_id("label")
        now = _now()
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM eval_tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError(f"unknown task_id: {task_id}")
            conn.execute(
                "INSERT INTO eval_labels(id, task_id, annotator, label_json, rationale, "
                "adjudicated, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    lid,
                    task_id,
                    annotator,
                    _dumps(label or {}),
                    rationale or "",
                    1 if adjudicated else 0,
                    now,
                ),
            )
            conn.commit()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_labels WHERE id=?", (lid,)).fetchone()
        assert row is not None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "annotator": row["annotator"],
            "label": _loads(row["label_json"]),
            "rationale": row["rationale"],
            "adjudicated": bool(row["adjudicated"]),
            "created_at": row["created_at"],
        }


def get_eval_store(*, tenant_id: str = "", db_path: Optional[str] = None) -> EvalStore:
    return EvalStore(db_path=db_path, tenant_id=tenant_id)


def import_code_review_gold(
    *,
    gold_dir: Optional[str] = None,
    tenant_id: str = "",
    set_name: str = "code-review-gold",
    set_version: str = "v0-seed",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Migrate code-review-gold YAML/JSON cases into eval_sets + eval_tasks.

    Does not delete JSONL reports; additive import with stable task ids
    ``crg:{case_id}`` so re-runs are idempotent (INSERT OR REPLACE via delete+insert).
    """
    import yaml  # type: ignore

    from core.harness.evaluation.code_review_gold import default_gold_dir

    root = Path(gold_dir).expanduser() if gold_dir else default_gold_dir(tenant_id)
    if not root.is_dir():
        # Fall back to workspace seeds for offline/local engineering
        seed = Path(__file__).resolve().parents[4] / "workspace_seeds" / "eval" / "code_review_gold"
        if seed.is_dir():
            root = seed
        else:
            raise FileNotFoundError(f"gold_dir not found: {root}")

    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    set_id = f"set_crg_{(tenant_id or 'default').strip() or 'default'}"
    existing = store.get_set(set_id)
    if not existing:
        store.create_set(
            name=set_name,
            version=set_version,
            split="gold",
            meta={
                "source": "code_review_gold",
                "gold_dir": str(root),
                "schema_version": STORE_SCHEMA_VERSION,
            },
            set_id=set_id,
        )
    else:
        # bump updated_at via recreate meta touch
        with store._connect() as conn:
            conn.execute(
                "UPDATE eval_sets SET version=?, updated_at=?, meta_json=? WHERE id=?",
                (
                    set_version,
                    _now(),
                    _dumps(
                        {
                            **(existing.get("meta") or {}),
                            "source": "code_review_gold",
                            "gold_dir": str(root),
                            "schema_version": STORE_SCHEMA_VERSION,
                        }
                    ),
                    set_id,
                ),
            )
            conn.commit()

    imported = 0
    skipped = 0
    files = sorted(
        list(root.glob("*.yaml"))
        + list(root.glob("*.yml"))
        + list(root.glob("*.json"))
    )
    for path in files:
        if path.name.upper().startswith("README"):
            skipped += 1
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            case = yaml.safe_load(raw) if path.suffix in {".yaml", ".yml"} else json.loads(raw)
        except Exception:
            skipped += 1
            continue
        if not isinstance(case, dict):
            skipped += 1
            continue
        # batch files may nest cases
        cases = case.get("cases") if isinstance(case.get("cases"), list) else [case]
        for c in cases:
            if not isinstance(c, dict):
                skipped += 1
                continue
            cid = str(c.get("id") or path.stem).strip()
            if not cid:
                skipped += 1
                continue
            task_id = f"crg:{cid}"
            with store._connect() as conn:
                conn.execute("DELETE FROM eval_tasks WHERE id=?", (task_id,))
                conn.commit()
            store.create_task(
                set_id=set_id,
                task_id=task_id,
                input_data={
                    "description": c.get("description"),
                    "profile": c.get("profile"),
                    "line_window": c.get("line_window"),
                    "predicted": c.get("predicted"),
                },
                expected={"gold_findings": c.get("gold_findings") or []},
                rubric={"kind": "code_review_gold", "match": "file_line_severity"},
                tags=["code-review-gold", str(c.get("profile") or "balanced")],
                hard_negative=bool(c.get("hard_negative")),
                source=str(path),
            )
            imported += 1

    return {
        "ok": True,
        "set_id": set_id,
        "gold_dir": str(root),
        "imported": imported,
        "skipped": skipped,
        "store": store.health(),
    }
