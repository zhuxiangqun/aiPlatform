"""PromptOptimizer — iterative prompt optimization orchestrator.

Phase 21: composes 5 existing modules (ReActLoop + Darwin Arena + prompt_optimize
+ PipelineEngine + EvolutionRunner) into a champion-challenger optimization loop.
Fills the ``evaluator_optimizer`` pipeline mode gap in schemas_builder.py:264.

Fully event-driven — runs autonomously for N rounds, detects stagnation, stops.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.prompt_optimizer")


def _load_yml(path: str) -> Dict[str, Any]:
    import yaml
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_optimization_config(agent_id: str) -> Dict[str, Any]:
    """Load optimization config from ~/.aiplat/optimizations/{agent_id}.yaml"""
    base = os.path.expanduser(f"~/.aiplat/optimizations/{agent_id}.yaml")
    return _load_yml(base) or _load_yml(
        os.path.expanduser(f"~/.aiplat/optimizations/default.yaml")
    )


class PromptOptimizer:
    """Iterative prompt optimization orchestrator.

    Usage:
        optimizer = PromptOptimizer(agent_id="materials_chat")
        result = await optimizer.execute()
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        cfg = _load_optimization_config(agent_id)
        self.max_rounds = int(cfg.get("max_rounds", 20))
        self.stagnation_limit = int(cfg.get("stagnation_limit", 3))
        self.train_val_split = float(cfg.get("train_val_split", 0.8))
        self.eval_config = cfg.get("eval_config", {})
        self.tools = cfg.get("tools", [
            "sys_file_write", "sys_skill_call", "sys_tool_call",
        ])
        self._round_log: List[Dict[str, Any]] = []

    async def execute(self) -> Dict[str, Any]:
        """Run the full optimization loop and return result."""
        from core.harness.knowledge.evolution_runner import (
            get_champion_score, accept_or_reject,
        )
        
        champion_score = get_champion_score(self.agent_id) or 0.0
        stagnation = 0
        accepted = 0

        for rnd in range(1, self.max_rounds + 1):
            logger.info("[Optimizer] Round %d/%d, champion=%.4f", rnd, self.max_rounds, champion_score)

            # 1. Generate challenger via ReActLoop
            loop = self._build_loop(champion_score, rnd)
            result = await loop.run(
                user_input=(
                    f"执行第 {rnd} 轮优化：1. 分析评测结果 2. 修改 {self.agent_id}/AGENT.md "
                    f"3. 部署 4. 发起评测 5. 获取结果并分析。"
                    f"当前冠军分数: {champion_score:.4f}。完成后在 metadata 中输出 "
                    f'{{"challenger_score": <float>}}'
                )
            )

            # 2. Extract challenger score and prompt
            challenger_score = self._extract_score(result)
            challenger_prompt = self._read_agent_md()

            entry = {"round": rnd, "champion_score": champion_score,
                     "challenger_score": challenger_score}
            if challenger_score is None:
                entry["verdict"] = "INCOMPLETE"
                self._round_log.append(entry)
                stagnation += 1
                logger.warning("[Optimizer] Round %d: no valid score extracted", rnd)
            else:
                # 3. Champion-challenger verdict
                verdict = accept_or_reject(
                    challenger_score=challenger_score,
                    champion_score=champion_score,
                    train_val_split=self.train_val_split,
                )
                entry["verdict"] = verdict
                if verdict == "accept":
                    champion_score = challenger_score
                    stagnation = 0
                    accepted += 1
                    logger.info("[Optimizer] ✅ Round %d accepted, new champion=%.4f", rnd, champion_score)
                else:
                    stagnation += 1
                    logger.info("[Optimizer] ❌ Round %d rejected", rnd)

            self._round_log.append(entry)

            # 4. Early stop
            if stagnation >= self.stagnation_limit:
                logger.info("[Optimizer] Stopping — %d consecutive stagnant rounds", stagnation)
                break

        final_prompt = self._read_agent_md()
        return {
            "agent_id": self.agent_id,
            "final_prompt": final_prompt[:500],
            "final_score": champion_score,
            "total_rounds": rnd,
            "accepted_rounds": accepted,
            "rejection_log": self._round_log,
            "status": "completed",
        }

    # ── Phase 52: A/B experiment comparison ──

    @staticmethod
    def compare_ab(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two optimization runs (A/B experiment) and return winner.

        Returns:
            {
                "winner": "A" | "B" | "tie",
                "a_score": float,
                "b_score": float,
                "a_rounds": int,
                "b_rounds": int,
                "recommendation": str,
            }
        """
        a_score = run_a.get("final_score", 0) or 0
        b_score = run_b.get("final_score", 0) or 0
        a_rounds = run_a.get("total_rounds", 0) or 0
        b_rounds = run_b.get("total_rounds", 0) or 0

        # Efficiency bonus: fewer rounds to achieve similar score is better
        a_efficiency = a_score / max(1, a_rounds)
        b_efficiency = b_score / max(1, b_rounds)

        if a_score > b_score:
            winner = "A"
            rec = f"A wins by score ({a_score:.2f} > {b_score:.2f})"
        elif b_score > a_score:
            winner = "B"
            rec = f"B wins by score ({b_score:.2f} > {a_score:.2f})"
        elif a_efficiency > b_efficiency:
            winner = "A"
            rec = f"A wins by efficiency ({a_rounds} rounds vs {b_rounds})"
        elif b_efficiency > a_efficiency:
            winner = "B"
            rec = f"B wins by efficiency ({b_rounds} rounds vs {a_rounds})"
        else:
            winner = "tie"
            rec = "Tie — identical results"

        return {
            "winner": winner,
            "a_score": round(a_score, 3),
            "b_score": round(b_score, 3),
            "a_rounds": a_rounds,
            "b_rounds": b_rounds,
            "a_efficiency": round(a_efficiency, 3),
            "b_efficiency": round(b_efficiency, 3),
            "recommendation": rec,
        }

    # ── Private helpers ──────────────────────────────────────────

    def _build_loop(self, champion_score: float, round_num: int):
        from core.harness.execution.loop import ReActLoop

        return ReActLoop(
            system_prompt=(
                "你是一个 prompt 优化工程师。你的任务是在每一轮中："
                "1. 基于评测结果分析 badcase 模式\n"
                "2. 修改 prompt (编辑 AGENT.md)\n"
                "3. 部署代码\n"
                "4. 发起评测\n"
                "5. 获取评测结果并分析\n\n"
                "**硬性规则**：\n"
                "- 一次只专注做一件事\n"
                "- 禁止向用户提问，必须自行判断\n"
                "- 禁止早停，必须完成所有步骤\n"
                "- 遇错先分析原因，不要机械重试\n"
                "- 不要在 prompt 中写针对单个 case 的硬规则（reward hacking）\n"
                f"- 本轮完成后，在最终输出中写一行 JSON: {{\"challenger_score\": <float>}}"
            ),
            tools=self.tools,
            max_iterations=15,
            verbose=True,
        )

    @staticmethod
    def _extract_score(result: Any) -> Optional[float]:
        """Extract challenger_score from ReActLoop output metadata."""
        import json as _json
        metadata = getattr(result, "metadata", {}) or {}
        output = getattr(result, "output", {}) or {}
        raw = (
            metadata.get("challenger_score")
            or (output.get("decision", {}) or {}).get("challenger_score")
            or output.get("challenger_score")
        )
        if raw is not None:
            try:
                return float(raw)
            except (ValueError, TypeError):
                pass
        # Fallback: try to parse from output string
        text = str(getattr(result, "output", result) or "")
        try:
            m = _json.loads(_json.loads(_json.dumps(text)))
            return float(m.get("challenger_score", 0))
        except Exception:
            return None

    def _read_agent_md(self) -> str:
        """Read current AGENT.md content (bypassing cache)."""
        path = os.path.expanduser(f"~/.aiplat/agents/{self.agent_id}/AGENT.md")
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
