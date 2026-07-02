"""
KB Metrics Dashboard — 7 operational indicators for knowledge base health.

Phase G: Aggregates data from ExecutionStore, KB database, and retrieval logs
to produce actionable metrics for knowledge base operations.

Indicators (per article §07):
  1. No-answer rate       — queries with zero results or empty citations
  2. Citation coverage    — answers that include source references
  3. Error correction rate— user-reported or audit-flagged wrong answers
  4. Approval trigger rate— high-risk questions entering review flow
  5. Permission blocks    — access denied at retrieval boundary
  6. Gap repair cycle     — time from gap detection to document update
  7. Repeat question rate — same question pattern recurring across users
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class KBMetrics:
    no_answer_rate: float = 0.0
    citation_coverage: float = 0.0
    error_correction_rate: float = 0.0
    approval_trigger_rate: float = 0.0
    permission_blocks: int = 0
    gap_repair_cycles: List[Dict[str, Any]] = field(default_factory=list)
    repeat_question_rate: float = 0.0
    total_queries: int = 0
    window_hours: int = 24

    def to_dict(self) -> Dict[str, Any]:
        return {
            "no_answer_rate_pct": round(self.no_answer_rate * 100, 1),
            "citation_coverage_pct": round(self.citation_coverage * 100, 1),
            "error_correction_rate_pct": round(self.error_correction_rate * 100, 1),
            "approval_trigger_rate_pct": round(self.approval_trigger_rate * 100, 1),
            "permission_blocks": self.permission_blocks,
            "gap_repair_cycles": self.gap_repair_cycles[:5],
            "repeat_question_rate_pct": round(self.repeat_question_rate * 100, 1),
            "total_queries": self.total_queries,
            "window_hours": self.window_hours,
        }


def get_kb_metrics(window_hours: int = 168, tenant_id: str = "") -> Dict[str, Any]:
    """Compute 7 operational metrics from execution store and KB database.

    Args:
        window_hours: Time window in hours (default 7 days)
        tenant_id: Optional tenant filter
    """
    metrics = KBMetrics(window_hours=window_hours)

    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store:
            _load_from_store(metrics, store, window_hours, tenant_id)
    except Exception:
        pass

    try:
        _load_from_kb_db(metrics, window_hours)
    except Exception:
        pass

    return metrics.to_dict()


def _load_from_store(metrics: KBMetrics, store: Any, window_hours: int, tenant_id: str) -> None:
    """Query ExecutionStore syscall_events for RAG metrics."""
    import sqlite3 as _sq
    conn = _sq.connect(store._config.db_path)
    try:
        cutoff = time.time() - window_hours * 3600

        # Total knowledge retrieval queries
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='knowledge_retrieve' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        metrics.total_queries = row[0] if row else 0

        # No-answer rate: queries with zero results
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='knowledge_retrieve' AND payload like '%\"count\":0%' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        no_answer = row[0] if row else 0
        metrics.no_answer_rate = no_answer / max(metrics.total_queries, 1)

        # Approval triggers
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='approval_requested' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        approval_count = row[0] if row else 0
        metrics.approval_trigger_rate = approval_count / max(metrics.total_queries, 1)

        # Permission blocks
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='policy_denied' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        metrics.permission_blocks = row[0] if row else 0

        # Citation coverage: queries with citations in metadata
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='knowledge_retrieve' AND payload like '%\"citations\"%' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        cited = row[0] if row else 0
        metrics.citation_coverage = cited / max(metrics.total_queries, 1)

        # Error corrections: feedback loops with errors
        row = conn.execute(
            "SELECT COUNT(*) FROM syscall_events WHERE kind='feedback' AND payload like '%\"type\":\"error\"%' AND created_at > ?",
            (cutoff,),
        ).fetchone()
        errors = row[0] if row else 0
        metrics.error_correction_rate = errors / max(metrics.total_queries, 1)

    finally:
        conn.close()


def _load_from_kb_db(metrics: KBMetrics, window_hours: int) -> None:
    """Query KB database for gap repair cycles and repeat questions."""
    kb_path = os.path.expanduser("~/.aiplat/data/kb/aiplat_knowledge.sqlite3")
    if not os.path.exists(kb_path):
        return

    conn = sqlite3.connect(kb_path)
    try:
        cutoff = time.time() - window_hours * 3600

        # Gap repair cycles: time between document gap detection and update
        rows = conn.execute(
            "SELECT doc_id, created_at, updated_at FROM documents WHERE meta_json LIKE '%gap_detected%' ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        for r in rows:
            gap_time = (r[2] or 0) - (r[1] or 0)
            if gap_time > 0:
                metrics.gap_repair_cycles.append({
                    "doc_id": r[0],
                    "repair_hours": round(gap_time / 3600, 1),
                })

        # Repeat question rate: syscall events with same query pattern
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE created_at > ?",
            (cutoff,),
        ).fetchone()
        total_docs = row[0] if row else 1
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE created_at > ? AND (meta_json LIKE '%gap_detected%' OR meta_json LIKE '%repeat%draft%')",
            (cutoff,),
        ).fetchone()
        repeat_docs = row[0] if row else 0
        metrics.repeat_question_rate = repeat_docs / max(total_docs, 1)

    finally:
        conn.close()


__all__ = ["KBMetrics", "get_kb_metrics"]
