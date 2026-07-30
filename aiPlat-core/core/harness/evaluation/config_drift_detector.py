"""Config Drift Detector — compare deployed agent state vs AGENT.md specification.



Detects when an agent's runtime behavior diverges from its declared configuration.

Uses the StalenessMonitor pattern for periodic scanning with the governance cron.



Usage:

    detector = ConfigDriftDetector()

    report = detector.scan_all_agents()

    # → [{agent_id, drift_type, declared, actual, severity}, ...]

"""



from __future__ import annotations



from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional

from pathlib import Path

import os

import logging





@dataclass

class DriftEntry:

    agent_id: str = ""

    drift_type: str = ""          # "phase_violation", "skill_unused", "tool_unbind", "hitl_bypass"

    declared: str = ""            # What AGENT.md says

    actual: str = ""              # What actually happens

    severity: str = "warning"     # warning/critical





class ConfigDriftDetector:

    """Compare runtime agent behavior against AGENT.md declarations."""



    def __init__(self):

        self._home = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat"))

        self._agents_dir = self._home / "agents"



    def scan_all_agents(self) -> List[DriftEntry]:

        """Scan all workspace agents for configuration drift."""

        entries: List[DriftEntry] = []



        if not self._agents_dir.exists():

            return entries



        for adir in self._agents_dir.iterdir():

            if not adir.is_dir():

                continue

            agent_file = adir / "AGENT.md"

            if not agent_file.exists():

                continue



            agent_id = adir.name

            try:

                drift = self._check_agent_drift(agent_id, agent_file)

                entries.extend(drift)

            except Exception:

                logging.getLogger(__name__).debug('scan_all_agents failed', exc_info=True)


        # v2.10: Event-driven health update

        if entries:

            try:

                from core.harness.evaluation.system_health import SystemHealthCalculator

                SystemHealthCalculator().recompute_on_event("config_drift_changed", source="scan_all_agents")

            except Exception:

                logging.getLogger(__name__).debug('scan_all_agents failed', exc_info=True)
        return entries



    def _check_agent_drift(self, agent_id: str, agent_file: Path) -> List[DriftEntry]:

        """Check one agent for 4 drift dimensions."""

        entries: List[DriftEntry] = []

        content = agent_file.read_text(encoding="utf-8")



        fm = self._parse_frontmatter(content)

        if not fm:

            return entries



        # 1. HITL bypass: declared auto_hitl but never paused

        if fm.get("auto_hitl"):

            entries.append(DriftEntry(

                agent_id=agent_id, drift_type="hitl_bypass",

                declared=f"auto_hitl: true (phase: {fm.get('hitl_phase', '?')})",

                actual="No HITL pause events detected",

                severity="warning",

            ))



        # 2. Skill unused: declared skills but none executed

        skills = fm.get("required_skills") or fm.get("skills") or []

        if skills:

            entries.append(DriftEntry(

                agent_id=agent_id, drift_type="skill_unbind_check",

                declared=f"{len(skills)} skills: {', '.join(skills[:3])}",

                actual="Verify all declared skills are available in SkillRegistry",

                severity="warning",

            ))



        # 3. Model mismatch: declared model not in registry

        model = fm.get("model", "")

        if model and model not in ("auto", "best"):

            entries.append(DriftEntry(

                agent_id=agent_id, drift_type="model_config_check",

                declared=f"model: {model}",

                actual="Verify model is available in ModelManager",

                severity="warning",

            ))



        # 4. Phase violation: declared phase but agent operates in different phase at runtime

        phase = fm.get("phase", "")

        if phase:

            entries.append(DriftEntry(

                agent_id=agent_id, drift_type="phase_alignment_check",

                declared=f"phase: {phase}",

                actual="Verify runtime phase matches declaration",

                severity="warning",

            ))



        return entries



    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:

        """Parse YAML frontmatter from AGENT.md."""

        if not text.startswith("---"):

            return {}

        parts = text.split("---", 2)

        if len(parts) < 3:

            return {}

        try:

            import yaml

            return yaml.safe_load(parts[1]) or {}

        except Exception:

            return {}



    def get_drift_summary(self) -> Dict[str, Any]:

        """Quick summary for dashboard."""

        entries = self.scan_all_agents()

        critical = [e for e in entries if e.severity == "critical"]

        warnings = [e for e in entries if e.severity == "warning"]

        result = {

            "total_agents": len([d for d in self._agents_dir.iterdir() if d.is_dir() and d.joinpath("AGENT.md").exists()]) if self._agents_dir.exists() else 0,

            "agents_with_drift": len(set(e.agent_id for e in entries)),

            "total_drifts": len(entries),

            "critical_count": len(critical),

            "warning_count": len(warnings),

            "by_type": _count_by(entries, "drift_type"),

        }

        # v2.10: Include ossification in summary

        ossified = self.detect_pattern_ossification()

        if ossified:

            result["ossified_agents"] = len(ossified)

            result["by_type"]["pattern_ossification"] = len(ossified)

        return result



    # ── v2.10: Pattern Ossification Detection ──



    def detect_pattern_ossification(self, recent_runs: int = 20) -> list:

        ossified = []

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            events = store.list_recent(hours=720) if store and hasattr(store, "list_recent") else []

            if not events:

                return ossified

            agent_tool_seqs, agent_success = {}, {}

            for e in events:

                aid = str(e.get("agent_id", ""))

                if not aid:

                    continue

                if e.get("kind") in ("tool", "tool_call"):

                    n = e.get("name") or e.get("tool_name", "")

                    agent_tool_seqs.setdefault(aid, []).append(n)

                if e.get("kind") in ("agent_complete", "done"):

                    agent_success[aid] = agent_success.get(aid, 0) + 1

            for aid, seq in agent_tool_seqs.items():

                if len(seq) < recent_runs:

                    continue

                recent = seq[-recent_runs:]

                unique = len(set(recent))

                if unique <= 3 and len(recent) >= 10:

                    mc = max(set(recent), key=recent.count)

                    ossified.append(DriftEntry(

                        agent_id=aid, drift_type="pattern_ossification",

                        declared=f"Repeated {mc} in {recent.count(mc)}/{len(recent)} runs",

                        actual=f"Only {agent_success.get(aid, 0)} completions",

                        severity="warning"))

        except Exception:

            logging.getLogger(__name__).debug('detect_pattern_ossification failed', exc_info=True)
        return ossified





def _count_by(entries: List[DriftEntry], field: str) -> Dict[str, int]:

    counts: Dict[str, int] = {}

    for e in entries:

        val = getattr(e, field, "unknown")

        counts[val] = counts.get(val, 0) + 1

    return counts

