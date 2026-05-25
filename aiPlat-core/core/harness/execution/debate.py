"""
Agent Debate Loop — adversarial multi-agent reasoning with convergence detection.

Inspired by TradingAgents' Bull/Bear researcher debate pattern.
General-purpose: works with any 2+ agents configured via PipelineStageConfig.

Caller: PipelineEngine._exec_stage when stage.debate_config is set.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.schemas_builder import PipelineStageConfig

logger = logging.getLogger("aiplat.debate")


class DebateState:
    """Tracks debate state across rounds."""

    def __init__(self, positions: List[str] = None):
        self.positions = positions or []
        self.round_outputs: List[Dict[str, Any]] = []
        self.rounds: int = 0
        self.converged: bool = False
        self.stability_counter: int = 0
        self._last_positions: List[str] = []

    def record_round(self, side: str, output: Any) -> None:
        self.rounds += 1
        self.round_outputs.append({"side": side, "output": output, "ts": time.time()})

    def check_stability(self, current_outputs: Dict[str, str], threshold: int = 2) -> bool:
        """Check if debate has converged (positions unchanged for N rounds)."""
        current_positions = sorted(
            f"{k}:{str(v)[:200]}" for k, v in current_outputs.items()
        )
        if current_positions == self._last_positions:
            self.stability_counter += 1
            if self.stability_counter >= threshold:
                self.converged = True
                return True
        else:
            self.stability_counter = 0
        self._last_positions = current_positions
        return False


async def run_agent_debate(
    agent_configs: List[Dict[str, Any]],
    debate_info: Dict[str, Any],
    *,
    max_rounds: int = 8,
    stability_threshold: int = 2,
    run_agent: callable,  # async (agent_name, prompt, model) -> str
    manager_agent: Dict[str, Any] = None,  # final synthesis
    run_manager: callable = None,  # async (agent_name, prompt, model, debate_outputs) -> str
) -> Dict[str, Any]:
    """Run an adversarial debate among N agents.

    Args:
        agent_configs: List of {name, prompt_template, model, side} dicts
        debate_info: {ticker, date, context) for prompt templates
        max_rounds: Maximum debate rounds before forced resolution
        stability_threshold: Consecutive stable rounds to declare convergence
        run_agent: Async function (agent_name, prompt, model) -> str
        manager_agent: {name, prompt_template, model} for final synthesis
        run_manager: Async function (agent_name, prompt, model, debate_outputs) -> str

    Returns:
        {rounds, converged, outputs: {side: output}, manager_decision}
    """
    state = DebateState()
    outputs: Dict[str, str] = {}

    for round_num in range(max_rounds):
        round_outputs = {}
        for cfg in agent_configs:
            # Build prompt with opponent's previous round outputs visible
            prompt = cfg["prompt_template"].format(**debate_info)
            if round_num > 0 and outputs:
                opponent_outputs = {k: v for k, v in outputs.items() if k != cfg.get("side")}
                prompt += _debate_context_block(opponent_outputs, round_num)

            result = await run_agent(cfg["name"], prompt, cfg.get("model"))
            side = cfg.get("side", cfg["name"])
            round_outputs[side] = str(result)
            state.record_round(side, result)

        outputs = round_outputs

        if state.check_stability(outputs, stability_threshold):
            logger.info("Debate converged after %d rounds", round_num + 1)
            break

    # Manager synthesis
    manager_decision = None
    if manager_agent and run_manager:
        prompt = manager_agent["prompt_template"].format(**debate_info)
        prompt += _debate_summary_block(outputs)
        manager_decision = await run_manager(
            manager_agent["name"], prompt, manager_agent.get("model")
        )

    return {
        "rounds": state.rounds,
        "converged": state.converged,
        "outputs": outputs,
        "manager_decision": str(manager_decision) if manager_decision else None,
    }


def _debate_context_block(
    opponent_outputs: Dict[str, str], round_num: int
) -> str:
    """Format opponent outputs for the next debate round."""
    parts = [f"\n\n## Debate Round {round_num} — Opposing Views\n"]
    for side, output in opponent_outputs.items():
        parts.append(f"### {side} argues:\n{str(output)[:3000]}\n")
    parts.append("\nAddress these points in your response. Counter specific arguments where you disagree.\n")
    return "\n".join(parts)


def _debate_summary_block(outputs: Dict[str, str]) -> str:
    """Format full debate record for the manager."""
    parts = ["\n\n## Full Debate Record\n"]
    for side, output in outputs.items():
        parts.append(f"### {side}\n{str(output)[:3000]}\n")
    parts.append("\nSynthesize these views into a single decision. Which side has the stronger arguments?\n")
    return "\n".join(parts)


def parse_debate_rating(output: str, ratings: Dict[str, int]) -> Optional[Tuple[str, int]]:
    """Parse rating from debate output for structured decision comparison.
    
    Args:
        output: Agent output text
        ratings: {rating_label: numeric_value} mapping, e.g., {'Buy': 5, 'Hold': 3, 'Sell': 1}
    Returns:
        (label, value) or None if no rating found
    """
    for label, value in sorted(ratings.items(), key=lambda x: -len(x[0])):
        if label.lower() in str(output).lower():
            return (label, value)
    return None


__all__ = ["run_agent_debate", "DebateState", "parse_debate_rating"]
