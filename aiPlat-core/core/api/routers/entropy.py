"""
Entropy Auditing API — production readiness §10.
Track technical debt accumulation across projects and agents.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/entropy", tags=["entropy"])


class EntropyRecord(BaseModel):
    project_id: str = ""
    agent_id: str = ""
    drift_type: str
    severity: str = "warning"
    description: str = ""
    source_file: str = ""
    source_line: int = 0


@router.get("/ledger")
async def list_entropy(
    project_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    from core.services.execution_store import get_execution_store
    store = get_execution_store()
    await store.init()
    db_path = store._config.db_path
    import sqlite3, json as _json

    def _sync():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            where = ["1=1"]
            params = []
            if project_id:
                where.append("project_id=?")
                params.append(project_id)
            if agent_id:
                where.append("agent_id=?")
                params.append(agent_id)
            if resolved is True:
                where.append("resolved_at IS NOT NULL")
            elif resolved is False:
                where.append("resolved_at IS NULL")

            sql = f"SELECT * FROM entropy_ledger WHERE {' AND '.join(where)} ORDER BY detected_at DESC LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
            rows = conn.execute(sql, params).fetchall()
            items = []
            for r in rows:
                items.append({
                    "id": r["id"], "project_id": r["project_id"], "agent_id": r["agent_id"],
                    "drift_type": r["drift_type"], "severity": r["severity"],
                    "description": r["description"], "detected_at": r["detected_at"],
                    "resolved_at": r["resolved_at"], "drift_count": r["drift_count"],
                    "source_file": r["source_file"], "source_line": r["source_line"],
                })
            total = conn.execute(f"SELECT COUNT(*) FROM entropy_ledger WHERE {' AND '.join(where)}", params[:-2]).fetchone()[0]
            return {"items": items, "total": total}
        finally:
            conn.close()
    return await _sync()


@router.get("/summary")
async def entropy_summary(project_id: str = ""):
    from core.services.execution_store import get_execution_store
    store = get_execution_store()
    await store.init()
    db_path = store._config.db_path
    import sqlite3

    def _sync():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            where = "WHERE project_id=?" if project_id else ""
            params = (project_id,) if project_id else ()

            total = conn.execute(f"SELECT COUNT(*) as n FROM entropy_ledger {where}", params).fetchone()["n"]
            unresolved = conn.execute(f"SELECT COUNT(*) as n FROM entropy_ledger {where} AND resolved_at IS NULL".replace("WHERE AND", "WHERE"), params).fetchone()["n"]

            by_type = conn.execute(f"SELECT drift_type, COUNT(*) as n FROM entropy_ledger {where} WHERE resolved_at IS NULL GROUP BY drift_type ORDER BY n DESC".replace("WHERE WHERE", "WHERE") if project_id else "SELECT drift_type, COUNT(*) as n FROM entropy_ledger WHERE resolved_at IS NULL GROUP BY drift_type ORDER BY n DESC", params).fetchall()

            by_severity = conn.execute(f"SELECT severity, COUNT(*) as n FROM entropy_ledger {where} WHERE resolved_at IS NULL GROUP BY severity ORDER BY n DESC".replace("WHERE WHERE", "WHERE") if project_id else "SELECT severity, COUNT(*) as n FROM entropy_ledger WHERE resolved_at IS NULL GROUP BY severity ORDER BY n DESC", params).fetchall()

            return {
                "total": total,
                "unresolved": unresolved,
                "by_type": [{"type": r["drift_type"], "count": r["n"]} for r in by_type],
                "by_severity": [{"severity": r["severity"], "count": r["n"]} for r in by_severity],
            }
        finally:
            conn.close()
    return await _sync()


@router.post("/record")
async def record_entropy(body: EntropyRecord):
    import uuid, time
    from core.services.execution_store import get_execution_store
    store = get_execution_store()
    await store.init()
    db_path = store._config.db_path
    import sqlite3

    def _sync():
        conn = sqlite3.connect(db_path)
        try:
            eid = f"ent_{uuid.uuid4().hex[:12]}"
            now = time.time()
            conn.execute(
                "INSERT INTO entropy_ledger VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (eid, body.project_id, body.agent_id, body.drift_type, body.severity,
                 body.description, now, None, 1, body.source_file, body.source_line),
            )
            conn.commit()
            return {"id": eid, "status": "recorded"}
        finally:
            conn.close()
    return await _sync()


@router.post("/resolve/{entry_id}")
async def resolve_entropy(entry_id: str):
    import time
    from core.services.execution_store import get_execution_store
    store = get_execution_store()
    await store.init()
    db_path = store._config.db_path
    import sqlite3

    def _sync():
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("UPDATE entropy_ledger SET resolved_at=? WHERE id=?", (time.time(), entry_id))
            conn.commit()
            return {"id": entry_id, "status": "resolved"}
        finally:
            conn.close()
    return await _sync()
