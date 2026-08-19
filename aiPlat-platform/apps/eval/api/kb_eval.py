"""
KB Evaluation API router — golden dataset CRUD + evaluation execution.
"""
from __future__ import annotations

import json as _json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from apps.common_schemas import StatusResponse, ListResponse, ItemResponse

router = APIRouter(prefix="/kb-eval", tags=["kb-eval"])


def _db_path() -> str:
    base = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    return os.path.join(base, "default", "kb.sqlite3")


def _connect():
    path = _db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Golden Dataset CRUD ──

@router.get("/samples", response_model=ItemResponse)
async def list_samples(limit: int = 100, offset: int = 0, tag: Optional[str] = None):
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)
        if tag:
            rows = conn.execute("SELECT * FROM kb_eval_samples WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                               (f'%"{tag}"%', limit, offset)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM kb_eval_samples ORDER BY created_at DESC LIMIT ? OFFSET ?",
                               (limit, offset)).fetchall()
        items = []
        for r in rows:
            items.append({
                "id": r["id"], "question": r["question"], "ground_truth": r["ground_truth"],
                "doc_ids": _json.loads(r["doc_ids"] or "[]"), "tags": _json.loads(r["tags"] or "[]"),
            })
        total = conn.execute("SELECT count(*) FROM kb_eval_samples").fetchone()[0]
        return {"items": items, "total": total}
    finally:
        conn.close()


@router.post("/samples", response_model=StatusResponse)
async def create_sample(body: Dict[str, Any]):
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)
        sid = body.get("id") or f"evs_{int(time.time())}"
        conn.execute("INSERT OR REPLACE INTO kb_eval_samples VALUES(?,?,?,?,?,?)",
                    (sid, str(body.get("question", "")), str(body.get("ground_truth", "")),
                     _json.dumps(body.get("doc_ids", [])), _json.dumps(body.get("tags", [])), time.time()))
        conn.commit()
        return {"id": sid, "status": "created"}
    finally:
        conn.close()


@router.delete("/samples/{sample_id}", response_model=StatusResponse)
async def delete_sample(sample_id: str):
    conn = _connect()
    try:
        conn.execute("DELETE FROM kb_eval_samples WHERE id=?", (sample_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


# ── Evaluation Execution ──

@router.post("/run", response_model=StatusResponse)
async def run_evaluation(body: Dict[str, Any]):
    sample_ids = body.get("sample_ids") or []
    tag = body.get("tag")

    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        from core.api.core_facade import get_rag_evaluator  # P0-A2 修复: CoreFacade 已补 re-export
        from core.api.core_facade import EvalSample  # P0-A2 修复: CoreFacade 已补 re-export
        _ensure_eval_schema(conn)

        if tag:
            rows = conn.execute("SELECT * FROM kb_eval_samples WHERE tags LIKE ? ORDER BY created_at", (f'%"{tag}"%',)).fetchall()
        elif sample_ids:
            placeholders = ",".join(["?"] * len(sample_ids))
            rows = conn.execute(f"SELECT * FROM kb_eval_samples WHERE id IN ({placeholders})", sample_ids).fetchall()
        else:
            rows = conn.execute("SELECT * FROM kb_eval_samples ORDER BY created_at DESC LIMIT 20").fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="no_samples_found")

        samples = []
        for r in rows:
            samples.append(EvalSample(
                id=r["id"], question=r["question"], ground_truth=r["ground_truth"],
                doc_ids=_json.loads(r["doc_ids"] or "[]"), tags=_json.loads(r["tags"] or "[]"),
            ))

        evaluator = get_rag_evaluator()
        reports = await evaluator.evaluate_batch(samples)

        # Persist reports
        now = time.time()
        for rp in reports:
            conn.execute("INSERT OR IGNORE INTO kb_eval_reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rp.sample_id, rp.question, rp.answer, _json.dumps(rp.contexts, ensure_ascii=False),
                         rp.ground_truth, rp.metrics.faithfulness, rp.metrics.answer_relevancy,
                         rp.metrics.context_precision, rp.metrics.context_recall,
                         rp.failure_type, rp.duration_ms, now))
        conn.commit()

        # Summary
        if reports:
            avg = {
                "faithfulness": round(sum(r.metrics.faithfulness for r in reports) / len(reports), 3),
                "answer_relevancy": round(sum(r.metrics.answer_relevancy for r in reports) / len(reports), 3),
                "context_precision": round(sum(r.metrics.context_precision for r in reports) / len(reports), 3),
                "context_recall": round(sum(r.metrics.context_recall for r in reports) / len(reports), 3),
            }
            failure_counts = {}
            for r in reports:
                failure_counts[r.failure_type] = failure_counts.get(r.failure_type, 0) + 1
            return {"samples": len(samples), "reports": len(reports), "avg_metrics": avg, "failure_distribution": failure_counts}

        return {"samples": len(samples), "reports": 0}
    finally:
        conn.close()


@router.get("/reports", response_model=ItemResponse)
async def list_reports(limit: int = 50, offset: int = 0):
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)
        rows = conn.execute("SELECT * FROM kb_eval_reports ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        items = []
        for r in rows:
            items.append({
                "sample_id": r["sample_id"], "question": r["question"], "answer": r["answer"][:300],
                "faithfulness": r["faithfulness"], "answer_relevancy": r["answer_relevancy"],
                "context_precision": r["context_precision"], "context_recall": r["context_recall"],
                "failure_type": r["failure_type"], "duration_ms": r["duration_ms"],
            })
        total = conn.execute("SELECT count(*) FROM kb_eval_reports").fetchone()[0]
        return {"items": items, "total": total}
    finally:
        conn.close()


# ── Bulk Import ──

@router.post("/samples/import", response_model=StatusResponse)
async def import_samples_csv(file: UploadFile = File(...)):
    """Import evaluation samples from CSV (columns: question,ground_truth,doc_ids,tags)."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    lines = text.strip().split("\n")
    if len(lines) < 2:
        raise HTTPException(status_code=400, detail="CSV must have header + at least 1 row")

    header = [h.strip().lower() for h in lines[0].split(",")]
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)
        imported = 0
        now = time.time()
        for i, line in enumerate(lines[1:]):
            cols = [c.strip() for c in line.split(",")]
            if len(cols) < 2:
                continue
            row = {header[j]: cols[j] if j < len(cols) else "" for j in range(len(header))}
            sid = f"evs_{int(now)}_{i}"
            question = row.get("question", "")
            ground_truth = row.get("ground_truth", "")
            doc_ids = [d.strip() for d in row.get("doc_ids", "").split(";") if d.strip()]
            tags = [t.strip() for t in row.get("tags", "").split(";") if t.strip()]
            conn.execute("INSERT OR IGNORE INTO kb_eval_samples VALUES(?,?,?,?,?,?)",
                        (sid, question, ground_truth, _json.dumps(doc_ids), _json.dumps(tags), now))
            imported += 1
        conn.commit()
        return {"imported": imported, "total_lines": len(lines) - 1}
    finally:
        conn.close()


# ── Time-series aggregation ──

@router.get("/reports/series", response_model=ItemResponse)
async def reports_time_series(days: int = 30):
    """Aggregate evaluation reports into daily buckets for time-series charts."""
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)
        cutoff = time.time() - days * 86400
        rows = conn.execute("""
            SELECT
              date(created_at, 'unixepoch') as day,
              ROUND(AVG(faithfulness), 3) as avg_faithfulness,
              ROUND(AVG(answer_relevancy), 3) as avg_answer_relevancy,
              ROUND(AVG(context_precision), 3) as avg_context_precision,
              ROUND(AVG(context_recall), 3) as avg_context_recall,
              COUNT(*) as sample_count,
              SUM(CASE WHEN failure_type != 'ok' THEN 1 ELSE 0 END) as failure_count
            FROM kb_eval_reports
            WHERE created_at > ?
            GROUP BY day ORDER BY day ASC
        """, (cutoff,)).fetchall()

        series = {
            "days": [], "faithfulness": [], "answer_relevancy": [],
            "context_precision": [], "context_recall": [],
            "sample_counts": [], "failure_counts": [],
        }
        for r in rows:
            series["days"].append(r["day"])
            series["faithfulness"].append(r["avg_faithfulness"])
            series["answer_relevancy"].append(r["avg_answer_relevancy"])
            series["context_precision"].append(r["avg_context_precision"])
            series["context_recall"].append(r["avg_context_recall"])
            series["sample_counts"].append(r["sample_count"])
            series["failure_counts"].append(r["failure_count"])
        return series
    finally:
        conn.close()


# ── Regression comparison ──

@router.get("/reports/compare", response_model=ItemResponse)
async def compare_reports(session_a: str = "", session_b: str = ""):
    """Compare two evaluation sessions (by day) side-by-side."""
    conn = _connect()
    try:
        from core.api.core_facade import _ensure_eval_schema
        _ensure_eval_schema(conn)

        def _avg_for_day(day: str) -> dict:
            cutoff = time.time() - 365 * 86400
            rows = conn.execute("""
                SELECT AVG(faithfulness) as f, AVG(answer_relevancy) as ar,
                       AVG(context_precision) as cp, AVG(context_recall) as cr, COUNT(*) as n
                FROM kb_eval_reports WHERE date(created_at, 'unixepoch') = ? AND created_at > ?
            """, (day, cutoff)).fetchone()
            if rows and rows["n"] > 0:
                return {k: round(float(rows[k] or 0), 3) for k in ("f", "ar", "cp", "cr")}
            return {"f": 0, "ar": 0, "cp": 0, "cr": 0}

        # If no days specified, use last two distinct evaluation days
        if not session_a or not session_b:
            days_row = conn.execute("""
                SELECT DISTINCT date(created_at, 'unixepoch') as d
                FROM kb_eval_reports ORDER BY d DESC LIMIT 2
            """).fetchall()
            days = [r["d"] for r in days_row]
            session_a = days[0] if len(days) > 0 else ""
            session_b = days[1] if len(days) > 1 else ""

        return {
            "session_a": session_a, "session_b": session_b,
            "metrics_a": _avg_for_day(session_a) if session_a else {},
            "metrics_b": _avg_for_day(session_b) if session_b else {},
        }
    finally:
        conn.close()
