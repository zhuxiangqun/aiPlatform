"""
Agent insight service — aggregated performance metrics per agent.

Reads data from projects.json to compute:
  - rejection_rate: how often HITL rejected this agent's output
  - qa_rollback_rate: how often QA routed back to this agent
  - output_completeness: presence of key fields in output
  - first_pass_rate: accepted without revision
  - total_runs: number of pipeline runs involving this agent
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

_AGENT_INSIGHT_FILE = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "agent_insights.json",
)


class AgentInsightService:

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            if os.path.exists(_AGENT_INSIGHT_FILE):
                with open(_AGENT_INSIGHT_FILE, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
        except Exception:
            pass

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(_AGENT_INSIGHT_FILE), exist_ok=True)
            with open(_AGENT_INSIGHT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def refresh_from_projects(self, projects_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate metrics from all project runs. Called after pipeline completes."""
        agent_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_runs": 0, "total_rejections": 0, "total_qa_rollbacks": 0,
            "runs_with_output": 0, "outputs_complete": 0, "first_pass": 0,
            "recent_runs": [],
        })

        for proj in projects_data:
            team_stages = proj.get("team_stages", [])
            agent_ids = [s.get("agent_id", "") for s in team_stages if s.get("agent_id")]

            for run in proj.get("runs", []):
                error = run.get("error", "")
                phase = run.get("phase", "")

                for agent_id in agent_ids:
                    stats = agent_stats[agent_id]
                    stats["total_runs"] += 1

                    if "stagnation" in error or "reject" in error.lower() or phase == "awaiting_architecture_approval":
                        stats["total_rejections"] += 1

                    if "qa" in error.lower() or "target_agent" in error.lower():
                        stats["total_qa_rollbacks"] += 1

                    if "pass_rate" in run and run.get("pass_rate", 0) >= 0.8:
                        stats["first_pass"] += 1

                    stats["runs_with_output"] += 1
                    stats["recent_runs"].append({
                        "project": proj.get("name", ""),
                        "phase": phase,
                        "pass_rate": run.get("pass_rate", 0),
                        "error": error[:80],
                    })

                # Keep only last 5 runs
                stats["recent_runs"] = stats["recent_runs"][-5:]

        for agent_id, stats in agent_stats.items():
            t = max(stats["total_runs"], 1)
            stats["rejection_rate"] = round(stats["total_rejections"] / t, 2)
            stats["qa_rollback_rate"] = round(stats["total_qa_rollbacks"] / t, 2)
            stats["first_pass_rate"] = round(stats["first_pass"] / t, 2)
            stats["output_completeness"] = round(stats["outputs_complete"] / max(stats["runs_with_output"], 1), 2)

        self._cache = dict(agent_stats)
        self._save_cache()
        return self._cache

    async def get_agent_insight(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(agent_id)

    async def get_all_insights(self) -> Dict[str, Any]:
        return dict(self._cache)

    async def record_run_completion(self, agent_id: str, metrics: Dict[str, Any]) -> None:
        """Record a single run's metrics for incremental update."""
        stats = self._cache.setdefault(agent_id, {
            "total_runs": 0, "total_rejections": 0, "total_qa_rollbacks": 0,
            "runs_with_output": 0, "outputs_complete": 0, "first_pass": 0,
            "recent_runs": [],
        })
        stats["total_runs"] += 1
        stats["recent_runs"].append(metrics)
        stats["recent_runs"] = stats["recent_runs"][-5:]
        t = max(stats["total_runs"], 1)
        stats["rejection_rate"] = round(stats["total_rejections"] / t, 2)
        stats["qa_rollback_rate"] = round(stats["total_qa_rollbacks"] / t, 2)
        stats["first_pass_rate"] = round(stats["first_pass"] / t, 2)
        self._save_cache()
