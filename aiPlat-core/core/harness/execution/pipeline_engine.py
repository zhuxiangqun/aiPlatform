"""
PipelineEngine -- generic team execution engine.

Canonical location: harness/execution/pipeline_engine.py (CLAUDE.md §5.23).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict

import asyncio
import json
import os
import time

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
    session_id: str
    phase: str
    description: str
    prd: Optional[Dict[str, Any]]
    architecture: Optional[Dict[str, Any]]
    code: Optional[Dict[str, Any]]
    test_plan: Optional[Dict[str, Any]]
    test_report: Optional[Dict[str, Any]]
    security_report: Optional[Dict[str, Any]]
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
        self._skill_loader = skill_loader
        self._stage_runner = StageRunner(model=model)

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
            state["prd"] = prd_data
        return await self._run_stages_from(0, state)

    async def approve(self, state: PipelineState) -> PipelineState:
        state = dict(state)
        idx = state.get("_current_stage_idx", 0)
        if state.get("phase") == BuilderSessionPhase.awaiting_test_plan_approval.value:
            return await self._run_stages_from(idx, state)
        return await self._run_stages_from(idx + 1, state)

    async def reject(self, state: PipelineState, feedback: str) -> PipelineState:
        state = dict(state)
        state["_reject_feedback"] = feedback
        idx = state.get("_current_stage_idx", 0)
        for i in range(idx, len(self._config.stages)):
            state[self._config.stages[i].output_artifact] = None
            state.pop(f"_stage_{self._config.stages[i].id}_done", None)
            if self._config.stages[i].generate_test_plan:
                state[self._config.stages[i].test_result_key] = None
        state["phase"] = BuilderSessionPhase.executing.value
        state["qa_retry"] = 0
        state["_stagnation_count"] = 0
        return await self._run_stages_from(idx, state)

    async def rollback(self, state: PipelineState, stage_id: str) -> PipelineState:
        state = dict(state)
        target_idx = -1
        for i, s in enumerate(self._config.stages):
            if s.id == stage_id:
                target_idx = i
                break
        if target_idx < 0:
            return state
        for i in range(target_idx, len(self._config.stages)):
            state[self._config.stages[i].output_artifact] = None
            state.pop(f"_stage_{self._config.stages[i].id}_done", None)
            if self._config.stages[i].generate_test_plan:
                state[self._config.stages[i].test_result_key] = None
        state["_current_stage_idx"] = target_idx
        state["phase"] = BuilderSessionPhase.executing.value
        state["_reject_feedback"] = ""
        state["_stagnation_count"] = 0
        state["qa_retry"] = 0
        return await self._run_stages_from(target_idx, state)

    async def _run_stages_from(self, start_idx: int, state: PipelineState) -> PipelineState:
        state = dict(state)
        for idx in range(start_idx, len(self._config.stages)):
            if state.get("phase") == BuilderSessionPhase.failed.value:
                state.setdefault("_last_action_reason", "phase_failed")
                break
            if state.get("tokens_used", 0) >= state.get("tokens_budget", 99999999):
                state["error"] = f"token_budget_exhausted ({state['tokens_used']})"
                state["_last_action_reason"] = "budget_exhausted"
                break

            state["_current_stage_idx"] = idx
            stage = self._config.stages[idx]
            graph_trace = state.setdefault("_graph_trace", [])
            graph_trace.append({"node": stage.id, "status": "started", "ts": time.time()})

            existing = state.get(stage.output_artifact)
            if existing and (not isinstance(existing, dict) or len(existing) > 0):
                if stage.retry_target_id and not self._check_done(stage, state):
                    pass
                else:
                    state[f"_stage_{stage.id}_done"] = True
                    state["_last_action_reason"] = f"skip:{stage.output_artifact}_exists"
                    graph_trace.append({"node": stage.id, "status": "skipped", "reason": f"{stage.output_artifact}_exists", "ts": time.time()})
                    continue

            if stage.generate_test_plan and not state.get(stage.output_artifact):
                state = await self._gen_test_plan(stage, state)
                if state.get("phase") in (BuilderSessionPhase.awaiting_test_plan_approval.value,):
                    graph_trace.append({"node": stage.id, "status": "paused", "phase": "awaiting_test_plan_approval", "ts": time.time()})
                    self._snapshot(state, f"stage_{stage.id}_test_plan")
                    return state

            if stage.generate_test_plan and state.get(stage.output_artifact):
                state = await self._exec_test_runner(stage, state)
                self._snapshot(state, f"stage_{stage.id}_output")
                state[f"_stage_{stage.id}_done"] = True
                graph_trace.append({"node": stage.id, "status": "completed", "ts": time.time()})
                continue

            if stage.uses_code_skill:
                state = await self._exec_code_generation(stage, state)
                self._snapshot(state, f"stage_{stage.id}_output")
                state[f"_stage_{stage.id}_done"] = True
                graph_trace.append({"node": stage.id, "status": "completed", "ts": time.time()})
                if state.get("phase") == BuilderSessionPhase.failed.value:
                    graph_trace.append({"node": stage.id, "status": "failed", "reason": "phase_failed", "ts": time.time()})
                    break
                continue

            state = await self._exec_stage(stage, state)
            state[f"_stage_{stage.id}_done"] = True
            artifact = state.get(stage.output_artifact)
            graph_trace.append({"node": stage.id, "status": "completed", "ts": time.time(), "metrics": {
                "artifact_fields": list(artifact.keys())[:5] if isinstance(artifact, dict) else [],
                "components_count": len(artifact.get("components", [])) if isinstance(artifact, dict) else 0,
                "files_count": len(artifact.get("files", [])) if isinstance(artifact, dict) else 0,
                "test_cases_count": len(artifact.get("test_cases", [])) if isinstance(artifact, dict) else 0,
            }})

            if state.get("phase") == BuilderSessionPhase.failed.value:
                graph_trace.append({"node": stage.id, "status": "failed", "reason": "phase_failed", "ts": time.time()})
                break

            if stage.hitl_after_execute and state.get(stage.output_artifact):
                state["phase"] = stage.hitl_after_phase or BuilderSessionPhase.awaiting_test_report_review.value
                graph_trace.append({"node": stage.id, "status": "paused", "phase": state["phase"], "ts": time.time()})
                self._snapshot(state, f"stage_{stage.id}_done")
                return state

            if stage.hitl:
                hitl_phase = stage.hitl_phase
                if not hitl_phase:
                    hitl_phase = (BuilderSessionPhase.awaiting_test_plan_approval.value
                                  if stage.generate_test_plan
                                  else BuilderSessionPhase.awaiting_architecture_approval.value)
                state["phase"] = hitl_phase
                graph_trace.append({"node": stage.id, "status": "paused", "phase": hitl_phase, "ts": time.time()})
                self._snapshot(state, f"stage_{stage.id}_done")
                return state

        if state.get("phase") not in (
            BuilderSessionPhase.failed.value,
            BuilderSessionPhase.awaiting_architecture_approval.value,
            BuilderSessionPhase.awaiting_test_plan_approval.value,
            BuilderSessionPhase.awaiting_test_report_review.value,
        ):
            state["phase"] = BuilderSessionPhase.done.value
        self._snapshot(state, "final_state")
        return state

    async def _exec_stage(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        """Generic stage execution via StageRunner -> ReActLoop (dumb loop)."""
        state = dict(state)
        state["iteration"] = state.get("iteration", 0) + 1
        used = state.get("tokens_used", 0)
        budget = state.get("tokens_budget", 99999999)
        print(f"    [stage] {stage.id} (iter {state['iteration']}, {used}/{budget} tokens)")
        prompt = self._build_prompt(stage, state)
        result_text = await self._stage_runner.run(prompt, state)
        parsed = self._parse_output(result_text)
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
        test_dir = os.path.join(output_dir, "test")
        os.makedirs(test_dir, exist_ok=True)
        with open(os.path.join(test_dir, "test_api.py"), "w", encoding="utf-8") as f:
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
            from core.apps.tools.code import CodeExecutionTool
            exec_tool = CodeExecutionTool()
            exec_args = {
                "language": "python",
                "code": f"import subprocess, sys; r = subprocess.run([sys.executable, '-m', 'pytest', '{test_dir}', '-v', '--tb=short'], capture_output=True, text=True, timeout=60, cwd='{output_dir}'); print(r.stdout[-3000:]); print('STDERR:', r.stderr[-500:] if r.stderr else '')",
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
                if not predictions:
                    try:
                        from core.apps.skills.evolution.engine import get_latest_predictions
                        predictions = get_latest_predictions()
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
        arch = state.get("architecture") or {}
        code_files = sum(len((state.get(s.output_artifact) or {}).get("files", [])) for s in self._config.stages if s.uses_code_skill)
        test_report["_coverage_trace"] = {
            "components_designed": len(arch.get("components") or []),
            "api_contracts_defined": len(arch.get("api_contracts") or []),
            "data_entities_defined": len(arch.get("data_model") or {}),
            "files_implemented": code_files,
            "test_cases_produced": len(test_report.get("test_cases") or []),
            "cascade": {"components_to_files": round(code_files / max(len(arch.get("components") or []), 1), 2),
                         "files_to_tests": round(len(test_report.get("test_cases") or []) / max(code_files, 1), 2)},
        }
        state[result_key] = test_report
        return state

    async def _tri_evaluate(self, stage: PipelineStageConfig, state: Dict, pytest_output: str) -> Dict:
        passed = pytest_output.count("PASSED") if "PASSED" in pytest_output else pytest_output.count(" passed")
        failed = pytest_output.count("FAILED") if "FAILED" in pytest_output else pytest_output.count(" failed")
        total = max(passed + failed, 1)
        pass_rate = passed / total
        prd = state.get("prd") or {}
        code = self._collect_upstream_code(state)
        code_summary = [{"path": f.get("path", ""), "lines": len((f.get("content") or f.get("code") or "").split("\n"))}
                        for f in self._collect_files(code)[:30]]
        eval_prompt = f"""You are a TriAgent Evaluator. Evaluate based on requirements, code, and test results.

## Requirements
{json.dumps(self._truncate(prd, 2500), ensure_ascii=False, indent=2)}

## Code Files
{json.dumps(code_summary, ensure_ascii=False, indent=2)}

## Pytest Output
{pytest_output[:3500] if pytest_output else '(no tests executed)'}

## Scoring (0-10)
functionality(55%): Code meets PRD; product_depth(20%): Edge cases; design_ux(15%): API quality; code_architecture(10%): Maintainability

Output ONLY JSON: {{"pass":true,"score":{{"functionality":8.5,"product_depth":6.0,"design_ux":7.0,"code_architecture":7.5,"overall":7.5}},"pass_rate":{pass_rate},"test_cases":[],"issues":[],"recommendation":"APPROVED"}}
APPROVED if pass_rate>=0.8 and functionality>=7.0"""
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
            report = {"pass": pass_rate >= 0.8, "score": {"functionality": pass_rate * 10, "product_depth": 0.0, "design_ux": 0.0, "code_architecture": 0.0, "overall": pass_rate * 10},
                "pass_rate": pass_rate, "test_cases": [], "issues": [{"severity": "P1", "description": i} for i in issues[:10]],
                "recommendation": "APPROVED" if pass_rate >= 0.8 else "REJECTED"}
        score = report.get("score") if isinstance(report.get("score"), dict) else {}
        try:
            functionality = float(score.get("functionality", 0))
        except (TypeError, ValueError):
            functionality = 0.0
        if report.get("pass") is True and functionality < 7.0:
            report["pass"] = False
        if "overall" not in score and score:
            dims = ["functionality", "product_depth", "design_ux", "code_architecture"]
            vals = [float(score.get(k, 0)) for k in dims if score.get(k) is not None]
            score["overall"] = round(sum(vals) / len(vals), 2) if vals else 0.0
        report["score"] = score
        report.setdefault("pass_rate", pass_rate)
        report.setdefault("recommendation", "APPROVED" if report.get("pass") else "REJECTED")
        return report

    async def _exec_code_generation(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        state = dict(state)
        proj_structure = (state.get("architecture") or {}).get("project_structure")
        skill = None
        if self._skill_loader:
            skill = self._skill_loader("code_generation")
        if skill is None:
            from core.apps.skills.base import CodeGenerationSkill
            skill = CodeGenerationSkill()
        from core.harness.interfaces import SkillContext
        if proj_structure:
            section = stage.code_target
            target_structure = proj_structure.get(section) or proj_structure
        else:
            target_structure = state.get("architecture")
        prompt = self._build_prompt(stage, state)
        result = await skill.execute(SkillContext(
            session_id=state.get("session_id", ""), user_id="system",
            variables={"project_structure": json.dumps(target_structure, ensure_ascii=False),
                       "prompt": prompt},
            metadata={"stage_id": stage.id, "agent_id": stage.agent_id},
        ), {"prompt": prompt, "project_structure": target_structure})
        if not result.success:
            state["phase"] = BuilderSessionPhase.failed.value
            state["error"] = f"CodeGeneration failed: {result.error}"
            return state
        output = result.output or {}
        code_text = output.get("code", "")
        files = self._extract_files_delimiter(code_text)
        if not files:
            parsed = self._parse_output(code_text)
            state[stage.output_artifact] = parsed.artifact if isinstance(parsed.artifact, dict) else {}
        else:
            state[stage.output_artifact] = {"files": files, "skills_created": [], "agents_created": [], "tools_created": []}
        state["issues"] = []
        self._persist_files(state.get(stage.output_artifact) or {}, state.get("output_dir", ""))
        return state

    async def _gen_test_plan(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        state = dict(state)
        prd = state.get("prd") or {}
        prompt = f"""Generate pytest test script from PRD.

## PRD
{json.dumps(self._truncate(prd, 2000), ensure_ascii=False, indent=2)}

Output ## FILE: format with pytest code. No JSON."""
        result = await self._stage_runner.run(prompt, state)
        parsed = self._parse_output(result)
        artifact = parsed.artifact if isinstance(parsed.artifact, dict) else {"test_script": result}
        state[stage.output_artifact] = artifact
        if stage.hitl:
            state["phase"] = BuilderSessionPhase.awaiting_test_plan_approval.value
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
                ctx[artifact_name] = self._truncate(val, 3000)
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
        output_dir = state.get("output_dir", "")
        deploy_dir = os.path.join(output_dir, "deploy")
        os.makedirs(deploy_dir, exist_ok=True)
        all_code = self._collect_upstream_code(state)
        for f in self._collect_files(all_code):
            path = f.get("path", "")
            content = f.get("content", "")
            if path and content:
                full = os.path.join(deploy_dir, path.lstrip("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(content)
        with open(os.path.join(deploy_dir, "Dockerfile"), "w") as f:
            f.write("FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"python\", \"main.py\"]")
        with open(os.path.join(deploy_dir, "requirements.txt"), "w") as f:
            f.write("fastapi\nuvicorn\n")
        return deploy_dir

    @staticmethod
    def _collect_files(artifact: Dict) -> List[Dict[str, str]]:
        files = []
        for f in (artifact.get("files") or []):
            if isinstance(f, dict):
                files.append({"path": f.get("path", ""), "content": f.get("content", "")})
        return files

    def _collect_upstream_code(self, state: PipelineState) -> Dict[str, Any]:
        all_code = {}
        for s in self._config.stages:
            if s.uses_code_skill and state.get(s.output_artifact):
                artifact = state[s.output_artifact]
                if isinstance(artifact, dict):
                    all_code = {**all_code, **artifact}
        for legacy_key in ("code", "backend_code", "frontend_code"):
            val = state.get(legacy_key)
            if val and isinstance(val, dict):
                all_code = {**all_code, **val}
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

    def _parse_output(self, raw: str) -> AgentOutput:
        json_str = self._extract_json(raw)
        if json_str:
            try:
                data = json.loads(json_str)
                artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else data
                issues = [Issue(severity=IssueSeverity(i.get("severity", "P1")),
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
    def _truncate(obj: Any, max_chars: int = 3000) -> Any:
        s = json.dumps(obj, ensure_ascii=False, default=str)
        if len(s) > max_chars:
            truncated = json.loads(s[:max_chars] + '..."')
            return truncated
        return obj

    async def run_auto(self, session_id: str, requirement: str = "",
                        prd_data: Optional[Dict] = None) -> PipelineState:
        return await self.initialize(session_id, requirement, prd_data=prd_data)
