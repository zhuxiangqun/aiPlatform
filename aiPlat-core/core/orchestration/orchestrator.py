"""
Orchestrator (Phase 5.2 - plan only).

Design:
- Input: agent_id, user messages, and lightweight context
- Output: OrchestratorPlan (steps + explain + version)

Rules:
- This module must remain side-effect free: do NOT execute tools/skills.
- LLM usage is allowed for planning, via sys_llm_generate syscall.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.syscalls.llm import sys_llm_generate


@dataclass
class PlanStep:
    """A single plan step (machine-friendly)."""

    step: int
    action: str
    kind: str = "instruction"  # instruction|tool|skill|llm
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorPlan:
    """Orchestrator output."""

    version: str = "5.2"
    explain: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "explain": self.explain,
            "created_at": self.created_at,
            "steps": [
                {"step": s.step, "action": s.action, "kind": s.kind, "args": s.args or {}}
                for s in self.steps
            ],
            "metadata": self.metadata or {},
        }


class Orchestrator:
    """
    Phase 5.2 minimal orchestrator.

    It asks an LLM for a plan in strict JSON format. If parsing fails, returns a fallback plan.
    """

    async def plan(
        self,
        *,
        agent_id: str,
        model: Any,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorPlan:
        task = ""
        if messages:
            task = str(messages[-1].get("content", "") or "")

        prompt = (
            "你是编排器（Orchestrator）。你只能输出执行计划，不允许执行任何工具/技能。\n"
            "请根据用户任务生成 JSON 计划，格式必须严格符合：\n"
            "{\n"
            '  "explain": "为什么这样拆解（简短）",\n'
            '  "steps": [\n'
            '    {"step": 1, "kind": "instruction", "action": "..."},\n'
            '    {"step": 2, "kind": "tool", "action": "tool_name", "args": {...}},\n'
            '    {"step": 3, "kind": "skill", "action": "skill_name", "args": {...}}\n'
            "  ]\n"
            "}\n"
            "约束：\n"
            "- steps 不超过 8 条\n"
            "- kind 只能是 instruction/tool/skill/llm\n"
            "- tool/skill 步骤只描述，不执行\n"
            f"\nAgent: {agent_id}\n"
            f"Task: {task}\n"
        )

        try:
            resp = await sys_llm_generate(model, prompt, trace_context=trace_context)
            raw = (getattr(resp, "content", "") or "").strip()
            data = json.loads(raw)
            explain = str(data.get("explain", "") or "")
            steps_in = data.get("steps") or []
            steps: List[PlanStep] = []
            for i, s in enumerate(steps_in, start=1):
                if not isinstance(s, dict):
                    continue
                steps.append(
                    PlanStep(
                        step=int(s.get("step") or i),
                        kind=str(s.get("kind") or "instruction"),
                        action=str(s.get("action") or ""),
                        args=s.get("args") if isinstance(s.get("args"), dict) else {},
                    )
                )
            if not steps:
                raise ValueError("empty plan")

            return OrchestratorPlan(
                explain=explain,
                steps=steps[:8],
                metadata={
                    "agent_id": agent_id,
                    "context_keys": sorted(list((context or {}).keys()))[:50],
                },
            )
        except Exception as e:
            # Fallback: 2-step minimal plan
            return OrchestratorPlan(
                explain=f"Fallback plan (parse_failed): {e}",
                steps=[
                    PlanStep(step=1, kind="instruction", action="理解任务与约束"),
                    PlanStep(step=2, kind="instruction", action="按既有 LoopEngine 执行（无额外编排）"),
                ],
                metadata={"agent_id": agent_id, "fallback": True},
            )

