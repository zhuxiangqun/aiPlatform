"""
RAGDiagnosticsCollector — aggregates RAG quality data from 3 sources.

Sources:
  1. HallucinationTracker — faithfulness, hallucination_risk, quality distribution
  2. FeedbackRadar — implicit user signals (abandon, repeat-query, negative patterns)
  3. Retrieval quality — gate pass rate, HyDE fallback rate (derived from distributions)

Outputs:
  - collect_quality_dashboard() → RAGQualityDashboard (JSON-serializable)
  - collect_bad_cases() → List[BadCase]
  - compute_overall_score() → 0-100 composite score

Used by:
  - diagnostics.py → _check_rag_quality() health check
  - /diagnostics/rag-quality API endpoint
  - /diagnostics/rag-quality/trend API endpoint
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.rag_diagnostics")


@dataclass
class BadCase:
    run_id: str
    question: str
    quality_flag: str
    hallucination_risk: float
    faithfulness: float
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "question": self.question[:100],
            "quality_flag": self.quality_flag,
            "hallucination_risk": round(self.hallucination_risk, 3),
            "faithfulness": round(self.faithfulness, 3),
            "timestamp": self.timestamp,
        }


@dataclass
class RAGQualityDashboard:
    period: str = "24h"
    overview: Dict[str, Any] = field(default_factory=dict)
    hallucination: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)
    retrieval: Dict[str, Any] = field(default_factory=dict)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overview": self.overview,
            "hallucination": self.hallucination,
            "signals": self.signals,
            "retrieval": self.retrieval,
            "anomalies": self.anomalies,
        }


class RAGDiagnosticsCollector:
    """Aggregates RAG quality data from multiple sources into a unified dashboard."""

    def __init__(self):
        self._thresholds: Dict[str, Any] = {}
        self._load_thresholds()

    def _load_thresholds(self):
        """Load thresholds from config/rag_quality.yaml, fallback to inline defaults."""
        import os as _os
        yaml_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__)))),
            "config", "rag_quality.yaml"
        )
        try:
            import yaml as _yaml
            with open(yaml_path) as f:
                cfg = _yaml.safe_load(f) or {}
            self._thresholds = cfg.get("thresholds", {})
        except Exception:
            pass

        # Fallback defaults
        self._thresholds.setdefault("pass_score", 70)
        self._thresholds.setdefault("warn_score", 50)
        self._thresholds.setdefault("faithfulness_warn", 0.7)
        self._thresholds.setdefault("gate_rate_warn", 0.8)
        self._thresholds.setdefault("abandon_rate_warn", 0.1)
        self._thresholds.setdefault("repeat_rate_warn", 0.15)

    async def collect_quality_dashboard(
        self,
        domain_id: str = "default",
        lookback_hours: int = 24,
    ) -> RAGQualityDashboard:
        """Collect unified RAG quality dashboard from all sources."""
        dash = RAGQualityDashboard(period=f"{lookback_hours}h")

        # ── Source 1: HallucinationTracker ──
        try:
            from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
            tracker = get_hallucination_tracker()
            h_dash = tracker.get_dashboard(domain_id=domain_id)
            dash.hallucination = {
                "total_checks": h_dash.get("total_evaluations", 0),
                "avg_faithfulness": round(h_dash.get("avg_faithfulness", 0), 3),
                "avg_relevancy": round(h_dash.get("avg_relevancy", 0), 3),
                "avg_hallucination_risk": round(h_dash.get("avg_hallucination_risk", 0), 3),
                "quality_distribution": h_dash.get("quality_distribution", {}),
            }
            # Relevant score proxy: 1.0 - hallucination_risk
            dash.hallucination["avg_relevancy_proxy"] = round(
                1.0 - dash.hallucination["avg_hallucination_risk"], 3
            )

            # Bad cases from recent reports
            reports = tracker.get_recent_reports(limit=20)
            dash.hallucination["recent_bad_cases"] = [
                BadCase(
                    run_id=r.get("run_id", ""),
                    question=r.get("question", "")[:100],
                    quality_flag=r.get("quality_flag", "ok"),
                    hallucination_risk=r.get("hallucination_risk", 0),
                    faithfulness=r.get("faithfulness", 0),
                    timestamp=r.get("timestamp", ""),
                ).to_dict()
                for r in reports
                if r.get("quality_flag") != "ok"
            ][:20]
        except Exception as e:
            logger.debug("HallucinationTracker unavailable: %s", e)
            dash.hallucination = {"error": "unavailable", "detail": str(e)[:200]}

        # ── Source 2: FeedbackRadar signals ──
        try:
            from core.harness.learning.feedback_radar import FeedbackRadar
            radar = FeedbackRadar()
            # analyze_all_active() returns {signal_alerts, patterns}
            signal_data = radar.analyze_all_active()
            dash.signals = {
                "abandon_rate": signal_data.get("abandon_rate", 0),
                "repeat_query_rate": signal_data.get("repeat_query_rate", 0),
                "active_patterns": signal_data.get("patterns", []),
            }
        except Exception as e:
            logger.debug("FeedbackRadar unavailable: %s", e)
            dash.signals = {"error": "unavailable", "detail": str(e)[:200]}

        # ── Source 3: Retrieval quality (derived from distributions) ──
        dist = dash.hallucination.get("quality_distribution", {})
        total = sum(dist.values()) if dist else 0
        low_evidence = dist.get("low_evidence", 0)
        needs_review = dist.get("needs_review", 0)
        dash.retrieval = {
            "quality_gate_pass_rate": round(
                1.0 - (low_evidence / max(total, 1)), 3
            ),
            "hyde_fallback_rate": round(
                low_evidence / max(total, 1), 3
            ),
            "needs_review_rate": round(
                needs_review / max(total, 1), 3
            ),
            "avg_chunks_retrieved": 0,  # Data source not yet aggregated
        }

        # ── Detect anomalies ──
        dash.anomalies = self._detect_anomalies(dash)

        # ── Compute overall score ──
        dash.overview = {
            "overall_score": self.compute_overall_score(dash),
            "overall_status": self._classify_status(dash),
            "period": f"{lookback_hours}h",
            "anomaly_count": len(dash.anomalies),
        }

        return dash

    def collect_retention_stats(self, domain_id: str = "default") -> Dict[str, Any]:
        """Collect user retention stats from execution_store.

        Returns empty dict if execution_store doesn't have user-level data.
        This is a reserved interface for future implementation.
        """
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            # Query user retention if available
            return {"source": "execution_store", "status": "not_yet_aggregated"}
        except Exception:
            return {"status": "unavailable"}

    def _detect_anomalies(self, dash: RAGQualityDashboard) -> List[Dict[str, Any]]:
        """Check each metric against configured thresholds and flag anomalies."""
        anomalies = []
        t = self._thresholds

        h = dash.hallucination
        r = dash.retrieval
        s = dash.signals

        # Hallucination anomalies
        if h.get("avg_faithfulness", 1.0) < t.get("faithfulness_warn", 0.7):
            anomalies.append({
                "component": "hallucination",
                "metric": "avg_faithfulness",
                "value": h["avg_faithfulness"],
                "threshold": t["faithfulness_warn"],
                "severity": "warning",
            })

        # Retrieval anomalies
        if r.get("quality_gate_pass_rate", 1.0) < t.get("gate_rate_warn", 0.8):
            anomalies.append({
                "component": "retrieval",
                "metric": "quality_gate_pass_rate",
                "value": r["quality_gate_pass_rate"],
                "threshold": t["gate_rate_warn"],
                "severity": "warning",
            })

        # Signal anomalies
        if s.get("abandon_rate", 0) > t.get("abandon_rate_warn", 0.1):
            anomalies.append({
                "component": "signals",
                "metric": "abandon_rate",
                "value": s["abandon_rate"],
                "threshold": t["abandon_rate_warn"],
                "severity": "warning",
            })
        if s.get("repeat_query_rate", 0) > t.get("repeat_rate_warn", 0.15):
            anomalies.append({
                "component": "signals",
                "metric": "repeat_query_rate",
                "value": s["repeat_query_rate"],
                "threshold": t["repeat_rate_warn"],
                "severity": "warning",
            })

        return anomalies

    def compute_overall_score(self, dash: RAGQualityDashboard) -> int:
        """Compute composite 0-100 score from all metrics.

        Formula:
          faithfulness * 35 + relevancy * 25 + quality_gate_rate * 20
          + (1 - abandon_rate) * 10 + (1 - repeat_rate) * 10
        """
        h = dash.hallucination
        r = dash.retrieval
        s = dash.signals

        faith = h.get("avg_faithfulness", 0)
        relevancy = h.get("avg_relevancy_proxy", 0) or h.get("avg_relevancy", 0)
        gate_rate = r.get("quality_gate_pass_rate", 0)
        abandon_rate = s.get("abandon_rate", 0)
        repeat_rate = s.get("repeat_query_rate", 0)

        score = (
            faith * 35
            + relevancy * 25
            + gate_rate * 20
            + (1 - abandon_rate) * 10
            + (1 - repeat_rate) * 10
        )

        return min(100, max(0, round(score)))

    def _classify_status(self, dash: RAGQualityDashboard) -> str:
        """Classify overall health status based on score thresholds."""
        score = dash.overview.get("overall_score", self.compute_overall_score(dash))
        if score >= self._thresholds.get("pass_score", 70):
            return "healthy"
        elif score >= self._thresholds.get("warn_score", 50):
            return "degraded"
        return "unhealthy"
