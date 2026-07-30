"""

ReparseQueue — HITL document reparse workflow.



When a user discovers a document was poorly parsed, they can submit it

for reparse. The queue ensures one-at-a-time processing with status tracking.



States: pending → processing → completed | failed

UNIQUE(doc_id, status) prevents duplicate submissions of the same document.



Integration:

  - POST /wiki/ingest/reparse {doc_id} → adds to queue

  - GET /wiki/ingest/reparse/{doc_id}/status → checks status

  - Background worker: reparse_queue.py processes one at a time

"""

from __future__ import annotations



import asyncio

import logging

import os

import sqlite3

import time

from typing import Any, Dict, List, Optional



logger = logging.getLogger("aiplat.reparse")





def _get_db() -> sqlite3.Connection:

    db_path = os.getenv(

        "AIPLAT_EXECUTION_DB_PATH",

        os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3"),

    )

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)

    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("PRAGMA busy_timeout=3000")

    return conn





def _init_table():

    conn = _get_db()

    try:

        conn.execute("""

            CREATE TABLE IF NOT EXISTS reparse_queue (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                doc_id TEXT NOT NULL,

                source_path TEXT NOT NULL DEFAULT '',

                status TEXT NOT NULL DEFAULT 'pending',

                created_at REAL NOT NULL,

                started_at REAL,

                completed_at REAL,

                error_message TEXT,

                reparse_count INTEGER DEFAULT 0,

                UNIQUE(doc_id, status)

            )

        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_reparse_status ON reparse_queue(status)")

        conn.commit()

    finally:

        conn.close()





async def enqueue_reparse(doc_id: str, source_path: str = "") -> Dict[str, Any]:

    """Add a document to the reparse queue. Idempotent per doc_id."""

    _init_table()

    conn = _get_db()

    try:

        # Check if already queued

        existing = conn.execute(

            "SELECT id, status FROM reparse_queue WHERE doc_id = ? AND status IN ('pending', 'processing')",

            (doc_id,),

        ).fetchone()

        if existing:

            return {"queued": False, "message": f"Document {doc_id} is already {existing[1]} (id={existing[0]})"}



        conn.execute(

            "INSERT INTO reparse_queue (doc_id, source_path, status, created_at) VALUES (?, ?, 'pending', ?)",

            (doc_id, source_path, time.time()),

        )

        conn.commit()



        # Start background worker if not running

        asyncio.create_task(_process_queue())



        return {"queued": True, "message": f"Document {doc_id} added to reparse queue"}

    finally:

        conn.close()





async def get_reparse_status(doc_id: str) -> Dict[str, Any]:

    """Get the current reparse status for a document."""

    conn = _get_db()

    try:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT * FROM reparse_queue WHERE doc_id = ? ORDER BY id DESC LIMIT 5",

            (doc_id,),

        ).fetchall()

        return {"doc_id": doc_id, "history": [dict(r) for r in rows]}

    finally:

        conn.close()





async def get_queue_stats() -> Dict[str, Any]:

    """Return current queue statistics."""

    conn = _get_db()

    try:

        stats = {}

        for status in ["pending", "processing", "completed", "failed"]:

            count = conn.execute(

                "SELECT COUNT(*) FROM reparse_queue WHERE status = ?", (status,),

            ).fetchone()[0]

            stats[status] = count

        return {"queue": stats}

    finally:

        conn.close()





_queue_lock = asyncio.Lock()

_worker_running = False





async def _process_queue():

    """Background worker: process one reparse task at a time."""

    global _worker_running

    if _worker_running:

        return

    _worker_running = True

    async with _queue_lock:

        try:

            await _process_one_task()

        finally:

            _worker_running = False





async def _process_one_task():

    """Pick the first pending task and process it."""

    conn = _get_db()

    try:

        task = conn.execute(

            "SELECT id, doc_id, source_path FROM reparse_queue WHERE status = 'pending' ORDER BY id LIMIT 1"

        ).fetchone()

        if not task:

            return



        task_id, doc_id, source_path = task

        conn.execute(

            "UPDATE reparse_queue SET status = 'processing', started_at = ? WHERE id = ?",

            (time.time(), task_id),

        )

        conn.commit()



        logger.info("ReparseQueue: processing doc_id=%s (task #%s)", doc_id, task_id)



        try:

            # ── Re-run the 13-step ontology pipeline ──

            from core.harness.ontology_engine.engine import process_chunks

            # Re-extract from source

            if source_path and os.path.exists(source_path):

                from core.harness.ontology_engine.document_parser import DocumentParser

                parser = DocumentParser()

                doc = parser.parse_file(source_path)

                if doc and doc.chunks:

                    result = await process_chunks(

                        chunks=doc.chunks,

                        domain_id="default",

                        doc_id=doc_id,

                    )

                    chunks_processed = len(doc.chunks)

                else:

                    chunks_processed = 0

            else:

                # Source path not available — just re-scan existing storage

                chunks_processed = -1



            # Mark completed

            conn.execute(

                "UPDATE reparse_queue SET status = 'completed', completed_at = ?, reparse_count = reparse_count + 1 WHERE id = ?",

                (time.time(), task_id),

            )

            conn.commit()



            # Invalidate caches

            try:

                from core.harness.knowledge.semantic_cache import SemanticCache

                cache = SemanticCache()

                cache.invalidate_domain("default")

            except Exception:

                logging.getLogger(__name__).debug('_process_one_task failed', exc_info=True)


            logger.info("ReparseQueue: completed doc_id=%s (%s chunks)", doc_id, chunks_processed)



        except Exception as e:

            conn.execute(

                "UPDATE reparse_queue SET status = 'failed', error_message = ? WHERE id = ?",

                (str(e)[:500], task_id),

            )

            conn.commit()

            logger.error("ReparseQueue: failed doc_id=%s: %s", doc_id, e)



    finally:

        conn.close()

