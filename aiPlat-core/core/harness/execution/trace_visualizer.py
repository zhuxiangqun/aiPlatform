"""
TraceVisualizer — Agent decision traces → developer-readable format (Andrew Ng three-layer Loop P2)

Translates the _dynamic_trace produced by DynamicRouter at runtime into:
  1. Decision chain: whom each step selected, and the Supervisor's reasoning basis
  2. Hesitation points: uncertainty signals when an Agent reconsiders
  3. Anomaly points: the same Agent being called repeatedly / skipped / timed out
  4. Efficiency summary: total steps, repeat rate, path-selection diversity

Output format: developer-ready text + structured data to help understand Agent behavior
and locate the parts of the Spec that need correction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.trace_visualizer")


@dataclass
class TraceStep:
    step: int
    agent: str
    reasoning: str
    decision: str
    is_hesitation: bool = False      # reasoning contains uncertain words like "consider", "maybe", "or"
    is_repeat: bool = False          # the same Agent was already called in a previous step
    outcome: str = ""                # ok / timeout / error


@dataclass
class TraceSummary:
    spec_id: str
    total_steps: int
    unique_agents: List[str]
    agent_call_order: List[str]      # actual call order
    repeat_count: int                 # number of repeated calls
    hesitation_count: int             # number of hesitant steps
    max_repeat_agent: str = ""        # the Agent called the most times
    steps: List[TraceStep] = field(default_factory=list)
    anomaly_warnings: List[str] = field(default_factory=list)
    spec_suggestions: List[str] = field(default_factory=list)


class TraceVisualizer:
    """Raw trace → developer-readable analysis.

    Usage:
        viz = TraceVisualizer()
        summary = viz.analyze(trace_data, spec_id="my-agent", stage_count=5)
        # summary.anomaly_warnings → ["architect was called 3 times, possibly over-split tasks"]
        # summary.spec_suggestions → ["suggest adding an output_artifact constraint at Stage 2"]
    """

    # hesitation words → likelihood score
    HESITATION_PATTERNS = [
    ("consider", 0.5), ("maybe", 0.4), ("unsure", 0.7),
    ("or", 0.3), ("temporarily", 0.3), ("try", 0.4),
        ("maybe", 0.4), ("perhaps", 0.4), ("unclear", 0.6),
        ("alternatively", 0.4),
    ]

    def analyze(
        self,
        trace: List[Dict[str, Any]],
        *,
        spec_id: str = "",
        stage_count: int = 0,
        goal: str = "",
    ) -> TraceSummary:
        steps = self._parse_steps(trace)
        unique = list(dict.fromkeys(s.agent for s in steps if s.agent))
        repeats = [s for s in steps if s.is_repeat]
        hesitations = [s for s in steps if s.is_hesitation]
        max_repeat = self._most_repeated(steps)

        summary = TraceSummary(
            spec_id=spec_id,
            total_steps=len(steps),
            unique_agents=unique,
            agent_call_order=[s.agent for s in steps if s.agent],
            repeat_count=len(repeats),
            hesitation_count=len(hesitations),
            max_repeat_agent=max_repeat,
            steps=steps,
        )

        # anomaly detection
        summary.anomaly_warnings = self._detect_anomalies(steps, stage_count)
        # Spec adjustment suggestions
        summary.spec_suggestions = self._suggest_spec_changes(steps, stage_count, goal)

        return summary

    def _parse_steps(self, trace: List[Dict[str, Any]]) -> List[TraceStep]:
        seen: Dict[str, int] = {}  # agent → first_step
        result: List[TraceStep] = []
        for entry in trace:
            agent = entry.get("agent", entry.get("agent_name", ""))
            reasoning = entry.get("reasoning", "")
            decision = entry.get("decision", "call_agent")
            step = entry.get("step", len(result) + 1)
            is_hesitation = self._check_hesitation(reasoning)
            is_repeat = agent in seen and (step - seen[agent] > 1)
            if agent and agent not in seen:
                seen[agent] = step
            result.append(TraceStep(
                step=step, agent=agent, reasoning=reasoning,
                decision=decision, is_hesitation=is_hesitation,
                is_repeat=is_repeat,
                outcome=entry.get("outcome", "ok"),
            ))
        return result

    def _check_hesitation(self, reasoning: str) -> bool:
        score = 0.0
        for word, weight in self.HESITATION_PATTERNS:
            if word.lower() in reasoning.lower():
                score += weight
        return score >= 0.5

    @staticmethod
    def _most_repeated(steps: List[TraceStep]) -> str:
        counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                counts[s.agent] = counts.get(s.agent, 0) + 1
        if not counts:
            return ""
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    def _detect_anomalies(self, steps: List[TraceStep], stage_count: int) -> List[str]:
        warnings: List[str] = []

        # 1. The same Agent was called ≥ 2 times (may need to merge stages)
        agent_counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                agent_counts[s.agent] = agent_counts.get(s.agent, 0) + 1
        for agent, count in agent_counts.items():
            if count >= 3:
                warnings.append(f"🔁 {agent} called {count} times — consider splitting into sub-Agents")
            elif count >= 2:
                warnings.append(f"🔄 {agent} called {count} times — check if should be reused")

        # 2. Step count vs expected stage count
        if stage_count > 0 and len(steps) > stage_count * 1.5:
            warnings.append(f"📊 Executed {len(steps)} steps (expected {stage_count} stages) — Agent may be looping")

        # 3. Multiple hesitation steps
        hesitation = [s for s in steps if s.is_hesitation]
        if len(hesitation) >= 3:
            warnings.append(f"🤔 Supervisor hesitated {len(hesitation)} times — stage boundaries may be unclear")

        # 4. Reasoning too short (Supervisor may not have analyzed properly)
        short_reason = [s for s in steps if len(s.reasoning) < 20]
        if len(short_reason) >= len(steps) * 0.5 and len(steps) >= 3:
            warnings.append("⚡ Supervisor reasoning too short — may have selected Agent without analysis")

        # 5. Timeout/error steps
        errors = [s for s in steps if s.outcome in ("timeout", "error")]
        if errors:
            warnings.append(f"✕ {len(errors)} step(s) failed ({', '.join(s.agent for s in errors)})")

        return warnings

    def _suggest_spec_changes(
        self, steps: List[TraceStep], stage_count: int, goal: str
    ) -> List[str]:
        suggestions: List[str] = []

        # Based on repeated Agent calls → suggest adjusting the stage config
        agent_counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                agent_counts[s.agent] = agent_counts.get(s.agent, 0) + 1
        for agent, count in agent_counts.items():
            if count >= 3:
                suggestions.append(
                    f"Stage '{agent}' was called repeatedly — check the dependency config, "
                    f"or split it into sub-agents with clear contexts"
                )

        # Based on hesitation → suggest clarifying stage division in the Spec
        hesitation = [s for s in steps if s.is_hesitation]
        if hesitation:
            agents_in_hesitation = list(dict.fromkeys(s.agent for s in hesitation if s.agent))
            suggestions.append(
                f"Supervisor hesitated between stages {', '.join(agents_in_hesitation[:3])} — "
                f"clarify each stage's output dependency in the Spec's pipeline_stage"
            )

        # Based on excessive steps → suggest limiting
        if stage_count > 0 and len(steps) > stage_count * 2:
            suggestions.append(
                f"Set max_steps={stage_count + 2} in PipelineConfig to prevent over-execution"
            )

        return suggestions

    def format_chain(self, summary: TraceSummary) -> str:
        """Generate a text rendering of the decision chain, for frontend/diagnostic panels."""
        lines = [f"## {summary.spec_id} decision chain ({summary.total_steps} steps)"]
        for s in summary.steps:
            flag = ""
            if s.is_hesitation:
                flag += "🤔"
            if s.is_repeat:
                flag += "🔄"
            action = "FINISH" if s.decision == "finish" else f"→ {s.agent}"
            reasoning_short = s.reasoning[:100]
            lines.append(f"{s.step}. {flag}{action}  — {reasoning_short}")
        return "\n".join(lines)

    def format_anomalies(self, summary: TraceSummary) -> str:
        """Generate a text rendering of the anomaly report."""
        if not summary.anomaly_warnings:
            return "✅ No anomalies detected"
        return "\n".join(summary.anomaly_warnings)

    def format_suggestions(self, summary: TraceSummary) -> str:
        """Generate a text rendering of Spec adjustment suggestions."""
        if not summary.spec_suggestions:
            return "✅ Current Spec needs no adjustment"
        return "\n".join(f"- {s}" for s in summary.spec_suggestions)


# ── Singleton ──

_viz_instance: Optional[TraceVisualizer] = None


def get_trace_visualizer() -> TraceVisualizer:
    global _viz_instance
    if _viz_instance is None:
        _viz_instance = TraceVisualizer()
    return _viz_instance
