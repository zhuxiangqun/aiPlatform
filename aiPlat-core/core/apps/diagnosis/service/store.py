"""DIAGNOSIS_V1 C1 — tenant-scoped SQLite store for Case / Evidence / Report."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_SCHEMA_VERSION = "diagnosis.store.v0"
SCENARIOS = frozenset({"run_failure", "version_regression"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def default_db_path(*, tenant_id: str = "") -> Path:
    from core.utils.paths import get_aiplat_data_dir

    tid = (tenant_id or "").strip() or "default"
    root = Path(get_aiplat_data_dir(f"diagnosis/tenants/{tid}"))
    root.mkdir(parents=True, exist_ok=True)
    override = (os.getenv("AIPLAT_DIAGNOSIS_STORE_DB") or "").strip()
    if override:
        p = Path(override).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return root / "diagnosis_store.v0.sqlite3"


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
CREATE TABLE IF NOT EXISTS diagnosis_cases (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    scenario TEXT NOT NULL,
    status TEXT NOT NULL,
    subject_ref TEXT NOT NULL DEFAULT '',
    baseline_ref TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dx_cases_tenant ON diagnosis_cases(tenant_id);

CREATE TABLE IF NOT EXISTS diagnosis_evidence (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES diagnosis_cases(id)
);
CREATE INDEX IF NOT EXISTS idx_dx_ev_case ON diagnosis_evidence(case_id);

CREATE TABLE IF NOT EXISTS diagnosis_reports (
    case_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL DEFAULT '{}',
    findings_json TEXT NOT NULL DEFAULT '[]',
    hypotheses_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES diagnosis_cases(id)
);
"""


class DiagnosisStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA_SQL)

    def health(self, *, tenant_id: str = "") -> Dict[str, Any]:
        tid = (tenant_id or "").strip()
        with self._conn() as conn:
            if tid:
                n = conn.execute(
                    "SELECT COUNT(*) AS c FROM diagnosis_cases WHERE tenant_id=?",
                    (tid,),
                ).fetchone()["c"]
            else:
                n = conn.execute("SELECT COUNT(*) AS c FROM diagnosis_cases").fetchone()["c"]
        return {
            "ok": True,
            "status": "ok",
            "product_id": "diagnosis",
            "capability_id": "diagnosis",
            "deploy_unit": "central",
            "schema_version": STORE_SCHEMA_VERSION,
            "case_count": int(n),
            "accuracy_claim": False,
            "auto_execute": False,
            "process_split_authorized": False,
        }

    def create_case(
        self,
        *,
        scenario: str,
        subject_ref: str,
        tenant_id: str = "",
        baseline_ref: Optional[str] = None,
        case_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sc = (scenario or "").strip()
        if sc not in SCENARIOS:
            raise ValueError("invalid_scenario")
        subj = (subject_ref or "").strip()
        if not subj:
            raise ValueError("missing_subject")
        cid = (case_id or "").strip() or _new_id("dxc")
        now = _now()
        tid = (tenant_id or "").strip()
        row = {
            "id": cid,
            "scenario": sc,
            "status": "open",
            "subject_ref": subj,
            "baseline_ref": baseline_ref,
            "created_at": now,
            "tenant_id": tid,
        }
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO diagnosis_cases"
                "(id,tenant_id,scenario,status,subject_ref,baseline_ref,meta_json,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    tid,
                    sc,
                    "open",
                    subj,
                    baseline_ref,
                    _dumps(meta or {}),
                    now,
                    now,
                ),
            )
        return row

    def list_cases(self, *, tenant_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        tid = (tenant_id or "").strip()
        lim = max(1, min(int(limit), 1000))
        with self._conn() as conn:
            if tid:
                rows = conn.execute(
                    "SELECT * FROM diagnosis_cases WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                    (tid, lim),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM diagnosis_cases ORDER BY created_at DESC LIMIT ?",
                    (lim,),
                ).fetchall()
        return [self._case_from_row(r) for r in rows]

    def get_case(self, case_id: str, *, tenant_id: str = "") -> Optional[Dict[str, Any]]:
        tid = (tenant_id or "").strip()
        with self._conn() as conn:
            if tid:
                row = conn.execute(
                    "SELECT * FROM diagnosis_cases WHERE id=? AND tenant_id=?",
                    (case_id, tid),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM diagnosis_cases WHERE id=?",
                    (case_id,),
                ).fetchone()
        return self._case_from_row(row) if row else None

    def set_status(self, case_id: str, status: str, *, tenant_id: str = "") -> None:
        case = self.get_case(case_id, tenant_id=tenant_id)
        if not case:
            raise KeyError("case_not_found")
        with self._conn() as conn:
            conn.execute(
                "UPDATE diagnosis_cases SET status=?, updated_at=? WHERE id=?",
                (status, _now(), case_id),
            )

    def replace_evidence(
        self,
        case_id: str,
        evidence: List[Dict[str, Any]],
        *,
        tenant_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        case = self.get_case(case_id, tenant_id=tenant_id)
        if not case:
            raise KeyError("case_not_found")
        tid = (tenant_id or "").strip()
        now = _now()
        body = {
            "schema_version": "diagnosis.evidence.v0",
            "case_id": case_id,
            "evidence": evidence,
            "payload": payload or {},
        }
        eid = _new_id("dxe")
        with self._conn() as conn:
            conn.execute("DELETE FROM diagnosis_evidence WHERE case_id=?", (case_id,))
            conn.execute(
                "INSERT INTO diagnosis_evidence(id,case_id,tenant_id,payload_json,created_at)"
                " VALUES (?,?,?,?,?)",
                (eid, case_id, tid, _dumps(body), now),
            )
            conn.execute(
                "UPDATE diagnosis_cases SET status=?, updated_at=? WHERE id=?",
                ("running", now, case_id),
            )
        return evidence

    def get_evidence_bundle(
        self, case_id: str, *, tenant_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        case = self.get_case(case_id, tenant_id=tenant_id)
        if not case:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload_json FROM diagnosis_evidence WHERE case_id=? ORDER BY created_at DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        if not row:
            return {"schema_version": "diagnosis.evidence.v0", "case_id": case_id, "evidence": [], "payload": {}}
        return _loads(row["payload_json"], {})

    def save_report(
        self,
        case_id: str,
        *,
        report: Dict[str, Any],
        findings: List[Dict[str, Any]],
        hypotheses: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        status: str,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        case = self.get_case(case_id, tenant_id=tenant_id)
        if not case:
            raise KeyError("case_not_found")
        tid = (tenant_id or "").strip()
        now = _now()
        report = dict(report)
        report["accuracy_claim"] = False
        report["case_id"] = case_id
        report.setdefault("schema_version", "diagnosis.report.v0")
        report["generated_at"] = now
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO diagnosis_reports"
                "(case_id,tenant_id,report_json,findings_json,hypotheses_json,recommendations_json,updated_at)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(case_id) DO UPDATE SET"
                " report_json=excluded.report_json,"
                " findings_json=excluded.findings_json,"
                " hypotheses_json=excluded.hypotheses_json,"
                " recommendations_json=excluded.recommendations_json,"
                " updated_at=excluded.updated_at",
                (
                    case_id,
                    tid,
                    _dumps(report),
                    _dumps(findings),
                    _dumps(hypotheses),
                    _dumps(recommendations),
                    now,
                ),
            )
            conn.execute(
                "UPDATE diagnosis_cases SET status=?, updated_at=? WHERE id=?",
                (status, now, case_id),
            )
        return report

    def get_report_bundle(
        self, case_id: str, *, tenant_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        case = self.get_case(case_id, tenant_id=tenant_id)
        if not case:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM diagnosis_reports WHERE case_id=?",
                (case_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "report": _loads(row["report_json"], {}),
            "findings": _loads(row["findings_json"], []),
            "hypotheses": _loads(row["hypotheses_json"], []),
            "recommendations": _loads(row["recommendations_json"], []),
        }

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "scenario": row["scenario"],
            "status": row["status"],
            "subject_ref": row["subject_ref"],
            "baseline_ref": row["baseline_ref"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "meta": _loads(row["meta_json"], {}),
        }


_STORE: Optional[DiagnosisStore] = None


def get_diagnosis_store(*, tenant_id: str = "") -> DiagnosisStore:
    global _STORE
    # Per-process singleton; path may vary by AIPLAT_DIAGNOSIS_STORE_DB for tests.
    override = (os.getenv("AIPLAT_DIAGNOSIS_STORE_DB") or "").strip()
    path = Path(override).expanduser() if override else default_db_path(tenant_id=tenant_id)
    if _STORE is None or Path(_STORE.db_path) != path:
        _STORE = DiagnosisStore(path)
    return _STORE
