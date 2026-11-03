"""KB eval sample/report ops — used by platform thin /kb-eval routes via CoreFacade.

Honesty: accuracy_claim stays caller-side; this module is storage + RagEvaluator glue.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


def _db_path() -> str:
    from core.utils.paths import get_aiplat_data_dir

    base = os.path.expanduser(
        os.getenv("AIPLAT_KB_TENANTS_DIR", get_aiplat_data_dir("kb/tenants"))
    )
    return os.path.join(base, "default", "kb.sqlite3")


def _connect() -> sqlite3.Connection:
    from core.harness.evaluation.rag_evaluator import _ensure_eval_schema

    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_eval_schema(conn)
    return conn


def kb_eval_list_samples(
    *,
    limit: int = 100,
    offset: int = 0,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    conn = _connect()
    try:
        if tag:
            rows = conn.execute(
                "SELECT * FROM kb_eval_samples WHERE tags LIKE ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (f'%"{tag}"%', limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kb_eval_samples ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "id": r["id"],
                    "question": r["question"],
                    "ground_truth": r["ground_truth"],
                    "doc_ids": json.loads(r["doc_ids"] or "[]"),
                    "tags": json.loads(r["tags"] or "[]"),
                }
            )
        total = conn.execute("SELECT count(*) FROM kb_eval_samples").fetchone()[0]
        return {"items": items, "total": total}
    finally:
        conn.close()


def kb_eval_create_sample(body: Dict[str, Any]) -> Dict[str, Any]:
    conn = _connect()
    try:
        sid = body.get("id") or f"evs_{int(time.time())}"
        conn.execute(
            "INSERT OR REPLACE INTO kb_eval_samples VALUES(?,?,?,?,?,?)",
            (
                sid,
                str(body.get("question", "")),
                str(body.get("ground_truth", "")),
                json.dumps(body.get("doc_ids", [])),
                json.dumps(body.get("tags", [])),
                time.time(),
            ),
        )
        conn.commit()
        return {"id": sid, "status": "created"}
    finally:
        conn.close()


def kb_eval_delete_sample(sample_id: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        conn.execute("DELETE FROM kb_eval_samples WHERE id=?", (sample_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


async def kb_eval_run(body: Dict[str, Any]) -> Dict[str, Any]:
    from core.harness.evaluation.rag_evaluator import EvalSample, get_rag_evaluator
    from core.harness.evaluation.eval_protocol import (
        attach_protocol as attach_eval_protocol,
        from_generic_eval as eval_protocol_from_generic,
    )

    sample_ids = body.get("sample_ids") or []
    tag = body.get("tag")
    conn = _connect()
    try:
        if tag:
            rows = conn.execute(
                "SELECT * FROM kb_eval_samples WHERE tags LIKE ? ORDER BY created_at",
                (f'%"{tag}"%',),
            ).fetchall()
        elif sample_ids:
            placeholders = ",".join(["?"] * len(sample_ids))
            rows = conn.execute(
                f"SELECT * FROM kb_eval_samples WHERE id IN ({placeholders})",
                sample_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kb_eval_samples ORDER BY created_at DESC LIMIT 20"
            ).fetchall()

        if not rows:
            raise LookupError("no_samples_found")

        samples: List[Any] = []
        for r in rows:
            samples.append(
                EvalSample(
                    id=r["id"],
                    question=r["question"],
                    ground_truth=r["ground_truth"],
                    doc_ids=json.loads(r["doc_ids"] or "[]"),
                    tags=json.loads(r["tags"] or "[]"),
                )
            )

        evaluator = get_rag_evaluator()
        reports = await evaluator.evaluate_batch(samples)

        now = time.time()
        for rp in reports:
            conn.execute(
                "INSERT OR IGNORE INTO kb_eval_reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rp.sample_id,
                    rp.question,
                    rp.answer,
                    json.dumps(rp.contexts, ensure_ascii=False),
                    rp.ground_truth,
                    rp.metrics.faithfulness,
                    rp.metrics.answer_relevancy,
                    rp.metrics.context_precision,
                    rp.metrics.context_recall,
                    rp.failure_type,
                    rp.duration_ms,
                    now,
                ),
            )
        conn.commit()

        if reports:
            avg = {
                "faithfulness": round(
                    sum(r.metrics.faithfulness for r in reports) / len(reports), 3
                ),
                "answer_relevancy": round(
                    sum(r.metrics.answer_relevancy for r in reports) / len(reports), 3
                ),
                "context_precision": round(
                    sum(r.metrics.context_precision for r in reports) / len(reports), 3
                ),
                "context_recall": round(
                    sum(r.metrics.context_recall for r in reports) / len(reports), 3
                ),
            }
            failure_counts: Dict[str, int] = {}
            for r in reports:
                failure_counts[r.failure_type] = failure_counts.get(r.failure_type, 0) + 1
            out = {
                "samples": len(samples),
                "reports": len(reports),
                "avg_metrics": avg,
                "failure_distribution": failure_counts,
                "status": "passed",
                "metrics": avg,
                "score": avg.get("faithfulness"),
            }
            return attach_eval_protocol(
                out,
                eval_protocol_from_generic(
                    task_id=f"kb-eval:{int(now)}",
                    target_kind="workflow",
                    target_ref="kb_eval",
                    result=out,
                    suite=str(tag or "kb"),
                ),
            )

        out = {"samples": len(samples), "reports": 0, "status": "skipped"}
        return attach_eval_protocol(
            out,
            eval_protocol_from_generic(
                task_id="kb-eval:empty",
                target_kind="workflow",
                target_ref="kb_eval",
                result=out,
                suite="kb",
            ),
        )
    finally:
        conn.close()


def kb_eval_list_reports(*, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM kb_eval_reports ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "sample_id": r["sample_id"],
                    "question": r["question"],
                    "answer": r["answer"][:300],
                    "faithfulness": r["faithfulness"],
                    "answer_relevancy": r["answer_relevancy"],
                    "context_precision": r["context_precision"],
                    "context_recall": r["context_recall"],
                    "failure_type": r["failure_type"],
                    "duration_ms": r["duration_ms"],
                }
            )
        total = conn.execute("SELECT count(*) FROM kb_eval_reports").fetchone()[0]
        return {"items": items, "total": total}
    finally:
        conn.close()


def kb_eval_import_csv_text(text: str) -> Dict[str, Any]:
    lines = text.strip().split("\n")
    if len(lines) < 2:
        raise ValueError("CSV must have header + at least 1 row")

    header = [h.strip().lower() for h in lines[0].split(",")]
    conn = _connect()
    try:
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
            conn.execute(
                "INSERT OR IGNORE INTO kb_eval_samples VALUES(?,?,?,?,?,?)",
                (sid, question, ground_truth, json.dumps(doc_ids), json.dumps(tags), now),
            )
            imported += 1
        conn.commit()
        return {"imported": imported, "total_lines": len(lines) - 1}
    finally:
        conn.close()


def kb_eval_reports_series(*, days: int = 30) -> Dict[str, Any]:
    conn = _connect()
    try:
        cutoff = time.time() - days * 86400
        rows = conn.execute(
            """
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
            """,
            (cutoff,),
        ).fetchall()

        series: Dict[str, List[Any]] = {
            "days": [],
            "faithfulness": [],
            "answer_relevancy": [],
            "context_precision": [],
            "context_recall": [],
            "sample_counts": [],
            "failure_counts": [],
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


def kb_eval_compare_reports(
    *,
    session_a: str = "",
    session_b: str = "",
) -> Dict[str, Any]:
    conn = _connect()
    try:

        def _avg_for_day(day: str) -> dict:
            cutoff = time.time() - 365 * 86400
            rows = conn.execute(
                """
                SELECT AVG(faithfulness) as f, AVG(answer_relevancy) as ar,
                       AVG(context_precision) as cp, AVG(context_recall) as cr, COUNT(*) as n
                FROM kb_eval_reports WHERE date(created_at, 'unixepoch') = ? AND created_at > ?
                """,
                (day, cutoff),
            ).fetchone()
            if rows and rows["n"] > 0:
                return {k: round(float(rows[k] or 0), 3) for k in ("f", "ar", "cp", "cr")}
            return {"f": 0, "ar": 0, "cp": 0, "cr": 0}

        sa, sb = session_a, session_b
        if not sa or not sb:
            days_row = conn.execute(
                """
                SELECT DISTINCT date(created_at, 'unixepoch') as d
                FROM kb_eval_reports ORDER BY d DESC LIMIT 2
                """
            ).fetchall()
            days = [r["d"] for r in days_row]
            sa = days[0] if len(days) > 0 else ""
            sb = days[1] if len(days) > 1 else ""

        return {
            "session_a": sa,
            "session_b": sb,
            "metrics_a": _avg_for_day(sa) if sa else {},
            "metrics_b": _avg_for_day(sb) if sb else {},
        }
    finally:
        conn.close()
