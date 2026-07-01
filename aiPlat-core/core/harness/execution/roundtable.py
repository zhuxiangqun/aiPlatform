"""
Roundtable Mode — multi-agent equal collaborative discussion (Octo Skill 2).
All agents see each other's outputs in each round, building consensus.
Not adversarial (unlike debate.py) — agents collaborate, not compete.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.roundtable")


async def run_roundtable(
    *,
    topic: str,
    agent_names: List[str],
    run_agent: callable,  # async (agent_name: str, prompt: str, model: str) -> str
    max_rounds: int = 3,
    facilitator_prompt: str = "",
) -> Dict[str, Any]:
    """Multi-agent equal discussion: all agents speak in each round, seeing all prior outputs.

    Args:
        topic: The discussion topic / problem statement
        agent_names: List of participating agent names (2+)
        run_agent: Async function (agent_name, prompt, model) -> output
        max_rounds: Maximum discussion rounds
        facilitator_prompt: Optional facilitator instructions for synthesis

    Returns:
        {rounds: int, transcript: [{round, agent, output}], synthesis: str}
    """
    if len(agent_names) < 2:
        return {"rounds": 0, "transcript": [], "synthesis": "Need 2+ agents"}

    transcript: List[Dict[str, Any]] = []
    all_outputs: Dict[str, List[str]] = {name: [] for name in agent_names}

    for round_num in range(1, max_rounds + 1):
        round_context = _build_round_context(round_num, topic, transcript, agent_names)
        round_speakers: List[Dict[str, Any]] = []

        for name in agent_names:
            prompt = round_context + f"\n\n现在是 {name} 的发言轮次。请基于之前的讨论，发表你的观点。可以赞同、补充、质疑其他观点，但保持建设性。"
            try:
                output = await run_agent(name, prompt, "")
                all_outputs[name].append(output)
                round_speakers.append({"round": round_num, "agent": name, "output": output[:2000]})
            except Exception as e:
                round_speakers.append({"round": round_num, "agent": name, "output": f"[ERROR] {e}"})

        transcript.extend(round_speakers)

        # Check for natural convergence (all agents start with "同意" / "Agreed" in last round)
        if round_num >= 2:
            agreements = sum(1 for s in round_speakers if s["output"].strip()[:4] in ("同意", "赞同", "Agre", "I ag"))
            if agreements >= len(agent_names) * 0.6:
                logger.info("Roundtable converged at round %d", round_num)
                break

    # Synthesis: concatenate final round outputs
    synthesis_parts = []
    for name in agent_names:
        if all_outputs[name]:
            synthesis_parts.append(f"### {name}\n{all_outputs[name][-1][:1500]}")
    synthesis = "\n\n".join(synthesis_parts)

    logger.info("Roundtable: %d rounds, %d agents, %d total utterances",
                 round_num, len(agent_names), len(transcript))

    return {
        "rounds": round_num,
        "transcript": transcript,
        "synthesis": synthesis,
        "converged": round_num < max_rounds,
    }


def _build_round_context(
    round_num: int,
    topic: str,
    transcript: List[Dict[str, Any]],
    agent_names: List[str],
) -> str:
    """Build the context prompt for the current round."""
    parts = [
        f"## 圆桌讨论 (Roundtable) — 第 {round_num} 轮",
        f"\n**讨论主题**: {topic}",
        f"\n**参与方**: {', '.join(agent_names)}",
        f"\n**规则**: 每位参与者平等发言。你可以赞同、补充或质疑其他观点，保持建设性。目标是达成共识或产出综合方案。",
    ]

    if transcript:
        parts.append("\n### 此前讨论记录")
        for entry in transcript[-10:]:  # Last 10 utterances
            parts.append(f"\n**{entry['agent']}** (第{entry['round']}轮):\n{entry['output'][:500]}")

    return "\n".join(parts)
