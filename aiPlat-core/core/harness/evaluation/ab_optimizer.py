"""
EvalABOptimizer — closes the A/B testing loop by feeding evaluation scores back
into prompt template rollout weights.

Design principle (CLAUDE.md §5.30, control theory Rule #4):
  Prompt changes MUST be A/B tested with independent evaluator results.
  The system auto-boosts the winning version's weight over time.

Flow:
  1. _tri_evaluate → record_score(template_id, version, score)
  2. POST /prompts/{id}/auto-optimize → compute winner → adjust rollout weights
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("pipeline_engine.ab_optimizer")


class EvalABOptimizer:
    MIN_EVALS_PER_VERSION = int(os.getenv("AIPLAT_AB_MIN_EVALS", "5"))
    WINNER_WEIGHT_BOOST = float(os.getenv("AIPLAT_AB_WINNER_BOOST", "0.1"))

    @staticmethod
    def _get_store():
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            return getattr(rt, "execution_store", None) if rt else None
        except Exception:
            return None

    @classmethod
    def ensure_tables(cls) -> None:
        store = cls._get_store()
        if not store or not hasattr(store, "_conn"):
            return
        try:
            conn = store._conn.get_connection()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_eval_scores (
                    id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    session_id TEXT,
                    overall_score REAL,
                    pass_rate REAL,
                    recommendation TEXT,
                    created_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prompt_eval_scores_tid_ver ON prompt_eval_scores(template_id, version);"
            )
        except Exception:
            _log.debug("prompt_eval_scores table init skipped", exc_info=True)

    @classmethod
    def record_score(
        cls,
        template_id: str,
        version: str,
        overall_score: float,
        pass_rate: float = 0.0,
        recommendation: str = "",
        session_id: str = "",
    ) -> None:
        store = cls._get_store()
        if not store or not template_id or not version:
            return
        try:
            conn = store._conn.get_connection()
            cls.ensure_tables()
            conn.execute(
                "INSERT INTO prompt_eval_scores(id, template_id, version, session_id, overall_score, pass_rate, recommendation, created_at) VALUES(?,?,?,?,?,?,?,?);",
                (uuid.uuid4().hex, template_id, version, session_id, overall_score, pass_rate, recommendation, time.time()),
            )
        except Exception:
            _log.debug("record_score best-effort skipped", exc_info=True)

    @classmethod
    def get_version_scores(
        cls, template_id: str, limit: int = 200
    ) -> Dict[str, Dict[str, Any]]:
        store = cls._get_store()
        if not store:
            return {}
        try:
            conn = store._conn.get_connection()
            rows = conn.execute(
                "SELECT version, AVG(overall_score) AS avg_score, COUNT(1) AS cnt, AVG(pass_rate) AS avg_pass FROM prompt_eval_scores WHERE template_id=? GROUP BY version ORDER BY cnt DESC LIMIT ?;",
                (template_id, limit),
            ).fetchall()
            return {
                str(row["version"]): {
                    "avg_score": round(float(row["avg_score"] or 0), 2),
                    "eval_count": int(row["cnt"] or 0),
                    "avg_pass_rate": round(float(row["avg_pass"] or 0), 2),
                }
                for row in rows
            }
        except Exception:
            return {}

    @classmethod
    def compute_optimized_rollout(
        cls,
        current_rollout: List[Dict[str, Any]],
        template_id: str,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
        if not current_rollout:
            return None, {"reason": "no_rollout_configured"}
        scores = cls.get_version_scores(template_id)
        if not scores:
            return None, {"reason": "no_eval_data"}

        candidates: List[Dict[str, Any]] = []
        for it in current_rollout:
            ver = str(it.get("version", ""))
            if not ver:
                continue
            stats = scores.get(ver, {})
            avg = stats.get("avg_score", 0)
            cnt = stats.get("eval_count", 0)
            if cnt >= cls.MIN_EVALS_PER_VERSION:
                candidates.append({
                    "version": ver,
                    "weight": int(it.get("weight", 0)),
                    "avg_score": avg,
                    "eval_count": cnt,
                })

        if len(candidates) < 2:
            return None, {"reason": "insufficient_eval_data", "candidates": len(candidates)}

        best = max(candidates, key=lambda x: x["avg_score"])
        baseline_weight = best["weight"]
        new_weight = min(95, baseline_weight + int(baseline_weight * cls.WINNER_WEIGHT_BOOST + 5))
        total_others = sum(c["weight"] for c in candidates if c["version"] != best["version"])
        max_other_total = 100 - new_weight
        if total_others > max_other_total and total_others > 0:
            ratio = max_other_total / total_others
        else:
            ratio = 1.0
        new_rollout = []
        for c in candidates:
            if c["version"] == best["version"]:
                new_rollout.append({"version": c["version"], "weight": new_weight})
            else:
                adjusted = max(1, int(c["weight"] * ratio))
                new_rollout.append({"version": c["version"], "weight": adjusted})

        report = {
            "winner": best["version"],
            "winner_avg_score": best["avg_score"],
            "winner_eval_count": best["eval_count"],
            "old_weight": baseline_weight,
            "new_weight": new_weight,
            "previous_rollout": current_rollout,
            "new_rollout": new_rollout,
            "all_scores": scores,
        }
        return new_rollout, report
