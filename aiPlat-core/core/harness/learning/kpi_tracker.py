"""KPI tracker — aggregates pipeline pass rates and feeds back to model health.

Reads from pipeline_runs table (PipelineRunStore), computes per-model
business scores, and writes back to model_health table for _score_model
to consume as a dynamic ranking factor.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time as _time
from typing import Dict, List

logger = logging.getLogger(__name__)


class KPITracker:
    def get_all(self, spec_id: str | None = None) -> list[dict]:
        """Return basic KPI summary for the dashboard."""
        try:
            metrics = self._query_model_performance()
            return metrics
        except Exception:
            logger.debug("KPITracker.get_all failed", exc_info=True)
            return []

    async def aggregate_daily_metrics(self) -> Dict[str, float]:
        """Daily cron: aggregate pipeline pass rates per model, write back to health.

        Returns:
            Dict[model_name, avg_pass_rate] for models used yesterday.
        """
        db_path = os.path.expanduser(
            os.getenv("AIPLAT_EXECUTION_DB_PATH",
                      os.path.join("~", ".aiplat", "data", "pipeline_runs.db")))
        db_path = os.path.expanduser(db_path)

        if not os.path.isfile(db_path):
            logger.debug("pipeline_runs.db not found, skipping KPI aggregation")
            return {}

        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            rows = conn.execute("""
                SELECT primary_model_used,
                       COUNT(*) as total_runs,
                       AVG(pass_rate) as avg_pass_rate
                FROM pipeline_runs
                WHERE DATE(started_at) = DATE('now', '-1 day')
                  AND primary_model_used IS NOT NULL
                GROUP BY primary_model_used
            """).fetchall()

            scores: Dict[str, float] = {}
            for row in rows:
                model = row[0]
                avg_pass = row[2] if row[2] is not None else 0.5
                scores[model] = round(avg_pass, 4)

            # Write back to ModelHealthStore
            if scores:
                try:
                    from core.harness.utils.model_health_store import get_model_health_store
                    store = get_model_health_store()
                    for model, score in scores.items():
                        store.set_business_score(model, score)
                    logger.info("Business scores updated for %d models: %s",
                                len(scores), scores)
                except Exception:
                    logger.debug("Business score write-back failed", exc_info=True)

            return scores
        finally:
            conn.close()

    def _query_model_performance(self) -> list[dict]:
        """Return model-level KPI summary for dashboard display."""
        db_path = os.path.expanduser(
            os.getenv("AIPLAT_EXECUTION_DB_PATH", ""))
        if not db_path or not os.path.isfile(db_path):
            return []

        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            rows = conn.execute("""
                SELECT primary_model_used,
                       COUNT(*) as total,
                       AVG(pass_rate) as avg_pass,
                       SUM(tokens_used) as total_tokens
                FROM pipeline_runs
                WHERE primary_model_used IS NOT NULL
                GROUP BY primary_model_used
                ORDER BY total DESC
            """).fetchall()
            return [
                {"model": r[0], "total_runs": r[1],
                 "avg_pass_rate": round(r[2] or 0, 3), "total_tokens": r[3] or 0}
                for r in rows
            ]
        finally:
            conn.close()


_tracker: KPITracker | None = None


def get_kpi_tracker() -> KPITracker:
    global _tracker
    if _tracker is None:
        _tracker = KPITracker()
    return _tracker
