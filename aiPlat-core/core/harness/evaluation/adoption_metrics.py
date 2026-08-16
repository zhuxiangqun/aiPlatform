"""AdoptionMetrics — employee engagement and resistance tracking.



Measures AI platform adoption health through usage patterns,

GrillingBridge engagement rates, HITL behaviors, and resistance signals.

Used by the Diagnostics dashboard for people-side governance.



Usage:

    tracker = AdoptionTracker()

    report = tracker.compute_metrics()

    # → {agent_usage, grill_rate, hitl_trends, resistance_hotspots, ...}

"""



from __future__ import annotations



import os

import time

import logging

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional

from pathlib import Path

from collections import Counter





@dataclass

class AdoptionReport:

    total_agent_calls: int = 0

    total_users: int = 0

    active_users_7d: int = 0

    grill_trigger_rate: float = 0.0          # GrillingBridge auto-trigger %

    grill_completion_rate: float = 0.0        # Started grill → completed %

    hitl_approval_rate: float = 0.0           # HITL approve %

    hitl_rejection_rate: float = 0.0          # HITL reject %

    resistance_hotspots: List[Dict[str, Any]] = field(default_factory=list)

    adoption_trend: str = "stable"            # rising/stable/declining

    recommendations: List[str] = field(default_factory=list)

    computed_at: float = 0.0





class AdoptionTracker:

    """Track AI platform adoption metrics from execution store and KB data."""



    def __init__(self):

        self._home = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat"))



    def compute_metrics(self) -> AdoptionReport:

        """Build adoption report from available data sources."""

        report = AdoptionReport(computed_at=time.time())



        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()



            # Agent call frequency (last 30 days)

            events = self._load_recent_events(store, hours=720)

            agent_calls = [e for e in events if e.get("kind") == "agent" or e.get("event_type") == "agent_call"]

            report.total_agent_calls = len(agent_calls)



            # Unique users

            users = set()

            for e in events:

                uid = e.get("user_id") or e.get("actor_id") or e.get("tenant_id")

                if uid:

                    users.add(str(uid))

            report.total_users = len(users)



            # Active users (7d)

            recent = self._load_recent_events(store, hours=168)

            active_users = set()

            for e in recent:

                uid = e.get("user_id") or e.get("actor_id") or e.get("tenant_id")

                if uid:

                    active_users.add(str(uid))

            report.active_users_7d = len(active_users)



            # GrillingBridge engagement

            grill_starts = [e for e in events if e.get("kind") == "grill_start" or e.get("event_type") == "grilling_start"]

            grill_completes = [e for e in events if e.get("kind") == "grill_complete" or e.get("event_type") == "grilling_complete"]

            total_queries = sum(1 for e in events if e.get("kind") in ("query", "execute", "chat") or e.get("event_type") in ("agent_query", "chat_query"))

            if total_queries > 0:

                report.grill_trigger_rate = round(len(grill_starts) / total_queries, 3)

            if grill_starts:

                report.grill_completion_rate = round(len(grill_completes) / len(grill_starts), 3)



            # HITL trends

            hitl_approves = [e for e in events if e.get("event_type") == "hitl_approved" or e.get("kind") == "hitl_approve"]

            hitl_rejects = [e for e in events if e.get("event_type") == "hitl_rejected" or e.get("kind") == "hitl_reject"]

            total_hitl = len(hitl_approves) + len(hitl_rejects)

            if total_hitl > 0:

                report.hitl_approval_rate = round(len(hitl_approves) / total_hitl, 3)

                report.hitl_rejection_rate = round(len(hitl_rejects) / total_hitl, 3)



        except Exception:

            logging.getLogger(__name__).debug('compute_metrics failed', exc_info=True)


        # Resistance detection

        report.resistance_hotspots = self._detect_resistance(events)



        # Adoption trend

        if report.active_users_7d < report.total_users * 0.3:

            report.adoption_trend = "declining"

        elif report.grill_trigger_rate > 0.3:

            report.adoption_trend = "rising"

        else:

            report.adoption_trend = "stable"



        # Recommendations

        if report.grill_trigger_rate > 0.2 and report.grill_completion_rate < 0.5:

            report.recommendations.append("GrillingBridge triggered often but rarely completed — consider simplifying interview questions or reducing required dimensions")

        if report.hitl_rejection_rate > 0.3:

            report.recommendations.append(f"HITL rejection rate high ({report.hitl_rejection_rate:.0%}) — review stage quality or prompt instructions")

        if report.active_users_7d == 0 and report.total_users > 0:

            report.recommendations.append("No active users in 7 days — all users may have abandoned the platform")

        if report.resistance_hotspots:

            report.recommendations.append(f"{len(report.resistance_hotspots)} resistance hotspots detected — see details below")



        return report



    def _load_recent_events(self, store, hours: int) -> List[Dict[str, Any]]:

        """Load recent syscall events from execution store."""

        try:

            return store.list_recent(hours=hours) or []

        except Exception:

            return []



    def _detect_resistance(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        """Detect resistance patterns from user behavior signals.



        Signals:

        - Repeated grill skipping (user skips > 3 consecutive questions)

        - Frequent HITL rejection without feedback

        - Agent abandonment (started but never completed)

        - Return to manual mode (agent query followed by manual query)

        """

        hotspots = []



        try:

            # Group events by user

            user_events: Dict[str, List[Dict]] = {}

            for e in events:

                uid = str(e.get("user_id") or e.get("actor_id") or e.get("tenant_id") or "unknown")

                if uid not in user_events:

                    user_events[uid] = []

                user_events[uid].append(e)



            for uid, uevts in user_events:

                # Count grill skips

                grill_skips = sum(1 for e in uevts if e.get("kind") == "grill_skip" or e.get("event_type") == "grilling_skip")

                grill_answered = sum(1 for e in uevts if e.get("kind") == "grill_answer" or e.get("event_type") == "grilling_answer")



                # Count HITL rejections without feedback

                hitl_rejects_no_feedback = sum(

                    1 for e in uevts

                    if (e.get("kind") == "hitl_reject" or e.get("event_type") == "hitl_rejected")

                    and not (e.get("feedback") or e.get("reason"))

                )



                # Detect abandonment: agent_execute followed by no completion within 5min

                exec_events = [e for e in uevts if e.get("kind") in ("agent_execute", "query", "chat")]

                complete_events = [e for e in uevts if e.get("kind") in ("agent_complete", "done")]



                abandonment_signals = []

                if grill_skips > 3 and grill_skips > grill_answered:

                    abandonment_signals.append(f"Grilling skip rate high ({grill_skips} skips, {grill_answered} answers)")

                if hitl_rejects_no_feedback > 2:

                    abandonment_signals.append(f"HITL rejected without feedback ({hitl_rejects_no_feedback} times)")

                if len(exec_events) > 5 and len(complete_events) < len(exec_events) * 0.5:

                    abandonment_signals.append(f"Low completion rate ({len(complete_events)}/{len(exec_events)})")



                if abandonment_signals:

                    hotspots.append({

                        "user": uid,

                        "signals": abandonment_signals,

                        "grill_skips": grill_skips,

                        "hitl_rejections": hitl_rejects_no_feedback,

                        "exec_count": len(exec_events),

                        "complete_count": len(complete_events),

                        "severity": "high" if len(abandonment_signals) >= 3 else "medium",

                    })

        except Exception:

            logging.getLogger(__name__).debug('_detect_resistance failed', exc_info=True)


        return sorted(hotspots, key=lambda x: len(x["signals"]), reverse=True)[:10]



    def get_training_effectiveness(self, before_events: List[Dict], after_events: List[Dict]) -> Dict[str, Any]:

        """Compare before/after training metrics to measure effectiveness."""

        before_grill_complete = sum(1 for e in before_events if e.get("kind") == "grill_complete")

        after_grill_complete = sum(1 for e in after_events if e.get("kind") == "grill_complete")

        before_errors = sum(1 for e in before_events if "error" in str(e.get("kind","")).lower())

        after_errors = sum(1 for e in after_events if "error" in str(e.get("kind","")).lower())



        grill_improvement = (after_grill_complete - before_grill_complete) / max(1, before_grill_complete) if before_grill_complete else 0

        error_reduction = (before_errors - after_errors) / max(1, before_errors) if before_errors else 0



        return {

            "grill_completion_delta": round(grill_improvement, 2),

            "error_reduction_delta": round(error_reduction, 2),

            "effective": grill_improvement > 0 or error_reduction > 0,

            "recommendation": "Training effective — metrics improved" if grill_improvement > 0 or error_reduction > 0 else "Training may need reinforcement — no measurable improvement detected"

        }

    def get_historical(self, days: int = 30) -> List[Dict[str, float]]:
        """Return daily metric snapshots for baseline calculation.

        Query adoption_metrics from execution_store.
        Returns empty list on cold start (caller handles insufficient history).
        """
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            rows = store.query_adoption_metrics(days=days)
            if not rows:
                return []
            return [
                {
                    "date": r.get("snapshot_date", ""),
                    "hitl_approval_rate": float(r.get("hitl_approval_rate", 0)),
                    "hitl_rejection_rate": float(r.get("hitl_rejection_rate", 0)),
                    "grill_completion_rate": float(r.get("grill_completion_rate", 0)),
                }
                for r in rows
            ]
        except Exception:
            return []

