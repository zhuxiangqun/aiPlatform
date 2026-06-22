"""
aiplat.pipeline — 自定义流水线编排 (Level 2)

Usage:
    pipeline = Pipeline()
    pipeline.add_stage("retrieve", skill="knowledge_retrieval")
    pipeline.add_stage("analyze", agent=my_agent)
    pipeline.add_stage("report", skill="text_generation")
    result = await pipeline.run(input_data)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .agent import Agent


class PipelineStage:
    """单个流水线阶段。"""

    def __init__(
        self,
        name: str,
        *,
        skill: str = "",
        agent: Optional[Agent] = None,
        depends_on: Optional[List[str]] = None,
    ):
        self.name = name
        self.skill = skill
        self.agent = agent
        self.depends_on = depends_on or []
        self.output: Optional[Dict[str, Any]] = None

    async def run(self, input_data: Any, upstream_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """执行此阶段。"""
        if self.agent:
            prompt = f"Stage '{self.name}':\nInput: {input_data}\n"
            if upstream_outputs:
                prompt += f"\nUpstream results:\n{json.dumps(upstream_outputs, ensure_ascii=False, indent=2)}"
            return self.agent.execute(prompt)
        elif self.skill:
            # Use a temporary agent to call the skill
            temp_agent = Agent(name=f"pipeline-{self.name}", model=self.agent._model if self.agent else "")
            temp_agent.bind_skill(self.skill)
            prompt = f"Execute skill '{self.skill}' with: {input_data}"
            return temp_agent.execute(prompt)
        return {"ok": False, "error": "No agent or skill configured"}


class Pipeline:
    """自定义流水线编排器。

    Usage:
        pipeline = Pipeline()
        pipeline.add_stage("retrieve", skill="knowledge_retrieval")
        pipeline.add_stage("analyze", agent=my_agent)
        pipeline.add_stage("report", skill="text_generation")
        result = await pipeline.run({"query": "分析数据"})
    """

    def __init__(self):
        self._stages: List[PipelineStage] = []
        self._results: Dict[str, Dict[str, Any]] = {}

    def add_stage(
        self,
        name: str,
        *,
        skill: str = "",
        agent: Optional[Agent] = None,
        depends_on: Optional[List[str]] = None,
    ) -> Pipeline:
        """添加一个阶段。

        Args:
            name: 阶段名称
            skill: 使用的 Skill 名称
            agent: 使用的 Agent 实例
            depends_on: 依赖的前置阶段名称列表
        """
        if not skill and not agent:
            raise ValueError("Either skill or agent must be specified")
        if name in {s.name for s in self._stages}:
            raise ValueError(f"Stage '{name}' already exists")
        self._stages.append(PipelineStage(name, skill=skill, agent=agent, depends_on=depends_on))
        return self

    async def run(self, input_data: Any = None) -> Dict[str, Any]:
        """执行流水线。

        Args:
            input_data: 初始输入数据

        Returns:
            {"stages": {...}, "final": stage_name}
        """
        completed: set = set()
        pending = list(self._stages)
        results: Dict[str, Any] = {}

        while pending:
            # Find stages whose dependencies are all satisfied
            ready = [s for s in pending if all(d in completed for d in s.depends_on)]
            if not ready:
                raise RuntimeError(f"Pipeline deadlock: pending stages {[s.name for s in pending]}")

            # Run all ready stages (could be parallelized in future)
            for stage in ready:
                upstream = {d: results.get(d, {}) for d in stage.depends_on}
                results[stage.name] = await stage.run(input_data, upstream)
                completed.add(stage.name)
                pending.remove(stage)

        self._results = results
        return {
            "stages": results,
            "final": self._stages[-1].name if self._stages else "",
        }

    def __repr__(self) -> str:
        stages = " → ".join(s.name for s in self._stages)
        return f"Pipeline({stages})"


# ── Stdlib import (used in PipelineStage.run) ──────────────────────────────

import json  # noqa: E402
