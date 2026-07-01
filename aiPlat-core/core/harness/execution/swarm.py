"""
Swarm Mode — multi-agent parallel execution with Darwin Arena selection (Octo Skill 6).
Same task → N agents execute independently → Arena scores → best output wins.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.swarm")


async def run_swarm(
    *,
    task: str,
    agent_names: List[str],
    run_agent: callable,  # async (agent_name: str, task: str, model: str) -> str
    arena_threshold: float = 0.6,
    select_top: int = 1,
) -> Dict[str, Any]:
    """Distribute same task to N agents, run independently, select best.

    Args:
        task: The task description
        agent_names: List of agent names to compete
        run_agent: Async function (agent_name, task, model) -> output string
        arena_threshold: Minimum Elo score to select a winner
        select_top: Number of top agents to merge (default: 1 = single winner)

    Returns:
        {winner: str, scores: {agent: score}, outputs: {agent: output}, merged: str}
    """
    if len(agent_names) < 2:
        return {"winner": agent_names[0] if agent_names else "",
                "outputs": {}, "scores": {}, "merged": ""}

    # 1. Execute all agents in parallel
    results: Dict[str, str] = {}
    import asyncio

    async def _run_one(name: str) -> tuple[str, str]:
        try:
            output = await run_agent(name, task, "")
            return name, output
        except Exception as e:
            return name, f"[ERROR] {e}"

    tasks = [_run_one(name) for name in agent_names]
    for coro in asyncio.as_completed(tasks):
        name, output = await coro
        results[name] = output

    # 2. Score outputs using Darwin Arena (simplified: length + diversity heuristic)
    scores: Dict[str, float] = {}
    for name, output in results.items():
        # Heuristic scoring: relevance (non-empty), specificity (length), structure (headers)
        score = 1.0
        if not output or output.startswith("[ERROR]"):
            score = 0.0
        else:
            # Prefer structured output (has headings, bullet points, code blocks)
            structure_bonus = 0.0
            if "##" in output or "###" in output:
                structure_bonus += 0.2
            if "```" in output:
                structure_bonus += 0.1
            if "- " in output or "* " in output:
                structure_bonus += 0.1
            # Prefer substantive output (> 200 chars)
            length_bonus = min(0.3, len(output) / 1000)
            score = 0.5 + structure_bonus + length_bonus
        scores[name] = round(min(score, 1.0), 2)

    # 3. Select top N winners
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winners = [name for name, sc in ranked[:select_top] if sc >= arena_threshold]

    if not winners:
        winners = [ranked[0][0]] if ranked else []

    # 4. Merge: concatenate or use best
    merged = ""
    if len(winners) > 1 and select_top > 1:
        parts = [f"### {w}\n{results.get(w, '')[:1500]}" for w in winners]
        merged = "\n\n".join(parts)
    else:
        merged = results.get(winners[0], "") if winners else ""

    logger.info("Swarm: %d agents, winner=%s (score=%.2f)", len(agent_names), winners[0] if winners else "none", scores.get(winners[0], 0) if winners else 0)

    return {
        "winner": winners[0] if winners else "",
        "winners": winners,
        "scores": scores,
        "outputs": results,
        "merged": merged,
    }
