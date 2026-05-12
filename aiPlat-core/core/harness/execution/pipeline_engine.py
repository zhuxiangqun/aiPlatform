"""
PipelineEngine -- generic team execution engine.

Canonical location: harness/execution/pipeline_engine.py (CLAUDE.md §5.23).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone

from core.schemas_builder import (
    BuilderSessionPhase,
    AgentConfidence,
    AgentDecision,
    IssueSeverity,
    TestRecommendation,
    Issue,
    PipelineConfig,
    PipelineStageConfig,
    AgentOutput,
)

from .langgraph.stage_runner import StageRunner


class PipelineState(TypedDict, total=False):
    """Pipeline execution state.

    All artifact keys (e.g., 'prd', 'architecture', 'frontend_code', etc.)
    are accessed via config.stages[i].output_artifact and stored dynamically
    in this dict at runtime. The TypedDict only declares framework-level fields.
    Artifact keys are entirely config-driven per CLAUDE.md §5.29.
    """
    session_id: str
    phase: str
    description: str
    iteration: int
    qa_retry: int
    max_iterations: int
    tokens_used: int
    tokens_budget: int
    _prev_failing_ids: List[str]
    _stagnation_count: int
    _bug_fixes: int
    _auto_approve: bool
    _current_stage_idx: int
    _reject_feedback: str
    issues: List[Dict[str, Any]]
    error: str
    output_dir: str
    context: Dict[str, Any]


class PipelineEngine:
    def __init__(self, config: PipelineConfig, model: Any = None, skill_loader: Any = None):
        self._config = config
        self._model = model
        if self._model is None:
            self._model = self._load_default_model()
        self._skill_loader = skill_loader
        self._stage_runner = StageRunner(model=self._model, pipeline_config=config)

    @staticmethod
    def _load_default_model() -> Any:
        import os
        from core.harness.utils.model_injection import create_selected_adapter
        model_name = os.getenv("AIPLAT_BUILDER_MODEL", "deepseek-chat")
        return create_selected_adapter(model_name=model_name)

    async def initialize(self, project_id: str, requirement: str,
                         prd_data: Optional[Dict] = None) -> PipelineState:
        output_dir = self._output_root(project_id)
        os.makedirs(output_dir, exist_ok=True)
        state: PipelineState = {
            "session_id": project_id,
            "phase": BuilderSessionPhase.executing.value,
            "description": requirement,
            "iteration": 0, "qa_retry": 0, "max_iterations": 100,
            "tokens_used": 0, "tokens_budget": self._config.max_tokens_per_run,
            "output_dir": output_dir, "issues": [], "context": {},
        }
        if prd_data:
            # Use first stage's output_artifact as the PRD key (config-driven)
            prd_key = self._config.stages[0].output_artifact if self._config.stages else ""
            state[prd_key] = prd_data
        return await self._run_stages_from(0, state)

    async def approve(self, state: PipelineState) -> PipelineState:
        state = dict(state)
        state["phase"] = BuilderSessionPhase.executing.value
        idx = state.get("_current_stage_idx", 0)
        # If current HITL stage has generate_test_plan, test plan means "same stage resume"
        if idx >= 0 and idx < len(self._config.stages):
            cur_stage = self._config.stages[idx]
            if cur_stage.generate_test_plan and state.get("phase") == (cur_stage.hitl_phase or ""):
                result = await self._run_stages_from(idx, state)
                await self._consolidate_auto_pipeline(result)
                return result
        result = await self._run_stages_from(idx + 1, state)
        await self._consolidate_auto_pipeline(result)
        return result

    def _upstream_output(self, state: PipelineState, include_outputs: set = set()) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for s in self._config.stages:
            if not include_outputs or s.output_artifact in include_outputs:
                val = state.get(s.output_artifact)
                if isinstance(val, dict) and val:
                    result[s.output_artifact] = val
        return result

    def _find_hitl_stage_index(self, state: PipelineState) -> int:
        idx = state.get("_current_stage_idx")
        if idx is not None and 0 <= idx < len(self._config.stages):
            return idx
        phase = state.get("phase", "")
        for i, s in enumerate(self._config.stages):
            if (s.hitl_phase and s.hitl_phase == phase) or (s.hitl_after_phase and s.hitl_after_phase == phase):
                return i
        return 0

    async def reject(self, state: PipelineState, feedback: str) -> PipelineState:
        state = dict(state)
        state["_reject_feedback"] = feedback
        idx = self._find_hitl_stage_index(state)
        for i in range(idx, len(self._config.stages)):
            state[self._config.stages[i].output_artifact] = None
            state.pop(f"_stage_{self._config.stages[i].id}_done", None)
            if self._config.stages[i].generate_test_plan:
                state[self._config.stages[i].test_result_key] = None
        state["phase"] = BuilderSessionPhase.executing.value
        state["qa_retry"] = 0
        state["_stagnation_count"] = 0
        state["tokens_used"] = 0
        state.pop("error", None)
        state.pop("_last_action_reason", None)
        return await self._run_stages_from(idx, state)

    async def rollback(self, state: PipelineState, stage_id: str) -> PipelineState:
        state = dict(state)
        target_idx = -1
        for i, s in enumerate(self._config.stages):
            if s.id == stage_id or s.output_artifact == stage_id:
                target_idx = i
                break
        if target_idx < 0:
            return state
        for i in range(target_idx, len(self._config.stages)):
            state[self._config.stages[i].output_artifact] = None
            state.pop(f"_stage_{self._config.stages[i].id}_done", None)
            if self._config.stages[i].generate_test_plan:
                state[self._config.stages[i].test_result_key] = None
        state["phase"] = BuilderSessionPhase.executing.value
        state["_stagnation_count"] = 0
        state["qa_retry"] = 0
        state["tokens_used"] = 0
        state.pop("error", None)
        return await self._run_stages_from(target_idx, state)

    def get_stages(self) -> List[PipelineStageConfig]:
        """Public getter for pipeline stages. Platform uses this instead of
        accessing engine._config.stages directly."""
        return list(self._config.stages)

    async def resume_from(self, start_idx: int, state: PipelineState) -> PipelineState:
        """Public wrapper for _run_stages_from. Platform uses this instead of
        calling the private method directly."""
        return await self._run_stages_from(start_idx, state)

    async def _run_stages_from(self, start_idx: int, state: PipelineState) -> PipelineState:
        state = dict(state)
        stages = self._config.stages
        # Compute dependency layers for parallel execution (P0-3)
        layers = self._compute_dependency_layers(stages, start_idx)
        for layer in layers:
            if not layer:
                continue
            # Check if pipeline is already failed before executing layer
            if state.get("phase") == BuilderSessionPhase.failed.value:
                state.setdefault("_last_action_reason", "phase_failed")
                break
            # Execute all stages in this layer in parallel
            results = await asyncio.gather(
                *[self._exec_single_stage(stages[i], i, state) for i in layer],
                return_exceptions=True,
            )
            # Merge results and check for HITL
            paused = False
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    idx = layer[i]
                    state["_last_action_reason"] = f"stage_{idx}_error:{result}"
                    continue
                if result is None:
                    continue
                r_state, r_paused = result
                state.update(r_state)
                if r_paused:
                    paused = True
            if paused:
                return state

        if state.get("phase") == BuilderSessionPhase.executing.value:
            state["phase"] = BuilderSessionPhase.done.value
        self._snapshot(state, "final_state")
        # Crystallize successful pipeline execution into a reusable Skill
        await self._crystallize_skill(state)
        # Notify PushManager on pipeline completion
        try:
            from core.harness.feedback_loops.push import get_push_manager
            pm = get_push_manager()
            if pm:
                pm.push(event={"type": "pipeline_complete", "phase": state.get("phase"),
                    "session_id": state.get("session_id")})
        except Exception:
            pass
        return state

    def _compute_dependency_layers(
        self, stages: List[PipelineStageConfig], start_idx: int
    ) -> List[List[int]]:
        """Topologically sort stages into dependency layers for parallel execution."""
        artifact_to_idx: Dict[str, int] = {}
        for i, s in enumerate(stages):
            if s.output_artifact:
                artifact_to_idx[s.output_artifact] = i

        in_degree: Dict[int, int] = {}
        graph: Dict[int, List[int]] = {}
        for i in range(start_idx, len(stages)):
            graph[i] = []
            in_degree[i] = 0

        for i in range(start_idx, len(stages)):
            s = stages[i]
            deps = s.depends_on if s.depends_on else []
            if not deps and i > start_idx:
                # Default: depends on previous stage
                deps = [stages[i - 1].output_artifact] if stages[i - 1].output_artifact else []
            for dep_artifact in deps:
                dep_idx = artifact_to_idx.get(dep_artifact)
                if dep_idx is not None and dep_idx < i:
                    graph.setdefault(dep_idx, []).append(i)
                    in_degree[i] = in_degree.get(i, 0) + 1

        layers: List[List[int]] = []
        remaining = set(range(start_idx, len(stages)))
        while remaining:
            current = sorted([i for i in remaining if in_degree.get(i, 0) == 0])
            if not current:
                # Cycle or all remaining have unsatisfied deps; sequential fallback
                current = sorted(remaining)
            layers.append(current)
            for n in current:
                remaining.discard(n)
                for child in graph.get(n, []):
                    in_degree[child] = max(0, in_degree.get(child, 1) - 1)
            if current == sorted(remaining):
                remaining.clear()

        return layers

    async def _exec_single_stage(
        self, stage: PipelineStageConfig, idx: int, state: PipelineState
    ) -> Optional[Tuple[PipelineState, bool]]:
        """Execute a single pipeline stage. Returns (updated_state, is_paused)."""
        import copy
        local_state = dict(state)
        local_state["_current_stage_idx"] = idx
        graph_trace: List[Dict] = []
        local_state.setdefault("_graph_trace", [])
        local_state["_graph_trace"] = list(local_state["_graph_trace"])  # shallow copy for parallel safety

        # Skip if already done
        existing = local_state.get(stage.output_artifact)
        if existing and (not isinstance(existing, dict) or len(existing) > 0):
            if not (stage.retry_target_id and not self._check_done(stage, local_state)):
                graph_trace.append({"node": stage.id, "status": "skipped", "reason": f"{stage.output_artifact}_exists", "ts": time.time()})
                local_state[f"_stage_{stage.id}_done"] = True
                local_state["_last_action_reason"] = f"skip:{stage.output_artifact}_exists"
                return local_state, False

        graph_trace.append({"node": stage.id, "status": "started", "ts": time.time()})
        local_state["_graph_trace"] = local_state.get("_graph_trace", []) + graph_trace

        # Test plan generation
        if stage.generate_test_plan and not local_state.get(stage.output_artifact):
            local_state = await self._gen_test_plan(stage, local_state)
            if local_state.get("phase") == stage.hitl_phase:
                graph_trace.append({"node": stage.id, "status": "paused", "phase": stage.hitl_phase, "ts": time.time()})
                self._snapshot(local_state, f"stage_{stage.id}_test_plan")
                return local_state, True

        # Test execution
        if stage.generate_test_plan and local_state.get(stage.output_artifact) and not local_state.get("_qa_done"):
            local_state = await self._exec_test_runner(stage, local_state)
            self._snapshot(local_state, f"stage_{stage.id}_output")
            local_state[f"_stage_{stage.id}_done"] = True
            graph_trace.append({"node": stage.id, "status": "completed", "ts": time.time()})
            return local_state, False

        # Normal stage execution (includes code generation via ReActLoop)
        local_state = await self._exec_stage(stage, local_state)
        local_state[f"_stage_{stage.id}_done"] = True
        artifact = local_state.get(stage.output_artifact)
        cfg_fields = getattr(stage, 'coverage_trace_fields', None) or {}
        comp_key = cfg_fields.get("components_key", "components")
        files_key = cfg_fields.get("files_key", "files")
        tests_key = cfg_fields.get("test_cases_key", "test_cases")
        graph_trace.append({"node": stage.id, "status": "completed", "ts": time.time(), "metrics": {
            "artifact_fields": list(artifact.keys())[:5] if isinstance(artifact, dict) else [],
            "components_count": len(artifact.get(comp_key, [])) if isinstance(artifact, dict) else 0,
            "files_count": len(artifact.get(files_key, [])) if isinstance(artifact, dict) else 0,
            "test_cases_count": len(artifact.get(tests_key, [])) if isinstance(artifact, dict) else 0,
        }})

        if local_state.get("phase") == BuilderSessionPhase.failed.value:
            graph_trace.append({"node": stage.id, "status": "failed", "reason": "phase_failed", "ts": time.time()})
            return local_state, True

        # HITL checks
        if stage.hitl_after_execute and local_state.get(stage.output_artifact):
            local_state["phase"] = stage.hitl_after_phase or BuilderSessionPhase.paused.value
            graph_trace.append({"node": stage.id, "status": "paused", "phase": local_state["phase"], "ts": time.time()})
            self._snapshot(local_state, f"stage_{stage.id}_done")
            return local_state, True

        if stage.hitl:
            hitl_phase = stage.hitl_phase or BuilderSessionPhase.paused.value
            local_state["phase"] = hitl_phase
            graph_trace.append({"node": stage.id, "status": "paused", "phase": hitl_phase, "ts": time.time()})
            self._snapshot(local_state, f"stage_{stage.id}_done")
            return local_state, True

        return local_state, False

    async def _exec_stage(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        """Generic stage execution. Uses agent_type from PipelineStageConfig:
        - non-react (conversational, rag, reflection, ...): routes through
          core_chat() which auto-activates Memory/Trace/Skills
        - react (default) or uses_code_skill: uses StageRunner for
          direct ReAct loop execution with FILE: parsing support
        """
        state = dict(state)
        used = state.get("tokens_used", 0)
        budget = state.get("tokens_budget", self._config.max_tokens_per_run or 100000)
        if used >= budget:
            state["error"] = f"token_budget_exhausted ({used}/{budget})"
            state["_last_action_reason"] = "budget_exhausted"
            return state
        state["iteration"] = state.get("iteration", 0) + 1
        print(f"    [stage] {stage.id} (iter {state['iteration']}, {used}/{budget} tokens)")
        prompt = self._build_prompt(stage, state)

        # ── Route: agent_type drives execution path ──
        agent_type = getattr(stage, 'agent_type', '') or 'react'

        # Sandbox path: execute stage in isolated subprocess
        if getattr(stage, 'sandbox', False):
            from core.harness.execution.sandbox import StageSandbox
            sb = StageSandbox(timeout_seconds=getattr(stage, 'stage_timeout_seconds', 600))
            sandbox_result = await sb.execute(
                stage_config={"id": stage.id, "agent_id": stage.agent_id, "agent_type": agent_type},
                state_snapshot=dict(state),
            )
            if sandbox_result.success:
                result_text = sandbox_result.output
            else:
                state["error"] = sandbox_result.error or "sandbox_execution_failed"
                state["_last_action_reason"] = "sandbox_failed"
                return state
        elif not stage.uses_code_skill and agent_type != 'react':
            # Intent-driven path: core_chat() auto-activates Memory/Trace/Skills
            import uuid as _uuid
            from core.api.intents import core_chat, ChatContext
            result = await core_chat(ChatContext(
                agent_name=stage.agent_id,
                session_id=f"{state.get('project_id', 'pipeline')}_stage_{stage.id}",
                user_input=prompt,
            ))
            result_text = result.reply
            state["_stage_trace_id"] = result.trace_id
        else:
            # ReAct loop path (code generation, default): direct StageRunner
            result_text = await self._stage_runner.run(prompt, state, stage=stage)
        state["step_count"] = state.get("step_count", 0)  # carried from stage_runner via shared state dict
        parsed = self._parse_output(result_text)
        if stage.uses_code_skill:
            files = self._extract_files_delimiter(str(result_text))
            if files:
                state[stage.output_artifact] = {"files": files}
            else:
                state[stage.output_artifact] = {"raw_output": str(result_text)}
            state["issues"] = []
        else:
            artifact = parsed.artifact if isinstance(parsed.artifact, dict) else {}
            state[stage.output_artifact] = artifact
            state["issues"] = [i.model_dump() for i in parsed.issues]
        self._snapshot(state, f"stage_{stage.id}_output")
        if artifact:
            self._persist_files(artifact, state.get("output_dir", ""))
        if parsed.decision == AgentDecision.NEEDS_CLARIFICATION:
            state["phase"] = BuilderSessionPhase.failed.value
            state["error"] = f"Stage {stage.id} needs clarification"
            return state
        if stage.retry_target_id:
            state = await self._retry_loop(stage, state)
        return state

    async def _exec_test_runner(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        state = dict(state)
        output_dir = state.get("output_dir", "")
        test_plan = state.get(stage.output_artifact) or {}
        script = test_plan.get("test_script", "")
        result_key = stage.test_result_key
        if not script:
            test_report = await self._tri_evaluate(stage, state, pytest_output="")
            state[result_key] = test_report
            return state
        test_dir = os.path.join(output_dir, os.getenv("AIPLAT_TEST_DIR", "test"))
        os.makedirs(test_dir, exist_ok=True)
        test_file = os.getenv("AIPLAT_TEST_FILE", "test_api.py")
        with open(os.path.join(test_dir, test_file), "w", encoding="utf-8") as f:
            f.write(script)
        with open(os.path.join(test_dir, "__init__.py"), "w") as f:
            f.write("")
        all_files = self._collect_files(self._collect_upstream_code(state))
        for f in all_files:
            path = f.get("path", "") or f.get("file", "")
            content = f.get("content", "") or f.get("code", "")
            if path and content:
                full = os.path.join(output_dir, path.lstrip("/"))
                try:
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "w", encoding="utf-8") as fh:
                        fh.write(content)
                except OSError:
                    pass
        try:
            from core.harness.syscalls.tool import sys_tool_call
            from core.apps.tools.code import CodeExecutionTool  # noqa: allowed — data type (class) import
            exec_tool = CodeExecutionTool()
            test_cmd = os.getenv("AIPLAT_TEST_COMMAND",
                f"pytest {test_dir} -v --tb=short")
            exec_args = {
                "language": os.getenv("AIPLAT_TEST_LANGUAGE", "python"),
                "code": f"import subprocess, sys; cmd = [sys.executable, '-m'] + '{test_cmd}'.split(); r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd='{output_dir}'); print(r.stdout[-3000:]); print('STDERR:', r.stderr[-500:] if r.stderr else '')",
                "timeout": 60000,
            }
            result = await sys_tool_call(exec_tool, exec_args, user_id="system", session_id=str(state.get("session_id", "engine")))
            pytest_output = (getattr(result, 'output', {}) or {}).get("stdout", "") if getattr(result, 'success', False) else ""
        except Exception:
            pytest_output = ""
        test_report = await self._tri_evaluate(stage, state, pytest_output)
        # Track evaluation count for epistemic uncertainty (Bayesian: more evidence = lower uncertainty)
        eval_count = state.get("_eval_count", 0) + 1
        state["_eval_count"] = eval_count
        try:
            from core.harness.evaluation.compare import pairwise_judge
            baseline = state.get("_baseline_test_report")
            if baseline and isinstance(baseline, dict):
                compare = await pairwise_judge(baseline, test_report, eval_count=eval_count)
                predictions = state.get("_predicted_fixes_and_regressions", {})
                if predictions:
                    try:
                        from core.harness.evaluation.compare import verify_prediction
                        state["_prediction_verification"] = await verify_prediction(predictions, test_report)
                    except Exception:
                        pass
                if not predictions:
                    try:
                        from core.harness.integration import _ensure_di
                        di = _ensure_di()
                        if di:
                            from core.apps.skills.evolution.engine import get_latest_predictions
                            predictions = get_latest_predictions()
                        else:
                            predictions = {}
                    except Exception:
                        predictions = {}
                test_report["_compare"] = {"verdict": compare.verdict, "stop_recommendation": compare.stop_recommendation,
                    "improvement_headroom": compare.improvement_headroom, "confidence": compare.confidence,
                    "evidence_count": compare.evidence_count, "uncertainty": compare.uncertainty,
                    "reason": compare.reason, "dimension_details": compare.dimension_details}
            else:
                state["_baseline_test_report"] = dict(test_report)
                test_report["_compare"] = {"verdict": "improved", "stop_recommendation": "continue",
                    "improvement_headroom": "high", "reason": "First evaluation -- baseline captured",
                    "evidence_count": eval_count, "uncertainty": "high"}
        except Exception:
            pass
        upstream = self._upstream_output(state, include_outputs=set())
        # Config-driven: find the architecture stage (not the QA stage)
        arch_key = ""
        for s in self._config.stages:
            if s.output_artifact and s.output_artifact != stage.output_artifact and not s.uses_code_skill and not s.generate_test_plan:
                arch_key = s.output_artifact
        arch = upstream.get(arch_key, {})
        code_files = sum(len((state.get(s.output_artifact) or {}).get("files", [])) for s in self._config.stages if s.uses_code_skill)
        cfg_fields = getattr(stage, 'coverage_trace_fields', None) or {}
        comp_key = cfg_fields.get("components_key", "components")
        api_key = cfg_fields.get("api_contracts_key", "api_contracts")
        data_key = cfg_fields.get("data_model_key", "data_model")
        test_report["_coverage_trace"] = {
            "components_designed": len(arch.get(comp_key) or []),
            "api_contracts_defined": len(arch.get(api_key) or []),
            "data_entities_defined": len(arch.get(data_key) or {}),
            "files_implemented": code_files,
            "test_cases_produced": len(test_report.get("test_cases") or []),
            "cascade": {"components_to_files": round(code_files / max(len(arch.get(comp_key) or []), 1), 2),
                         "files_to_tests": round(len(test_report.get("test_cases") or []) / max(code_files, 1), 2)},
        }
        state[result_key] = test_report
        return state

    async def _tri_evaluate(self, stage: PipelineStageConfig, state: Dict, pytest_output: str) -> Dict:
        passed = pytest_output.count("PASSED") if "PASSED" in pytest_output else pytest_output.count(" passed")
        failed = pytest_output.count("FAILED") if "FAILED" in pytest_output else pytest_output.count(" failed")
        total = max(passed + failed, 1)
        pass_rate = passed / total
        upstream = self._upstream_output(state, include_outputs=set())
        # Config-driven: find the first stage's output as requirements source
        prd_key = self._config.stages[0].output_artifact if self._config.stages else ""
        prd = upstream.get(prd_key, {}) if prd_key else {}
        code = self._collect_upstream_code(state)
        code_summary = [{"path": f.get("path", ""), "lines": len((f.get("content") or f.get("code") or "").split("\n"))}
                        for f in self._collect_files(code)[:30]]

        dims: List[Dict[str, Any]] = stage.scoring_dimensions or []
        if not dims:
            dims = [
                {"name": "quality", "weight": 1.0, "description": "Overall output quality", "threshold": 6.0},
            ]
        dim_names = [d.get("name", "") for d in dims if d.get("name")]
        dim_lines = "; ".join(f"{d.get('name','')}({int(d.get('weight',0)*100)}%): {d.get('description','')}" for d in dims)
        primary_dim = dim_names[0] if dim_names else "overall"
        score_example = {d.get("name", ""): 8.0 for d in dims}
        score_example["overall"] = 7.5

        eval_template = os.getenv("AIPLAT_EVAL_TEMPLATE",
            """You are a TriAgent Evaluator. Evaluate based on requirements, code, and test results.

## Requirements
{prd}

## Code Files
{code_summary}

## Pytest Output
{pytest_output}

## Scoring (0-10)
{dim_lines}

Output ONLY JSON: {{"pass":true,"score":{score_example},"pass_rate":{pass_rate},"test_cases":[],"issues":[],"recommendation":"APPROVED"}}
APPROVED if pass_rate>=0.8 and {primary_dim}>=7.0""")
        eval_prompt = eval_template.format(
            prd=json.dumps(self._summarize_artifact(prd), ensure_ascii=False, indent=2),
            code_summary=json.dumps(code_summary, ensure_ascii=False, indent=2),
            pytest_output=pytest_output[:3500] if pytest_output else '(no tests executed)',
            dim_lines=dim_lines,
            score_example=json.dumps(score_example),
            pass_rate=pass_rate,
            primary_dim=primary_dim,
        )
        result_text = await self._stage_runner.run(eval_prompt, state)
        report = {}
        json_str = self._extract_json(result_text)
        if json_str:
            try:
                report = json.loads(json_str)
            except json.JSONDecodeError:
                pass
        if not isinstance(report, dict) or not report:
            issues = [l.strip()[:120] for l in pytest_output.split("\n") if "FAILED" in l or "Error" in l]
            fallback_score = {d.get("name", ""): pass_rate * 10 for d in dims if d.get("name")}
            fallback_score["overall"] = pass_rate * 10
            report = {"pass": pass_rate >= 0.8, "score": fallback_score,
                "pass_rate": pass_rate, "test_cases": [], "issues": [{"severity": "P1", "description": i} for i in issues[:10]],
                "recommendation": "APPROVED" if pass_rate >= 0.8 else "REJECTED"}
        score = report.get("score") if isinstance(report.get("score"), dict) else {}
        try:
            primary_val = float(score.get(primary_dim, 0))
        except (TypeError, ValueError):
            primary_val = 0.0
        primary_threshold = dims[0].get("threshold", 7.0) if dims else 7.0
        if report.get("pass") is True and primary_val < primary_threshold:
            report["pass"] = False
        if "overall" not in score and score:
            vals = [float(score.get(d.get("name", ""), 0)) for d in dims if score.get(d.get("name")) is not None]
            weights = [d.get("weight", 0) for d in dims if score.get(d.get("name")) is not None]
            total_w = sum(weights) or 1.0
            score["overall"] = round(sum(v * w for v, w in zip(vals, weights)) / total_w, 2) if vals else 0.0
        report["score"] = score
        report.setdefault("pass_rate", pass_rate)
        report.setdefault("recommendation", "APPROVED" if report.get("pass") else "REJECTED")
        return report

    async def _gen_test_plan(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        state = dict(state)
        prompt = self._build_prompt(stage, state)
        result = await self._stage_runner.run(prompt, state, stage=stage)
        parsed = self._parse_output(result)
        artifact = parsed.artifact if isinstance(parsed.artifact, dict) else {"test_cases": [], "pass_rate": 0, "recommendation": "REJECTED"}
        if "test_cases" in artifact:
            state[stage.test_result_key or stage.output_artifact] = artifact
        else:
            artifact = {"test_cases": [], "pass_rate": 0, "recommendation": "REJECTED"}
            state[stage.output_artifact] = artifact
        if stage.hitl:
            state["phase"] = stage.hitl_phase
            self._snapshot(state, f"stage_{stage.id}_test_plan")
        return state

    async def _retry_loop(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        state = dict(state)
        max_stag = self._config.max_stagnation
        cfg_budget = self._config.max_tokens_per_run
        max_attempts = getattr(self._config, 'max_retry_attempts', None) or 3

        def _over_budget():
            u = state.get("tokens_used", 0)
            b = state.get("tokens_budget") or cfg_budget or 100000
            return u >= b

        attempt = 0
        loop_start = time.time()
        stage_timeout = getattr(stage, 'stage_timeout_seconds', None) or 600
        while True:
            attempt += 1
            elapsed = time.time() - loop_start
            if elapsed > stage_timeout:
                state["error"] = f"stage_timeout ({elapsed:.0f}s > {stage_timeout}s)"
                state["_last_action_reason"] = "stage_timeout"
                break
            state["qa_retry"] = state.get("qa_retry", 0) + 1
            b = state.get("tokens_budget") or cfg_budget or 100000
            if attempt > max_attempts:
                state["error"] = f"max_retry_attempts ({max_attempts}) exceeded"
                state["_last_action_reason"] = "retry_max_attempts"
                break
            if _over_budget():
                state["error"] = "token_budget_exhausted"
                state["_last_action_reason"] = "retry_budget_exhausted"
                break
            if state.get("_stagnation_count", 0) >= max_stag:
                state["error"] = f"stagnation ({state['_stagnation_count']} rounds unchanged)"
                state["_last_action_reason"] = "retry_stagnation"
                break
            if self._check_done(stage, state):
                state["phase"] = BuilderSessionPhase.done.value
                break
            report = state.get(stage.output_artifact)
            if report and isinstance(report, dict) and report.get("recommendation") == "REJECTED":
                auto_r = state.get("_auto_retry_count", 0) + 1
                state["_auto_retry_count"] = auto_r
                max_auto_retries = getattr(self._config, 'max_auto_retries', None) or 3
                if auto_r > max_auto_retries:
                    state["error"] = f"auto_retry_exhausted ({max_auto_retries} evaluation rejections)"
                    state["_last_action_reason"] = "evaluation_rejected_max_auto_retry"
                    break
            if report and isinstance(report, dict):
                compare = report.get("_compare", {})
                if isinstance(compare, dict) and compare.get("verdict") == "regressed":
                    state["error"] = "evaluation regressed"
                    state["_last_action_reason"] = "evaluation_regressed"
                    break
            eval_state = await self._exec_stage(stage, state)
            state.update(eval_state)
            if _over_budget() or self._check_done(stage, state):
                state["phase"] = BuilderSessionPhase.done.value if self._check_done(stage, state) else state.get("phase", "")
                break
            target = self._resolve_retry_target(stage, state)
            if not target:
                state["error"] = f"No retry target found for stage {stage.id}"
                break
            fix = await self._exec_fix_stage(target, stage, state)
            state.update(fix)
            if _over_budget():
                state["error"] = "token_budget_exhausted"
                break
            eval_state = await self._exec_stage(stage, state)
            state.update(eval_state)
            if attempt < max_attempts:
                delay = 2 ** (attempt - 1)
                await asyncio.sleep(delay)
        return state

    def _build_prompt(self, stage: PipelineStageConfig, state: PipelineState) -> str:
        feedback = state.get("_reject_feedback", "")
        fb = f"\n## Reject Feedback\n{feedback}" if feedback else ""
        ctx = {}
        constraint_text = ""
        handoff_text = ""
        for artifact_name in stage.input_artifacts:
            val = state.get(artifact_name)
            if val:
                ctx[artifact_name] = self._summarize_artifact(val)
                if isinstance(val, dict) and val.get("constraints"):
                    parts = "\n".join(f"- {c}" for c in val["constraints"])
                    if parts:
                        constraint_text = f"\n## Constraints (from {artifact_name})\n{parts}"
        if stage.input_artifacts and ctx:
            handoff_parts = []
            for artifact_name, val in ctx.items():
                if isinstance(val, dict):
                    summary = str(val.get("description") or f"{artifact_name} completed")[:120]
                    handoff_parts.append(f"1. What was done ({artifact_name}): {summary}")
                    handoff_parts.append(f"2. Where ({artifact_name}): state[\"{artifact_name}\"]")
                    verify = val.get("verify") or val.get("acceptance_criteria") or ""
                    if verify:
                        handoff_parts.append(f"3. How to verify ({artifact_name}): {str(verify)[:120]}")
                    for s in self._config.stages:
                        if artifact_name in s.input_artifacts:
                            handoff_parts.append(f"5. Next ({artifact_name}): {(s.agent_name or s.agent_id)} continues")
                            break
            if handoff_parts:
                handoff_text = "\n## Handoff (upstream output summary)\n" + "\n".join(handoff_parts)
        prev_issues = state.get("issues") or []
        iss = f"\n## Previous Issues\n{json.dumps(prev_issues[:3], ensure_ascii=False, indent=2)}" if prev_issues else ""
        agent_list = ""
        if stage.retry_target_id or stage.generate_test_plan:
            agents_info = [{"id": s.agent_id, "name": s.agent_name, "role": s.phase}
                          for s in self._config.stages]
            agent_list = f"\n## Available Agents\n{json.dumps(agents_info, ensure_ascii=False, indent=2)}"
        stage_hints = ""
        if stage.prompt_extra and stage.prompt_extra.strip():
            stage_hints = f"\n## Stage Instructions\n{stage.prompt_extra}"
        return f"""You are {stage.agent_name or stage.id}.
Complete your work based on upstream output.{fb}{constraint_text}{handoff_text}{iss}{agent_list}{stage_hints}

## Upstream Artifacts
{json.dumps(ctx, ensure_ascii=False, indent=2)}

## Task Description
{state.get('description', '')}

## Output Format
Output JSON with artifact, confidence, issues, decision.
```json
{{"artifact": {{}},"confidence": "HIGH","issues": [{{"severity": "P1","description": "description","target_agent": "agent_id","suggestion": "suggestion"}}],"decision": "PROCEED"}}
```"""

    def _find_stage(self, stage_id: str) -> Optional[PipelineStageConfig]:
        for s in self._config.stages:
            if s.id == stage_id:
                return s
        return None

    def _current_stage(self, state: PipelineState) -> PipelineStageConfig:
        idx = state.get("_current_stage_idx", 0)
        return self._config.stages[idx]

    def _check_done(self, stage: PipelineStageConfig, state: PipelineState) -> bool:
        result_key = getattr(stage, 'test_result_key', None) or stage.output_artifact
        report = state.get(result_key) or {}
        return report.get("recommendation") == TestRecommendation.APPROVED.value

    def _resolve_retry_target(self, stage: PipelineStageConfig, state: PipelineState) -> Optional[PipelineStageConfig]:
        if not stage.retry_target_id:
            return None
        report = state.get(stage.output_artifact) or {}
        for iss in (report.get("issues") or []):
            target_agent = iss.get("target_agent", "")
            for s in self._config.stages:
                if s.agent_id == target_agent or s.id == target_agent:
                    return s
        for s in self._config.stages:
            if s.id == stage.retry_target_id:
                return s
        return None

    async def _exec_fix_stage(self, target: PipelineStageConfig, caller: PipelineStageConfig,
                               state: PipelineState) -> PipelineState:
        state = dict(state)
        found_target = False
        for s in self._config.stages:
            if s.id == target.id:
                found_target = True
            if found_target:
                state[s.output_artifact] = None
                state.pop(f"_stage_{s.id}_done", None)
                if s.generate_test_plan:
                    state[s.test_result_key] = None
        state["_reject_feedback"] = f"Fix issues from {caller.agent_name}"
        return await self._run_stages_from(self._config.stages.index(target), state)

    async def assemble_deploy(self, state: PipelineState) -> str:
        strategy = self._config.deploy_strategy
        output_dir = state.get("output_dir", "")
        deploy_dir = os.path.join(output_dir, "deploy")
        os.makedirs(deploy_dir, exist_ok=True)
        if strategy == "manifest":
            return await self._deploy_manifest(state, deploy_dir)
        all_code = self._collect_upstream_code(state)
        files = self._collect_files(all_code)
        has_dockerfile = any(f.get("path", "").endswith("Dockerfile") for f in files)
        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            if path and content:
                full = os.path.join(deploy_dir, path.lstrip("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(content)
        if not has_dockerfile:
            dockerfile_template = os.getenv("AIPLAT_DEPLOY_DOCKERFILE_TEMPLATE", "")
            if dockerfile_template:
                with open(os.path.join(deploy_dir, "Dockerfile"), "w") as f:
                    f.write(dockerfile_template)
        if strategy == "docker":
            await self._deploy_docker(deploy_dir, state)
        return deploy_dir

    async def _deploy_manifest(self, state: PipelineState, deploy_dir: str) -> str:
        import json
        import yaml
        services = {}
        for s in self._config.stages:
            if s.uses_code_skill and state.get(s.output_artifact):
                svc_name = s.code_target or s.output_artifact
                services[svc_name] = {"source": s.output_artifact, "files": []}
        manifest = {
            "version": "1.0",
            "project": state.get("session_id", ""),
            "services": services,
            "phase": state.get("phase", ""),
        }
        with open(os.path.join(deploy_dir, "manifest.yaml"), "w") as f:
            yaml.safe_dump(manifest, f, default_flow_style=False)
        return deploy_dir

    async def _deploy_docker(self, deploy_dir: str, state: PipelineState) -> None:
        import subprocess
        try:
            subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
            prefix = os.getenv("AIPLAT_DOCKER_IMAGE_PREFIX", "aiplat-")
            subprocess.run(["docker", "build", "-t", f"{prefix}{state.get('session_id', 'proj')[:12]}", deploy_dir],
                           capture_output=True, timeout=60)
        except Exception:
            pass

    @staticmethod
    def _collect_files(artifact: Dict) -> List[Dict[str, str]]:
        files = []
        for f in (artifact.get("files") or []):
            if isinstance(f, dict):
                files.append({"path": f.get("path", ""), "content": f.get("content", "")})
        return files

    def _store_artifacts(self, session_id: str, state: PipelineState) -> None:
        """Persist pipeline artifacts to ArtifactRegistry for versioned retrieval."""
        try:
            from core.harness.artifacts.registry import get_artifact_registry
            reg = get_artifact_registry()
            for s in self._config.stages:
                val = state.get(s.output_artifact)
                if not isinstance(val, dict):
                    continue
                files = self._collect_files(val)
                if files:
                    reg.store(
                        project_id=session_id,
                        name=s.output_artifact,
                        files=files,
                        session_id=session_id,
                        tags=["pipeline_crystal", s.id],
                        metadata={"agent_id": s.agent_id},
                    )
        except Exception:
            pass

    def _collect_upstream_code(self, state: PipelineState) -> Dict[str, Any]:
        all_code = {}
        for s in self._config.stages:
            if s.uses_code_skill and state.get(s.output_artifact):
                artifact = state[s.output_artifact]
                if isinstance(artifact, dict):
                    all_code = {**all_code, **artifact}
        return all_code

    @staticmethod
    def _extract_json(text: str) -> str:
        import re
        m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if m:
            return m.group(1).strip()
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return m.group(0).strip()
        return ""

    @staticmethod
    def _extract_files_delimiter(text: str) -> List[Dict[str, str]]:
        files = []
        import re
        for m in re.finditer(r'##\s*FILE:\s*(\S+)[\s\S]*?\n(.*?)(?=\n##\s*FILE:|\Z)', text, re.MULTILINE):
            files.append({"path": m.group(1).strip(), "content": m.group(2).strip()})
        return files

    @staticmethod
    def _parse_output(raw: str) -> AgentOutput:
        json_str = PipelineEngine._extract_json(raw)
        if json_str:
            try:
                data = json.loads(json_str)
                artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else data
                issues = [Issue(severity=IssueSeverity(i.get("severity", "P1")) if i.get("severity") in {"P0","P1","P2"} else "P1",
                                description=i.get("description", ""),
                                target_agent=i.get("target_agent", ""),
                                suggestion=i.get("suggestion", ""))
                          for i in (data.get("issues") or []) if isinstance(i, dict)]
                return AgentOutput(artifact=artifact if isinstance(artifact, dict) else {},
                                 issues=issues,
                                 confidence=AgentConfidence(data.get("confidence", "MEDIUM")),
                                 decision=AgentDecision(data.get("decision", "PROCEED")))
            except (json.JSONDecodeError, TypeError):
                pass
        return AgentOutput(artifact={"raw_output": raw[:5000]}, issues=[], confidence=AgentConfidence.LOW, decision=AgentDecision.PROCEED)

    def _snapshot(self, state: PipelineState, name: str) -> None:
        sid = state.get("session_id", "")
        if not sid:
            return
        checkpoint = {"name": name, "ts": time.time(), "phase": state.get("phase", ""),
            "stage_idx": state.get("_current_stage_idx"), "last_reason": state.get("_last_action_reason", ""),
            "artifacts": {s.output_artifact: bool(state.get(s.output_artifact)) for s in self._config.stages},
            "tokens_used": state.get("tokens_used", 0), "iteration": state.get("iteration", 0)}
        state.setdefault("_checkpoints", []).append(checkpoint)
        base = self._output_root(sid)
        os.makedirs(base, exist_ok=True)
        try:
            with open(os.path.join(base, f"_{name}.json"), "w", encoding="utf-8") as fh:
                json.dump(dict(state), fh, ensure_ascii=False, indent=2, default=str)
        except OSError:
            pass

    def _output_root(self, project_id: str) -> str:
        return str(os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id))

    def _persist_files(self, artifact: Dict[str, Any], output_dir: str = "") -> None:
        if not output_dir:
            return
        for f in self._collect_files(artifact):
            path = f.get("path", "")
            content = f.get("content", "")
            if path and content:
                full = os.path.join(output_dir, path.lstrip("/"))
                try:
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "w", encoding="utf-8") as fh:
                        fh.write(content)
                except OSError:
                    pass

    @staticmethod
    def _summarize_artifact(val: Any, max_chars: int = 8000) -> Dict[str, Any]:
        """Structured 7-section summary template (OpenCode pattern).

        Sections: goal, artifacts, quality, key_decisions, next_steps,
        critical_context, relevant_files.
        """
        if not isinstance(val, dict):
            s = str(val)[:max_chars // 2] if val else "{}"
            return {"summary": s, "artifact_keys": []}
        raw = json.dumps(val, ensure_ascii=False, default=str)
        if len(raw) <= max_chars:
            return val

        files = val.get("files", []) if isinstance(val.get("files"), list) else []
        file_list = [
            {"path": f.get("path", ""), "purpose": f.get("description", "")[:80]}
            for f in files[:20]
        ]

        tests_data = val.get("test_results", {}) or {}
        pass_count = tests_data.get("passed", 0) if isinstance(tests_data, dict) else 0
        fail_count = tests_data.get("failed", 0) if isinstance(tests_data, dict) else 0
        total_count = pass_count + fail_count
        pass_rate = f"{pass_count}/{total_count}" if total_count > 0 else "N/A"

        issues = val.get("issues", []) if isinstance(val.get("issues"), list) else []
        p0 = sum(1 for i in issues if isinstance(i, dict) and str(i.get("severity", "")).upper() == "P0")
        p1 = sum(1 for i in issues if isinstance(i, dict) and str(i.get("severity", "")).upper() == "P1")

        return {
            "goal": str(val.get("phase_description", "") or val.get("description", "") or "")[:200],
            "artifacts_produced": {
                "keys": list(val.keys())[:20],
                "total_size_chars": len(raw),
                "file_count": len(files),
            },
            "quality_assessment": {
                "tests_run": pass_rate,
                "confidence": val.get("confidence", "N/A") if isinstance(val, dict) else "N/A",
                "issues_found": f"{len(issues)} (P0:{p0}, P1:{p1})" if issues else "none",
            },
            "key_decisions": val.get("decisions", []) if isinstance(val.get("decisions"), list) else [],
            "next_steps": val.get("next_steps", []) if isinstance(val.get("next_steps"), list) else [],
            "critical_context": str(val.get("known_issues", "") or val.get("notes", "") or "")[:500],
            "relevant_files": file_list,
        }

    async def _crystallize_skill(self, state: PipelineState) -> Optional[str]:
        """Crystallize successful pipeline execution into a reusable Skill.

        Extracts agent_sequence, artifacts, pass_rate, and keywords from state,
        writes a Skill YAML to ~/.aiplat/skills/auto/, and saves L3 task skill
        memory via MemoryManager.
        """
        try:
            agent_sequence = [s.agent_id or s.id for s in self._config.stages if s.agent_id or s.id]

            artifacts: List[str] = []
            artifact_keys: Dict[str, Any] = {}
            pass_rate = 0.0
            issues_total = 0
            for s in self._config.stages:
                val = state.get(s.output_artifact)
                if isinstance(val, dict):
                    artifacts.append(s.output_artifact)
                    artifact_keys[s.output_artifact] = {
                        "size_chars": len(json.dumps(val, ensure_ascii=False, default=str)),
                        "file_count": len(val.get("files", []) if isinstance(val.get("files"), list) else []),
                    }
                tests_data = val.get("test_results", {}) if isinstance(val, dict) else {}
                if isinstance(tests_data, dict):
                    p = tests_data.get("passed", 0)
                    f = tests_data.get("failed", 0)
                    total = p + f
                    if total > 0:
                        pass_rate = p / total
                    issues_total += len(tests_data.get("issues", []) if isinstance(tests_data.get("issues"), list) else [])

            if pass_rate < 0.01 and issues_total > 0:
                total = sum(1 for s in self._config.stages if s.generate_test_plan)
                runner_total = sum(
                    (state.get(s.test_result_key, {}).get("test_results", {}).get("passed", 0) if isinstance(state.get(s.test_result_key, {}), dict) else 0) +
                    (state.get(s.test_result_key, {}).get("test_results", {}).get("failed", 0) if isinstance(state.get(s.test_result_key, {}), dict) else 0)
                    for s in self._config.stages if s.generate_test_plan
                )
                if runner_total > 0:
                    runner_passed = sum(
                        state.get(s.test_result_key, {}).get("test_results", {}).get("passed", 0) if isinstance(state.get(s.test_result_key, {}), dict) else 0
                        for s in self._config.stages if s.generate_test_plan
                    )
                    pass_rate = runner_passed / runner_total

            description = str(state.get("description", ""))
            keywords = self._extract_keywords(description)

            sid = state.get("session_id", "")
            skill_id = f"pipeline_{hashlib.md5(sid.encode()).hexdigest()[:8]}" if sid else f"pipeline_{hashlib.md5(json.dumps(agent_sequence).encode()).hexdigest()[:8]}"

            agent_label = " + ".join(agent_sequence[:4])
            name = f"Auto: {agent_label}" if agent_sequence else f"Auto: Pipeline {skill_id}"

            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            skills_dir = os.path.expanduser("~/.aiplat/skills/auto")
            os.makedirs(skills_dir, exist_ok=True)
            skill_path = os.path.join(skills_dir, f"{skill_id}.md")

            frontmatter = {
                "type": "rule",
                "category": "pipeline_crystal",
                "source_pipeline_id": sid,
                "agent_sequence": agent_sequence,
                "artifacts": artifacts,
                "pass_rate": round(pass_rate, 3),
                "prompt_keywords": keywords,
                "created_at": created_at,
            }

            lines = ["---"]
            for k, v in frontmatter.items():
                lines.append(f"{k}: {v}")
            lines.append("---")
            lines.append("")
            lines.append(f"# {name}")
            lines.append("")
            lines.append("## Agent Sequence")
            for i, ag in enumerate(agent_sequence, 1):
                lines.append(f"{i}. {ag}")
            lines.append("")
            lines.append("## Artifacts Produced")
            for art in artifacts:
                info = artifact_keys.get(art, {})
                lines.append(f"- `{art}` ({info.get('file_count', 0)} files, {info.get('size_chars', 0)} chars)")
            lines.append("")
            lines.append(f"## Quality: {pass_rate:.1%} pass rate | {issues_total} issues")
            lines.append("")
            lines.append("## Suggested Scenarios")
            if keywords:
                lines.append(f"Keywords: {', '.join(keywords)}")

            with open(skill_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            try:
                from core.harness.memory.manager import get_memory_manager, TaskSkill
                mm = get_memory_manager(namespace=state.get("session_id", "default"))
                task_skill = TaskSkill(
                    skill_id=skill_id,
                    name=name,
                    pipeline_id=sid,
                    agent_sequence=agent_sequence,
                    artifacts=artifacts,
                    pass_rate=round(pass_rate, 3),
                    keywords=keywords,
                    artifacts_keys=artifact_keys,
                    created_at=created_at,
                )
                await mm.save_task_skill(task_skill)
            except Exception:
                pass

            # Store pipeline artifacts in ArtifactRegistry for versioned retrieval
            self._store_artifacts(sid, state)

            return skill_path
        except Exception:
            return None

    async def _accept_plan_stages(self, plan_stages: List[Dict], state: PipelineState) -> PipelineState:
        """Accept AI-recommended stages JSON and write PipelineStageConfig.

        Validates that each stage has required fields (id, agent_id, output_artifact),
        then replaces self._config.stages and clears old artifacts from state.
        Returns updated state with new stage config applied.
        """
        new_stages: List[PipelineStageConfig] = []
        for i, ps in enumerate(plan_stages):
            sid = ps.get("id") or f"plan_stage_{i}"
            new_stages.append(PipelineStageConfig(
                id=sid,
                agent_id=ps.get("agent_id", ""),
                output_artifact=ps.get("output_artifact", f"plan_artifact_{i}"),
                description=ps.get("description", ""),
                generate_test_plan=ps.get("generate_test_plan", False),
                uses_code_skill=ps.get("uses_code_skill", False),
                hitl=ps.get("hitl", True),
                order=ps.get("order", i),
                prompt_extra=ps.get("prompt_extra", ""),
                agent_type=ps.get("agent_type", "react"),
                test_result_key=ps.get("test_result_key", f"test_results_{i}"),
            ))
        old_stages = self._config.stages
        self._config.stages = new_stages
        state = dict(state)
        for s in old_stages:
            state.pop(s.output_artifact, None)
            state.pop(f"_stage_{s.id}_done", None)
            state.pop(s.test_result_key, None)
        state["_plan_stage_ids"] = [s.id for s in new_stages]
        state["_last_action_reason"] = "plan_accepted"
        return state

    def _rollback_to_plan(self, state: PipelineState) -> PipelineState:
        """Rollback execution to planning recommended state.

        Clears all artifacts, resets retry counters, sets phase to executing
        with _current_stage_idx = 0 so pipeline restarts from first stage.
        """
        state = dict(state)
        for s in self._config.stages:
            state.pop(s.output_artifact, None)
            state.pop(f"_stage_{s.id}_done", None)
            state.pop(s.test_result_key, None)
            if s.retry_target_id:
                state.pop(s.retry_target_id, None)
        state["iteration"] = 0
        state["qa_retry"] = 0
        state["tokens_used"] = 0
        state["_current_stage_idx"] = 0
        state["_prev_failing_ids"] = []
        state["_stagnation_count"] = 0
        state["_auto_retry_count"] = 0
        state["error"] = ""
        state["phase"] = BuilderSessionPhase.executing.value
        state["_last_action_reason"] = "rolled_back_to_plan"
        return state

    async def _auto_sop_pipeline(
        self, project_id: str, requirement: str, plan_stages: List[Dict],
        prd_data: Optional[Dict] = None
    ) -> PipelineState:
        """Full automatic SOP pipeline: plan → accept → execute → evaluate → crystallize.

        Covers all stages without human intervention. Used when auto_approve is
        true or when the same pipeline pattern has been previously approved.
        """
        state = await self.initialize(project_id, requirement, prd_data)
        state = await self._accept_plan_stages(plan_stages, state)
        state["_auto_approve"] = True
        state["phase"] = BuilderSessionPhase.executing.value
        state = await self._run_stages_from(0, state)
        if state.get("error") and not state.get("phase") == BuilderSessionPhase.done.value:
            rollback_threshold = getattr(self._config, 'rollback_threshold', 0.5)
            total = len(self._config.stages)
            completed = sum(1 for s in self._config.stages if state.get(f"_stage_{s.id}_done"))
            if total > 0 and completed / total < rollback_threshold:
                state = self._rollback_to_plan(state)
                state["phase"] = BuilderSessionPhase.executing.value
                state = await self._run_stages_from(0, state)
        return state

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract technical framework keywords from requirement text.

        Only includes technology-agnostic framework/tool names, NOT business domain terms.
        Business keywords (e-commerce, healthcare, finance, etc.) must be declared
        by the Skill author in its SKILL.md frontmatter, not inferred by the engine.
        """
        import re
        tech_patterns = [
            r"(?:fastapi|flask|django|express|spring|rails|laravel)",
            r"(?:react|vue|angular|next\.?js|nuxt|svelte)",
            r"(?:postgres|mysql|mongodb|redis|sqlite|mariadb)",
            r"(?:docker|kubernetes|k8s|terraform)",
            r"(?:python|typescript|javascript|go|rust|java|kotlin|swift)",
            r"(?:rest|graphql|grpc|websocket|soap)",
        ]
        kw = set()
        text_lower = text.lower()
        for p in tech_patterns:
            m = re.findall(p, text_lower)
            for x in m:
                kw.add(x.lower().replace("-", "").replace(".", ""))
        return sorted(kw)[:10]

    async def _consolidate_auto_pipeline(self, state: PipelineState) -> None:
        """After HITL approval, persist pipeline config and artifacts for future auto-runs.

        When the same pipeline pattern (agent_sequence + keywords) is detected
        in a future run, the system auto-approves via state['_auto_approve'] = True.
        """
        try:
            sid = state.get("session_id", "")
            agent_seq = [s.agent_id or s.id for s in self._config.stages if s.agent_id or s.id]
            desc = str(state.get("description", ""))
            keywords = self._extract_keywords(desc)
            fingerprint = hashlib.sha256(
                (json.dumps(agent_seq, sort_keys=True) + ":" + json.dumps(keywords, sort_keys=True)).encode()
            ).hexdigest()[:12]

            auto_dir = os.path.expanduser("~/.aiplat/auto_pipelines")
            os.makedirs(auto_dir, exist_ok=True)

            pipeline_json = {
                "fingerprint": fingerprint,
                "session_id": sid,
                "agent_sequence": agent_seq,
                "keywords": keywords,
                "stages": [
                    {
                        "id": s.id,
                        "agent_id": s.agent_id,
                        "output_artifact": s.output_artifact,
                        "generate_test_plan": s.generate_test_plan,
                        "uses_code_skill": s.uses_code_skill,
                        "hitl": False,
                    }
                    for s in self._config.stages
                ],
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            config_path = os.path.join(auto_dir, f"{fingerprint}.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(pipeline_json, f, indent=2)

            state["_auto_approve"] = True
            state["_consolidated_fingerprint"] = fingerprint
        except Exception:
            pass
