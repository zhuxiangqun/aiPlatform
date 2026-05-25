"""
PipelineGraph — LangGraph representation of a Builder pipeline.

Phase B: Produces graph-structured trace events for pipeline execution.
Builds a sub-graph for each invocation and delegates stage execution to
the existing _exec_stage callback (replaces _run_stages_from for-loop).

Usage:
  graph = PipelineGraph(stages)
  state = await graph.execute(state, start_idx=0, exec_fn=engine._exec_stage)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig, PipelineState
from .core import GraphBuilder, CompiledGraph, GraphConfig, GraphState


class PipelineGraph:
    """Execute a pipeline subset as a named graph for trace observability."""

    def __init__(self, stages: List[PipelineStageConfig], name: str = "pipeline"):
        self._stages = list(stages)
        self._name = name

    async def execute(
        self,
        state: PipelineState,
        start_idx: int = 0,
        exec_fn: Optional[Callable] = None,
    ) -> PipelineState:
        if exec_fn is None:
            raise ValueError("exec_fn is required")

        stages_to_run = list(range(start_idx, len(self._stages)))
        if not stages_to_run:
            state["phase"] = "done"
            return state

        builder = GraphBuilder(name=f"{self._name}#{start_idx}")

        # One node per stage
        for idx in stages_to_run:
            stage = self._stages[idx]
            builder.add_node(
                f"stage_{idx}_{stage.id}",
                self._make_node_func(idx, stage),
            )

        builder.set_entry_point(f"stage_{stages_to_run[0]}_{self._stages[stages_to_run[0]].id}")

        # Linear edges: stage_i → stage_{i+1}
        for i in range(len(stages_to_run) - 1):
            ci = stages_to_run[i]
            ni = stages_to_run[i + 1]
            builder.add_edge(
                f"stage_{ci}_{self._stages[ci].id}",
                f"stage_{ni}_{self._stages[ni].id}",
            )

        last_r = stages_to_run[-1]
        builder.add_end_point(f"stage_{last_r}_{self._stages[last_r].id}")
        compiled = builder.build()

        graph_state: GraphState = {
            "messages": [],
            "context": {
                "_pipeline_state": dict(state),
                "_start_idx": start_idx,
            },
            "current_step": "",
            "step_count": 0,
            "max_steps": len(stages_to_run),
            "metadata": {
                "_exec_fn": exec_fn,
                "graph_name": self._name,
            },
            "errors": [],
            "results": {},
        }

        result = await compiled.execute(graph_state, GraphConfig(max_steps=len(stages_to_run)))
        final_state = result.get("context", {}).get("_pipeline_state", state)
        return dict(final_state)

    @staticmethod
    def _make_node_func(idx: int, stage: PipelineStageConfig) -> Callable:
        async def _node(state: GraphState) -> GraphState:
            exec_fn = state.get("metadata", {}).get("_exec_fn")
            if exec_fn is None:
                return state
            pipeline_state = state.get("context", {}).get("_pipeline_state", {})
            pipeline_state["_current_stage_idx"] = idx
            result_state = await exec_fn(stage, pipeline_state)
            state.setdefault("context", {})["_pipeline_state"] = result_state
            state["context"][f"stage_{stage.id}"] = result_state.get(stage.output_artifact)
            state["context"]["phase"] = result_state.get("phase", "")
            state.setdefault("metadata", {})["last_stage"] = stage.id
            return state
        return _node

