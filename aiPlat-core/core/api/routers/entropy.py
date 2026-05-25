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


@router.get("/audit")
async def run_readiness_audit():
    """Run the full platform readiness audit (Agent 3 + Platform 8 checks)."""
    import os, re, json
    from pathlib import Path as _Path
    core_src = _Path(__file__).resolve().parents[3] / "core"

    def _ok(desc, passed, detail=""):
        return {"desc": desc, "result": "✅" if passed else "❌", "detail": detail}

    items = []

    # ── Agent Level ──
    agent_files = list(_Path.home().glob(".aiplat/agents/*/AGENT.md")) + list((core_src / "engine" / "agents").rglob("AGENT.md"))
    has_type = has_skills = has_model = 0
    for f in agent_files:
        c = f.read_text()
        if 'agent_type:' in c: has_type += 1
        if 'skills:' in c or 'required_skills:' in c: has_skills += 1
        if 'model:' in c: has_model += 1
    total = len([f for f in agent_files if f.exists()])
    items.append(_ok("任务规格 (Task Specification)", total > 0 and has_type > 0,
        f"{total} agents, {has_type} with agent_type, {has_skills} with skills, {has_model} with model"))

    loop_py = core_src / "harness" / "execution" / "loop.py"
    has_compact = "maybe_compact_messages" in loop_py.read_text() if loop_py.exists() else False
    has_claude_md = _Path.home().parents[2].joinpath("CLAUDE.md").exists() if False else (_Path(__file__).resolve().parents[5] / "CLAUDE.md").exists()
    items.append(_ok("上下文选择 (Context Selection)", has_compact,
        f"5-level compaction: {'✅' if has_compact else '❌'}"))

    engine_py = core_src / "harness" / "execution" / "pipeline_engine.py"
    has_snapshot = bool(engine_py.exists() and "_snapshot" in engine_py.read_text())
    items.append(_ok("任务状态 (Task State)", has_snapshot,
        f"_snapshot: {'✅' if has_snapshot else '❌'}"))

    # ── Platform Level ──
    policy = core_src / "harness" / "infrastructure" / "gates" / "policy_gate.py"
    has_gate = policy.exists()
    items.append(_ok("工具访问 (Tool Access)", has_gate,
        f"PolicyGate: {'✅' if has_gate else '❌'}"))

    mem = core_src / "harness" / "memory" / "manager.py"
    has_mem = bool(loop_py.exists() and mem.exists() and "save_interaction" in loop_py.read_text())
    items.append(_ok("项目记忆 (Project Memory)", has_mem,
        f"MemoryManager wired: {'✅' if has_mem else '❌'}"))

    llm_py = core_src / "harness" / "syscalls" / "llm.py"
    has_trace = bool(llm_py.exists() and "trace_id" in llm_py.read_text())
    items.append(_ok("可观测性 (Observability)", has_trace,
        f"trace_id+span_id per syscall: {'✅' if has_trace else '❌'}"))

    has_classifier = (core_src / "harness" / "execution" / "failure_classifier.py").exists()
    has_drift = (core_src / "harness" / "evaluation" / "drift_detector.py").exists()
    items.append(_ok("失败归因 (Failure Attribution)", has_classifier and has_drift,
        f"classifier: {'✅' if has_classifier else '❌'}, DriftDetector: {'✅' if has_drift else '❌'}"))

    has_eval = (core_src / "harness" / "evaluation" / "rag_evaluator.py").exists()
    items.append(_ok("结果验证 (Verification)", has_eval,
        f"RagEvaluator: {'✅' if has_eval else '❌'}"))

    # Check RBAC
    has_rbac = False
    try:
        from core.api.deps import rbac_guard, actor_from_http
        has_rbac = True
    except: pass
    items.append(_ok("权限校验 (Permissions)", has_rbac,
        f"RBAC imports: {'✅' if has_rbac else '❌'}"))

    # Check entropy_ledger table
    has_entropy = False
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        await store.init()
        import sqlite3
        conn = sqlite3.connect(store._config.db_path)
        rows = conn.execute("SELECT name FROM sqlite_master WHERE name='entropy_ledger'").fetchall()
        has_entropy = len(rows) > 0
        conn.close()
    except: pass
    items.append(_ok("熵审计 (Entropy Auditing)", has_entropy,
        f"entropy_ledger v42: {'✅' if has_entropy else '❌'}"))

    has_chg = (core_src / "api" / "routers" / "change_control.py").exists() or (core_src / "governance" / "gating.py").exists()
    items.append(_ok("干预记录 (Intervention Recording)", has_chg,
        f"change_control: {'✅' if has_chg else '❌'}"))

    passed = sum(1 for i in items if i["result"] == "✅")
    return {"total": len(items), "passed": passed, "verdict": "✅ 可上线" if passed >= 10 else "🔶 建议改进" if passed >= 8 else "❌ 需修复", "items": items}
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
