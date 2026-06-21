"""
PipelineAgent — YAML-driven agent that runs through PipelineEngine.

v4.0: Replaces hand-crafted execute() with config-driven pipeline stages.
      Automatically inherits ReActLoop context compression, Hook system,
      PolicyGate, and token budget tracking.

Delegates to PipelineEngine for stage orchestration instead of
implementing a custom execute() method.
"""
from typing import Any, Dict, List

from .base import BaseAgent, AgentConfig, AgentMetadata, AgentResult


class PipelineAgent(BaseAgent):
    """An agent whose behavior is entirely defined by AGENT.md stages[].
    
    Unlike MaterialsChatAgent (hand-crafted execute()), this agent
    delegates to PipelineEngine → StageRunner → ReActLoop for all
    stage execution, inheriting context compression, Hooks, and
    budget tracking automatically.
    """

    def __init__(self, config: AgentConfig, stages: List[Any] = None, **kwargs):
        super().__init__(config=config, model=config.model if hasattr(config, 'model') else None,
                         loop_type="react", **kwargs)
        self._pipeline_stages = stages or []
        self._meta = AgentMetadata(
            name="PipelineAgent",
            version="4.0.0",
            loop_type="react",
            description="YAML-driven pipeline agent (v4.0)",
        )

    async def execute(self, context):
        """Execute pipeline stages via PipelineEngine.
        
        If stages are configured, runs them through the engine.
        Otherwise falls back to the standard ReActLoop (BaseAgent.execute).
        """
        if self._pipeline_stages:
            return await self._execute_pipeline(context)
        return await super().execute(context)

    async def _execute_pipeline(self, context):
        """Run YAML-configured stages through PipelineEngine."""
        try:
            from core.harness.execution.pipeline_engine import PipelineEngine
            from core.harness.execution.engines.loop_engine import LoopEngine
            # Build a minimal pipeline config from our stages
            engine = PipelineEngine()
            for stage in self._pipeline_stages:
                # Use StageRunner to execute each stage
                runner = engine._create_stage_runner(stage)
                result = await runner.run(context)
                if not result.success:
                    engine._handle_stage_failure(stage, result)
            return AgentResult(success=True, output={"status": "completed"})
        except Exception as e:
            if not self._pipeline_stages:
                return await super().execute(context)
            return AgentResult(success=False, error=str(e))
