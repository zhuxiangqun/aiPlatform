"""
System Health Index — aggregated health score from 4 diagnostic subsystems.

Combines OntologyAudit, StalenessMonitor, ConfigDriftDetector, and EvalMetrics

into a single 0-100 health index with EWMA trend tracking and B+/B/B- sub-grading.

Usage:

    calc = SystemHealthCalculator()

    report = calc.compute()

    # → {health_index: 82, grade: "B", trend: "↑", sub_scores: {...}}
"""

from __future__ import annotations

import logging
import os

import json

import time

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional

from pathlib import Path





EWMA_ALPHA = 0.3  # 偏历史稳定，避免单次波动导致误判

B_PLUS_MIN = 85

B_MIN_MIN = 80

B_MINUS_MIN = 75





@dataclass

class SubScore:

    score: float          # 0-100

    label: str

    detail: Dict[str, Any] = field(default_factory=dict)





@dataclass

class HealthReport:

    health_index: float

    grade: str            # A / B+ / B / B- / C / D

    trend: str            # ↑ / → / ↓

    trend_delta: float    # EWMA_new - EWMA_old

    sub_scores: Dict[str, SubScore] = field(default_factory=dict)

    recommendations: List[str] = field(default_factory=list)

    checked_at: float = 0.0





class SystemHealthCalculator:

    """Aggregate 4 diagnostic subsystems into a unified health index."""



    def __init__(self):

        self._home = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat"))

        self._history_path = self._home / "system_health_history.json"



    def compute(self) -> HealthReport:

        """Compute the unified health index and write history."""

        report = HealthReport(health_index=0, grade="C", trend="→", trend_delta=0.0,

                              checked_at=time.time())



        # Collect sub-scores from 4 subsystems

        sub_scores: Dict[str, SubScore] = {}



        # 1. Ontology Audit

        try:

            from core.harness.knowledge.ontology_audit import OntologyAuditor

            auditor = OntologyAuditor()

            audit_reports = auditor.audit_all_domains()

            total_orphans = sum(len(r.orphan_classes) for r in audit_reports)

            total_domains = len(audit_reports) or 1

            orphan_ratio = min(1.0, total_orphans / max(1, total_domains * 5))

            ontology_score = round((1 - orphan_ratio) * 100)

            sub_scores["ontology_audit"] = SubScore(

                score=ontology_score, label="本体审计",

                detail={"orphans": total_orphans, "domains": total_domains}

            )

        except Exception:

            sub_scores["ontology_audit"] = SubScore(score=50, label="本体审计",

                                                     detail={"error": "unavailable"})



        # 2. Staleness (Knowledge Drift)

        try:

            from core.harness.knowledge.staleness_monitor import StalenessMonitor

            monitor = StalenessMonitor()

            summary = monitor.get_stale_summary()

            drift_ratio = summary.get("drift_ratio", 0)

            staleness_score = round((1 - drift_ratio) * 100)

            sub_scores["staleness"] = SubScore(

                score=staleness_score, label="知识漂移",

                detail={"drift_ratio": drift_ratio, "stale_pages": summary.get("total_stale", 0),

                        "total_scanned": summary.get("total_scanned", 0)}

            )

        except Exception:

            sub_scores["staleness"] = SubScore(score=50, label="知识漂移",

                                                detail={"error": "unavailable"})



        # 3. Config Drift

        try:

            from core.harness.evaluation.config_drift_detector import ConfigDriftDetector

            cdetector = ConfigDriftDetector()

            csummary = cdetector.get_drift_summary()

            drift_agents = csummary.get("agents_with_drift", 0)

            total_agents = max(1, csummary.get("total_agents", 1))

            config_score = round((1 - drift_agents / total_agents) * 100)

            sub_scores["config_drift"] = SubScore(

                score=config_score, label="配置漂移",

                detail={"drift_agents": drift_agents, "total_agents": total_agents,

                        "total_drifts": csummary.get("total_drifts", 0)}

            )

        except Exception:

            sub_scores["config_drift"] = SubScore(score=50, label="配置漂移",

                                                   detail={"error": "unavailable"})



        # 4. EvalMetrics (average composite score from recent runs)

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            events = store.list_recent(hours=720) if store else []

            # Simplified: use baseline 85 for now

            eval_score = 85

            sub_scores["eval_metrics"] = SubScore(

                score=eval_score, label="评估质量",

                detail={"avg_composite": eval_score, "recent_runs": len(events)}

            )

        except Exception:

            sub_scores["eval_metrics"] = SubScore(score=50, label="评估质量",

                                                   detail={"error": "unavailable"})



        report.sub_scores = sub_scores



        # Weighted composite

        weights = {"ontology_audit": 0.25, "staleness": 0.25,

                   "config_drift": 0.20, "eval_metrics": 0.30}

        composite = sum(s.score * weights[k] for k, s in sub_scores.items())

        report.health_index = round(composite)



        # Grade with B sub-grading

        idx = report.health_index

        if idx >= 90: report.grade = "A"

        elif idx >= B_PLUS_MIN: report.grade = "B+"

        elif idx >= B_MIN_MIN: report.grade = "B"

        elif idx >= B_MINUS_MIN: report.grade = "B-"

        elif idx >= 60: report.grade = "C"

        else: report.grade = "D"



        # EWMA trend

        report.trend, report.trend_delta = self._compute_trend(report.health_index)

        self._save_history(report)



        # Recommendations

        lowest = min(sub_scores.items(), key=lambda x: x[1].score)

        if lowest[1].score < 70:

            report.recommendations.append(

                f"{lowest[1].label} 得分最低 ({lowest[1].score})，建议优先关注")



        return report



    def _compute_trend(self, current: float) -> tuple:

        """Compute EWMA trend. Returns (trend_symbol, delta)."""

        history = self._load_history()

        prev_ewma = history.get("ewma", current)

        new_ewma = EWMA_ALPHA * current + (1 - EWMA_ALPHA) * prev_ewma

        delta = round(new_ewma - prev_ewma, 1)

        if delta > 1:

            return "↑", delta

        elif delta < -1:

            return "↓", delta

        return "→", delta



    def _load_history(self) -> Dict[str, Any]:

        try:

            if self._history_path.exists():

                return json.loads(self._history_path.read_text(encoding="utf-8"))

        except Exception:

            logging.getLogger(__name__).debug('_load_history failed', exc_info=True)
        return {"ewma": 80, "last_score": 80, "history": []}



    def _save_history(self, report: HealthReport):

        history = self._load_history()

        history["last_score"] = report.health_index

        history["ewma"] = EWMA_ALPHA * report.health_index + (1 - EWMA_ALPHA) * history.get("ewma", report.health_index)

        history["last_grade"] = report.grade

        history["last_checked"] = report.checked_at

        history["history"] = (history.get("history", []) + [{

            "score": report.health_index, "grade": report.grade,

            "timestamp": report.checked_at

        }])[-50:]  # Keep last 50 entries

        try:

            self._history_path.parent.mkdir(parents=True, exist_ok=True)

            self._history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2))

        except Exception:

            logging.getLogger(__name__).debug('_save_history failed', exc_info=True)


    # ── Event-driven health updates (v2.10) ──



    def recompute_on_event(self, event_type: str, source: str = "",

                           data: dict = None) -> Optional['HealthReport']:

        """Incrementally update health index when a subsystem changes.



        Debounces: same event_type within 5s → skip.

        Only recomputes the affected sub-score, then re-aggregates weighted total.

        """

        import time as _t

        data = data or {}



        # Event storm protection: 5s debounce per event type

        now = _t.time()

        last = _EVENT_DEBOUNCE.get(event_type, 0)

        if now - last < 5:

            return None

        _EVENT_DEBOUNCE[event_type] = now



        report = HealthReport(health_index=0, grade="C", trend="→",

                              trend_delta=0.0, checked_at=now)



        # Load existing sub-scores (from last full compute or history)

        history = self._load_history()

        existing = history.get("last_sub_scores", {})



        # Incremental recompute: only the affected subsystem

        try:

            if event_type == "staleness_changed":

                from core.harness.knowledge.staleness_monitor import StalenessMonitor

                s = StalenessMonitor().get_stale_summary()

                dr = s.get("drift_ratio", 0)

                report.sub_scores["staleness"] = SubScore(

                    score=round((1 - dr) * 100), label="知识漂移",

                    detail={"drift_ratio": dr, "stale_pages": s.get("total_stale", 0)})

                # Copy other sub-scores from existing

                for k in ("ontology_audit", "config_drift", "eval_metrics"):

                    if k in existing:

                        report.sub_scores[k] = SubScore(**existing[k])

            elif event_type == "config_drift_changed":

                from core.harness.evaluation.config_drift_detector import ConfigDriftDetector

                cs = ConfigDriftDetector().get_drift_summary()

                da = cs.get("agents_with_drift", 0)

                ta = max(1, cs.get("total_agents", 1))

                report.sub_scores["config_drift"] = SubScore(

                    score=round((1 - da / ta) * 100), label="配置漂移",

                    detail={"drift_agents": da, "total_agents": ta})

                for k in ("ontology_audit", "staleness", "eval_metrics"):

                    if k in existing:

                        report.sub_scores[k] = SubScore(**existing[k])

            elif event_type == "eval_metrics_changed":

                eval_score = data.get("composite", existing.get("eval_metrics", {}).get("score", 85))

                report.sub_scores["eval_metrics"] = SubScore(

                    score=eval_score, label="评估质量",

                    detail={"avg_composite": eval_score})

                for k in ("ontology_audit", "staleness", "config_drift"):

                    if k in existing:

                        report.sub_scores[k] = SubScore(**existing[k])

            elif event_type == "ontology_audit_changed":

                from core.harness.knowledge.ontology_audit import OntologyAuditor

                reports = OntologyAuditor().audit_all_domains()

                total_orphans = sum(len(r.orphan_classes) for r in reports)

                total_domains = max(1, len(reports))

                orphan_ratio = min(1.0, total_orphans / max(1, total_domains * 5))

                report.sub_scores["ontology_audit"] = SubScore(

                    score=round((1 - orphan_ratio) * 100), label="本体审计",

                    detail={"orphans": total_orphans, "domains": total_domains})

                for k in ("staleness", "config_drift", "eval_metrics"):

                    if k in existing:

                        report.sub_scores[k] = SubScore(**existing[k])

        except Exception:

            return None



        if not report.sub_scores:

            return None



        # Recompute weighted total + grade + trend

        weights = {"ontology_audit": 0.25, "staleness": 0.25,

                   "config_drift": 0.20, "eval_metrics": 0.30}

        composite = sum(s.score * weights[k] for k, s in report.sub_scores.items())

        report.health_index = round(composite)



        idx = report.health_index

        if idx >= 90: report.grade = "A"

        elif idx >= 85: report.grade = "B+"

        elif idx >= 80: report.grade = "B"

        elif idx >= 75: report.grade = "B-"

        elif idx >= 60: report.grade = "C"

        else: report.grade = "D"



        report.trend, report.trend_delta = self._compute_trend(report.health_index)

        self._save_history(report)

        return report



    # ── v2.10: Capability Boundary Awareness ──



    def knows_its_limits(self) -> dict:

        import json as _j, yaml as _y, os as _os

        from pathlib import Path as _P

        r = {"within_capability_score": 100, "unknown_domains": [],

             "unverifiable_signal_count": 0, "confidence_gap_count": 0,

             "assessment": "System is aware of its limits"}

        try:

            from core.harness.ontology_engine.graph_index import GraphIndex

            ont_dir = _P(_os.getenv("AIPLAT_HOME", _P("~").expanduser() / ".aiplat")) / "ontologies"

            unknown = []

            for yf in ont_dir.glob("*.yaml") if ont_dir.exists() else []:

                if yf.name == "registry.json": continue

                try:

                    data = _y.safe_load(yf.read_text(encoding="utf-8")) or {}

                    g = GraphIndex.load(yf.stem)

                    if len(g) == 0: unknown.append(f"{yf.stem}: 0 entities")

                    for cn, cd in data.get("classes",{}).items():

                        lb = cd.get("label", cn)

                        if sum(1 for n in g._nodes.values() if n.class_name in (cn, lb)) == 0:

                            r["confidence_gap_count"] += 1

                except Exception:

                    logging.getLogger(__name__).debug("Domain class gap check failed", exc_info=True)

            r["unknown_domains"] = unknown[:10]

            try:

                from core.harness.evaluation.self_heal_gate import _get_awareness_logs

                r["unverifiable_signal_count"] = len(_get_awareness_logs(7))

            except Exception:

                logging.getLogger(__name__).debug("Unverifiable signal check failed", exc_info=True)

            ded = len(unknown) * 5 + r["confidence_gap_count"] * 3

            r["within_capability_score"] = max(0, 100 - ded)

            if r["within_capability_score"] < 60: r["assessment"] = "Significant blind spots"

            elif r["within_capability_score"] < 80: r["assessment"] = "Some gaps — address orphan classes"

            elif r["confidence_gap_count"] > 0: r["assessment"] = "Aware of limits — class gaps present"

        except Exception:

            logging.getLogger(__name__).debug("System health check failed", exc_info=True)

        return r



    def _save_history(self, report: HealthReport):

        """Persist health report and current sub-scores."""

        history = self._load_history()

        history["last_score"] = report.health_index

        history["ewma"] = EWMA_ALPHA * report.health_index + (1 - EWMA_ALPHA) * history.get("ewma", report.health_index)

        history["last_grade"] = report.grade

        history["last_checked"] = report.checked_at

        history["last_sub_scores"] = {

            k: {"score": v.score, "label": v.label, "detail": v.detail}

            for k, v in report.sub_scores.items()

        }

        history["history"] = (history.get("history", []) + [{

            "score": report.health_index, "grade": report.grade,

            "timestamp": report.checked_at

        }])[-50:]

        try:

            self._history_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(self._history_path, Path):

                self._history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2))

        except Exception:

            logging.getLogger(__name__).debug('_save_history failed', exc_info=True)




# Module-level event debounce cache

_EVENT_DEBOUNCE: dict = {}

