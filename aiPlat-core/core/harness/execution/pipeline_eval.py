"""PipelineEvalMixin — test evaluation / triage methods for PipelineEngine.

Extracted from pipeline_engine.py (P2-A4 Phase 3, 2026-08-18). Pure structure
move: method bodies unchanged, no API/semantics change. Cross-domain helpers
(self._config / self._upstream_output / self._meta_optimize / self._exec_stage)
resolve via the MRO at runtime.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from core.harness.execution.phase import PipelinePhase
from core.schemas_builder import PipelineStageConfig


class PipelineEvalMixin:
    """Test execution, tri-evaluation, retry loop, output verification."""

    async def _verify_stage_output(

        self, stage: PipelineStageConfig, state: PipelineState

    ) -> None:

        u"""Run verification checks on stage output: expected outcomes + replay.



        Algorithm nodes always record replay snapshots.

        Stages with expected_outcomes in config get verified against constraints.

        """

        artifact = state.get(stage.output_artifact)

        if artifact is None:

            return



        try:

            from core.harness.execution.verification import (

                verify_against_expected, record_replay_snapshot, verify_replay,

            )



            # Compute input hash for replay tracking

            input_hash = state.get(f"_input_hash_{stage.id}", "")

            if not input_hash:

                import hashlib

                input_snapshot = str(artifact)[:500]

                input_hash = hashlib.sha256(input_snapshot.encode()).hexdigest()[:16]



            node_type = getattr(stage, 'node_type', '') or ''



            # Algorithm nodes: always record replay snapshots

            if node_type == 'algorithm':

                algo_result = None

                if isinstance(artifact, str):

                    try:

                        algo_result = __import__('json').loads(artifact)

                    except Exception as e:

                        logging.warning(str(e), exc_info=True)

                record_replay_snapshot(

                    str(state.get("session_id", "")),

                    stage.id, input_hash, str(artifact)[:2000],

                    algorithm_result=algo_result,

                )

                # Check replay consistency

                replay = verify_replay(

                    str(state.get("session_id", "")),

                    stage.id, input_hash, str(artifact)[:2000],

                    algorithm_result=algo_result,

                )

                if replay and not replay.replay_consistent:

                    logger.warning(

                        "Replay inconsistent for %s: %s", stage.id, replay.replay_diff,

                    )

                    state[f"_replay_{stage.id}"] = replay.to_dict()



            # Expected outcome verification

            expected_outcomes = getattr(stage, 'expected_outcomes', None) or []

            if expected_outcomes:

                result = verify_against_expected(artifact, expected_outcomes, stage_id=stage.id)

                state[f"_verify_{stage.id}"] = result.to_dict()

                if not result.verified:

                    state["_stage_verification_failed"] = True

                    msg = (

                        f"Verification failed for {stage.id}: "

                        f"{result.checks_failed}/{result.checks_passed + result.checks_failed} checks failed"

                    )

                    logger.warning(msg)

                    state.setdefault("_quick_check_issues", []).append(msg)



        except Exception as e:

            logging.getLogger("pipeline_engine").debug(

                "Verification skipped for stage %s: %s", stage.id, str(e)[:100],

            )

    async def _exec_test_runner(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        state = dict(state)

        output_dir = state.get("output_dir", "")

        # §7-5: system dependency health check — missing runtime deps → ENV_ERROR (not TEST_FAIL)
        import shutil as _shutil
        _env_issues = []
        for _dep in ("ffmpeg", "ffprobe"):
            if not _shutil.which(_dep):
                _env_issues.append(f"{_dep} not found on PATH")
        state["_test_env_issues"] = _env_issues

        test_plan = state.get(stage.output_artifact) or {}

        script = test_plan.get("test_script", "")

        result_key = stage.test_result_key

        if not script:

            test_report = await self._tri_evaluate(stage, state, pytest_output="")

            state[result_key] = test_report

            return state

        test_dir = os.path.join(output_dir, os.getenv("AIPLAT_TEST_DIR", "test"))

        # ── L2: skip_pytest_gate — user explicitly opted out of the real pytest
        #     gate (e.g. legacy imported repo has no tests). Mark state so the
        #     platform deploy path falls back to estimated pass rate (with reason).
        if state.get("skip_pytest_gate"):
            state["_test_pass_rate"] = None
            state["_has_tests"] = False
            state["_skip_pytest_gate"] = True
            state["_test_gate_skipped_reason"] = (
                "user skipped pytest gate (L2 import mode) — pass_rate will be estimated, not measured"
            )
            state[result_key] = {
                "pass": False, "pass_rate": 0, "score": {"overall": 0},
                "recommendation": "APPROVED_SKIPPED",
                "error": "pytest_gate_skipped",
                "reason": state["_test_gate_skipped_reason"],
                "test_cases": [], "issues": [],
            }
            return state

        os.makedirs(test_dir, exist_ok=True)

        test_file = os.getenv("AIPLAT_TEST_FILE", "test_api.py")

        await asyncio.to_thread(_write_file, os.path.join(test_dir, test_file), script)

        await asyncio.to_thread(_write_file, os.path.join(test_dir, "__init__.py"), "")

        all_files = self._collect_files(self._collect_upstream_code(state))

        # FIX B: If no upstream code found, don't run eval — return clear diagnostic

        if not all_files:

            state[result_key] = {

                "pass": False, "pass_rate": 0, "score": {"overall": 0},

                "recommendation": "REJECTED",

                "error": "no_upstream_code",

                "reason": "No upstream code files found. Check upstream code generation stages.",

                "test_cases": [], "issues": [],

            }

            return state

        for f in all_files:

            path = f.get("path", "") or f.get("file", "")

            content = f.get("content", "") or f.get("code", "")

            if path and content:

                try:

                    full = _safe_join(output_dir, path)

                except ValueError:

                    logging.getLogger("pipeline_engine").warning("test_runner path traversal blocked: %s", path)

                    continue

                    os.makedirs(os.path.dirname(full), exist_ok=True)

                    with open(full, "w", encoding="utf-8") as fh:

                        fh.write(content)

                except OSError:

                    pass  # noqa: cleanup-best-effort

        try:

            from core.harness.syscalls.tool import sys_tool_call

            from core.apps.tools.code import CodeExecutionTool  # noqa: allowed — data type (class) import

            exec_tool = CodeExecutionTool()

            test_cmd = os.getenv("AIPLAT_TEST_COMMAND", "")

            if not test_cmd:

                test_lang = os.getenv("AIPLAT_TEST_LANGUAGE", "python")

                if test_lang == "python":

                    test_cmd = f"pytest {test_dir} -v --tb=short"

                elif test_lang in ("node", "javascript", "typescript"):

                    test_cmd = f"npx jest {test_dir} --verbose"

                elif test_lang == "go":

                    test_cmd = f"go test {test_dir}/..."

                else:

                    test_cmd = f"pytest {test_dir} -v --tb=short"

            exec_code = os.getenv("AIPLAT_TEST_EXEC_CODE", "")

            if not exec_code:

                exec_code = (

                    f"import subprocess, sys; "

                    f"r = subprocess.run('{test_cmd}'.split(), capture_output=True, text=True, "

                    f"timeout=60, cwd='{output_dir}'); "

                    f"print(r.stdout[-3000:]); print('STDERR:', r.stderr[-500:] if r.stderr else '')"

                )

            exec_args = {

                "language": os.getenv("AIPLAT_TEST_LANGUAGE", "python"),

                "code": exec_code,

                "timeout": 60000,

            }

            result = await sys_tool_call(exec_tool, exec_args, user_id="system", session_id=str(state.get("session_id", "engine")))

            pytest_output = (getattr(result, 'output', {}) or {}).get("stdout", "") if getattr(result, 'success', False) else ""

        except Exception as e:

            pytest_output = f"TEST_EXECUTION_FAILED: {e}"

            state["_test_execution_error"] = str(e)[:500]

            state["error"] = str(e)[:200]

            return state

        # RTK-style compression: keep only summary + FAILED/ERROR headers, drop full stack traces.

        pytest_output = self._compress_pytest_output(pytest_output)

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

                        logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

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

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        upstream = self._upstream_output(state, include_outputs=set())

        # Config-driven: find the first non-code, non-test design stage for coverage tracing

        design_key = ""

        for s in self._config.stages:

            if s.output_artifact and s.output_artifact != stage.output_artifact and not s.uses_file_output and not s.generate_test_plan:

                design_key = s.output_artifact

        design = upstream.get(design_key, {})

        code_files = sum(len((state.get(s.output_artifact) or {}).get("files", [])) for s in self._config.stages if s.uses_file_output)

        cfg_fields = getattr(stage, 'coverage_trace_fields', None) or {}

        comp_key = cfg_fields.get("components_key", "components")

        api_key = cfg_fields.get("api_contracts_key", "api_contracts")

        data_key = cfg_fields.get("data_model_key", "data_model")

        test_report["_coverage_trace"] = {

            "components_designed": len(design.get(comp_key) or []),

            "api_contracts_defined": len(design.get(api_key) or []),

            "data_entities_defined": len(design.get(data_key) or {}),

            "files_implemented": code_files,

            "test_cases_produced": len(test_report.get("test_cases") or []),

            "cascade": {"components_to_files": round(code_files / max(len(design.get(comp_key) or []), 1), 2),

                         "files_to_tests": round(len(test_report.get("test_cases") or []) / max(code_files, 1), 2)},

        }

        state[result_key] = test_report

        # Auto-retry: REJECTED test report triggers retry on the specific failing stage

        if isinstance(test_report, dict) and test_report.get("recommendation") == "REJECTED":

            state["_test_rejected"] = True

            # Target: the stage mentioned in the first issue's target_agent,

            # falling back to any uses_file_output stage

            target_agent = ""

            issues = test_report.get("issues") or []

            if isinstance(issues, list) and issues:

                target_agent = str((issues[0] or {}).get("target_agent", "") or "").strip()

            for s in self._config.stages:

                if s.uses_file_output and not s.generate_test_plan:

                    if not target_agent or s.agent_id == target_agent or s.id == target_agent:

                        state = await self._retry_loop(s, state)

                        break

        return state

    async def _tri_evaluate(self, stage: PipelineStageConfig, state: Dict, pytest_output: str) -> Dict:

        # Parse pytest output structurally (e.g. "3 passed, 1 failed") instead of

        # string counting to avoid false matches on log lines containing "PASSED"/"FAILED"

        import re

        m = re.search(r'(\d+)\s+passed', pytest_output)

        passed = int(m.group(1)) if m else 0

        m = re.search(r'(\d+)\s+failed', pytest_output)

        failed = int(m.group(1)) if m else 0

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

            # No custom dimensions configured — skip dimensional threshold gate.

            # Scoring is config-driven per CLAUDE.md §5.29.

            dims = []

        dim_names = [d.get("name", "") for d in dims if d.get("name")]

        dim_lines = "; ".join(f"{d.get('name','')}({int(d.get('weight',0)*100)}%): {d.get('description','')}" for d in dims)

        primary_dim = dim_names[0] if dim_names else "overall"

        score_example = {d.get("name", ""): 8.0 for d in dims}

        score_example["overall"] = 7.5



        eval_template = os.getenv("AIPLAT_EVAL_TEMPLATE",

            """Evaluate the stage output based on requirements, code, and test results.



## Requirements

{prd}



## Code Files

{code_summary}



## Test Output

{pytest_output}



## Scoring Dimensions (0-10)

{dim_lines}



Output ONLY JSON: {{"pass":true,"score":{score_example},"pass_rate":{pass_rate},"test_cases":[],"issues":[],"recommendation":"<APPROVED|REJECTED>"}}

Evaluate pass/fail based on pass_rate and configured dimension thresholds.""")

        eval_prompt = eval_template.format(

            prd=json.dumps(self._summarize_artifact(prd), ensure_ascii=False, indent=2),

            code_summary=json.dumps(code_summary, ensure_ascii=False, indent=2),

            pytest_output=pytest_output[:3500] if pytest_output else '(no tests executed)',

            dim_lines=dim_lines,

            score_example=json.dumps(score_example),

            pass_rate=pass_rate,

        )

        eval_runner = self._eval_runner

        stage_eval_model = getattr(stage, 'eval_model', '') or ''

        if stage_eval_model:

            eval_runner = EvalRunner()

        result_text = await eval_runner.run(eval_prompt, state)

        report = {}

        json_str = self._extract_json(result_text)

        if json_str:

            try:

                report = json.loads(json_str)

            except json.JSONDecodeError:

                pass  # noqa: cleanup-best-effort

        if not isinstance(report, dict) or not report:

            issues = [l.strip()[:120] for l in pytest_output.split("\n") if "FAILED" in l or "Error" in l]

            fallback_score = {d.get("name", ""): pass_rate * 10 for d in dims if d.get("name")}

            fallback_score["overall"] = pass_rate * 10

            report = {"pass": pass_rate >= 0.8, "score": fallback_score,

                "pass_rate": pass_rate, "test_cases": [], "issues": [{"severity": "P1", "description": i} for i in issues[:10]],

                 "recommendation": "APPROVED" if pass_rate >= 0.8 else "REJECTED"}

        # ── Standards compliance check (best-effort) ──

        try:

            from core.harness.evaluation.standards_validator import StandardsValidator

            stage_output_text = str(state.get(stage.output_artifact, ""))

            if stage_output_text and len(stage_output_text) > 100:

                sv = StandardsValidator()

                sv_report = sv.validate(stage_output_text, doc_type=stage.output_artifact or "general")

                if sv_report and hasattr(sv_report, 'issues'):

                    report.setdefault("standards_issues", []).extend(

                        {"rule": i.rule_id, "level": i.level or "warning",

                         "message": i.message}

                        for i in sv_report.issues[:5])

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
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

        tolerance = getattr(stage, 'deviation_tolerance', 0.0) or 0.0

        if tolerance > 0 and score.get("overall", 0) >= tolerance:

            report["pass"] = True

            report["recommendation"] = "APPROVED"

            state["_last_action_reason"] = "tolerated_deviation"

            try:

                artifact = state.get(stage.output_artifact)

                if isinstance(artifact, str) and artifact:

                    fixed = PostprocessCorrector.auto_fix_json(artifact)

                    if fixed != artifact:

                        state[stage.output_artifact] = fixed

                        state["_postprocess_applied"] = True

            except Exception as e:

                logging.warning(str(e), exc_info=True)

        # Track score history for convergence detection and meta-optimization feedback

        state.setdefault("_score_history", []).append({

            "iteration": state.get("iteration", 0),

            "overall": score.get("overall", 0),

            "pass_rate": pass_rate,

            "recommendation": report.get("recommendation", ""),

            "dimensions": {d.get("name", ""): score.get(d.get("name", 0)) for d in dims},

        })

        # A/B feedback loop: record score against prompt version for auto-optimization

        try:

            from core.harness.evaluation.ab_optimizer import EvalABOptimizer

            ctx_asm = state.get("_context_assembly") or {}

            prompt_version = ctx_asm.get("prompt_version") or ctx_asm.get("meta", {}).get("prompt_version", "")

            if prompt_version:

                EvalABOptimizer.record_score(

                    template_id=stage.agent_id,

                    version=prompt_version,

                    overall_score=float(score.get("overall", 0)),

                    pass_rate=float(pass_rate),

                    recommendation=str(report.get("recommendation", "")),

                    session_id=str(state.get("session_id", "")),

                )

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # Health Report: per-stage dimensional scoring for quality dashboard

        health_dims = []

        for d in dims:

            dname = d.get("name", "unknown")

            health_dims.append({

                "name": dname, "display_name": d.get("description", dname),

                "score": float(score.get(dname, 0)), "max_score": 10.0,

                "weight": float(d.get("weight", 1.0)), "pass_threshold": float(d.get("threshold", 7.0)),

                "issues_count": len(report.get("issues", [])),

            })

        overall = sum(d["score"] * d["weight"] for d in health_dims) / max(sum(d["weight"] for d in health_dims), 0.01)

        verdict = "passed" if overall >= 7.0 and pass_rate >= 0.8 else ("partial" if overall >= 4.0 else "failed")

        state[f"_health_report_{stage.id}"] = {

            "stage_id": stage.id, "agent_id": stage.agent_id,

            "dimensions": health_dims, "overall_score": round(overall * 10, 1),

            "verdict": verdict,

        }

        # RAG evaluation: wire ragas metrics when scoring dimensions include RAG dimensions

        try:

            rag_dims = [d.get("name", "") for d in dims if d.get("name", "") in ("faithfulness", "context_relevance", "answer_relevance", "context_precision", "context_recall")]

            if rag_dims:

                from core.harness.evaluation.rag_evaluator import EvalSample

                answer_text = str(report.get("output", report.get("artifact", ""))) if isinstance(report, dict) else ""

                contexts = [state.get(s.output_artifact, "") for s in self._config.stages]

                contexts = [str(c) for c in contexts if c]

                sample = EvalSample(

                    question=str(state.get("description", "")),

                    answer=answer_text[:3000] if answer_text else "",

                    contexts=contexts[:5],

                )

                try:

                    from core.harness.evaluation.rag_evaluator import RagEvaluator

                    evaluator = RagEvaluator()

                    rag_result = await evaluator.evaluate_sample(sample)

                    state[f"_rag_eval_{stage.id}"] = rag_result.to_dict() if hasattr(rag_result, 'to_dict') else str(rag_result)

                except Exception as e:

                    logging.warning(str(e), exc_info=True)

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # AST graph diff for semantic-level regression detection

        try:

            from core.harness.evaluation.graph_diff import parse_code_to_graph, diff_graphs

            prev_report = state.get(f"_prev_{stage.test_result_key}", {})

            if isinstance(prev_report, dict) and prev_report.get("code_graph"):

                current_graph = parse_code_to_graph(json.dumps(code_summary, ensure_ascii=False))

                diff = diff_graphs(prev_report.get("code_graph", {}), current_graph)

                if diff.get("verdict") == "regression":

                    report.setdefault("_compare", {})["graph_diff"] = diff

            report["code_graph"] = parse_code_to_graph(json.dumps(code_summary, ensure_ascii=False))

            state[f"_prev_{stage.test_result_key}"] = report

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        return report

    async def _gen_test_plan(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        state = dict(state)

        prompt = self._build_prompt(stage, state)

        if getattr(stage, 'render_upstream', False):

            upstream = {}

            for s in self._config.stages:

                if s.id == stage.id:

                    break

                val = state.get(s.output_artifact)

                if val:

                    upstream[s.output_artifact] = val

            if upstream:

                from core.harness.execution.renderer import inject_rendered_output

                stage_names = {s.output_artifact: s.agent_name or s.id for s in self._config.stages}

                prompt = inject_rendered_output(prompt, upstream, stage_names)

        result = await self._stage_runner.run(prompt, state, stage=stage)

        parsed = self._parse_output(result)

        artifact = parsed.artifact if isinstance(parsed.artifact, dict) else {"test_cases": [], "pass_rate": 0, "recommendation": "REJECTED"}

        if "test_cases" in artifact:

            state[stage.test_result_key or stage.output_artifact] = artifact

        else:

            artifact = {"test_cases": [], "pass_rate": 0, "recommendation": "REJECTED"}

            state[stage.output_artifact] = artifact

        if stage.hitl:

            state["phase"] = PipelinePhase.PAUSED

            state["_hitl_phase_name"] = stage.hitl_phase

            self._snapshot(state, f"stage_{stage.id}_test_plan")

        return state

    async def _retry_loop(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        state = dict(state)

        max_stag = self._config.max_stagnation

        cfg_budget = self._config.max_tokens_per_run

        max_attempts = getattr(self._config, 'max_retry_attempts', None) or 3

        # Per-stage retry policy (from PipelineStageConfig.retry_policy)
        _retry_pol = getattr(stage, 'retry_policy', {}) or {}
        if _retry_pol and _retry_pol.get("max_retries"):
            max_attempts = int(_retry_pol["max_retries"])

        # Per-node overrides from workflow canvas

        node_cfg = getattr(stage, 'node_config', None) or {}

        max_attempts = int(node_cfg.get('retry_count', max_attempts))



        def _over_budget():

            u = state.get("tokens_used", 0)

            b = state.get("tokens_budget") or cfg_budget or 100000

            return u >= b



        attempt = 0

        loop_start = time.time()

        stage_timeout = getattr(stage, 'stage_timeout_seconds', None) or 600

        # Per-node timeout override from canvas

        stage_timeout = int(node_cfg.get('timeout_sec', stage_timeout))

        while True:

            attempt += 1

            elapsed = time.time() - loop_start

            if elapsed > stage_timeout:

                state["error"] = f"stage_timeout ({elapsed:.0f}s > {stage_timeout}s)"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "stage_timeout"

                break

            state["qa_retry"] = state.get("qa_retry", 0) + 1

            b = state.get("tokens_budget") or cfg_budget or 100000

            if attempt > max_attempts:

                state["error"] = f"max_retry_attempts ({max_attempts}) exceeded"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "retry_max_attempts"

                break

            # Convergence detection: score plateau for N consecutive iterations

            history = state.get("_score_history", [])

            win = int(os.getenv("AIPLAT_CONVERGENCE_WINDOW", "4"))

            threshold = float(os.getenv("AIPLAT_CONVERGENCE_THRESHOLD", "0.03"))

            if len(history) >= win:

                recent = [h.get("overall", 0) for h in history[-win:]]

                if max(recent) - min(recent) < threshold:

                    state["error"] = "score plateaued — meta-optimization unable to improve"

                    state["phase"] = PipelinePhase.FAILED

                    state["_last_action_reason"] = "score_converged"

                    break

            if _over_budget():

                state["error"] = "token_budget_exhausted"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "retry_budget_exhausted"

                break

            if state.get("_stagnation_count", 0) >= max_stag:

                state["error"] = f"stagnation ({state['_stagnation_count']} rounds unchanged)"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "retry_stagnation"

                break

            if self._check_done(stage, state):

                state["phase"] = PipelinePhase.DONE

                # OTel trace export (best-effort)

                if os.getenv("AIPLAT_OTEL_EXPORT_ENABLED", "").lower() in ("true","1","yes"):

                    try:

                        trace = state.get("_graph_trace", [])

                        out_path = os.getenv("AIPLAT_OTEL_EXPORT_PATH", os.path.expanduser("~/.aiplat/traces/latest.json"))

                        export_otel_trace(trace, out_path)

                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

                # Save execution state snapshot for history

                try:

                    snapshot_dir = os.path.expanduser("~/.aiplat/traces/history")

                    os.makedirs(snapshot_dir, exist_ok=True)

                    ts = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')

                    snap = {"ts": ts, "phase": state.get("phase",""), "tokens": state.get("tokens_used",0),

                            "stages": {s.id: {"status": "completed" if state.get(f"_stage_{s.id}_done") else "pending",

                            "output": str(state.get(s.output_artifact,""))[:1000]} for s in self._config.stages}}

                    snap_path = os.path.join(snapshot_dir, f"{state.get('session_id','unknown')}_{ts}.json")

                    with open(snap_path, 'w') as sf: json.dump(snap, sf, ensure_ascii=False, indent=2)

                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

                break

            report = state.get(stage.output_artifact)

            if report and isinstance(report, dict) and report.get("recommendation") == "REJECTED":

                tol = getattr(stage, 'deviation_tolerance', 0.0) or 0.0

                if tol > 0 and report.get("score", {}).get("overall", 0) >= tol:

                    state["_last_action_reason"] = "tolerated_deviation"

                    state["_skip_retry_on_tolerance"] = True

                    break

                auto_r = state.get("_auto_retry_count", 0) + 1

                state["_auto_retry_count"] = auto_r

                max_auto_retries = getattr(self._config, 'max_auto_retries', None) or 3

                if auto_r > max_auto_retries:

                    state["error"] = f"auto_retry_exhausted ({max_auto_retries} evaluation rejections)"

                    state["phase"] = PipelinePhase.FAILED

                    state["_last_action_reason"] = "evaluation_rejected_max_auto_retry"

                    # Git rollback to last passing tag

                    self._git_rollback_to_last_good(state)

                    break

            if report and isinstance(report, dict):

                compare = report.get("_compare", {})

                if isinstance(compare, dict) and compare.get("verdict") == "regressed":

                    state["error"] = "evaluation regressed"

                    state["phase"] = PipelinePhase.FAILED

                    state["_last_action_reason"] = "evaluation_regressed"

                    self._git_rollback_to_last_good(state)

                    break

            # Meta-optimization: after 3+ retries still REJECTED, try config changes

            report = state.get(stage.output_artifact)

            if attempt >= 3 and isinstance(report, dict) and report.get("recommendation") == "REJECTED":

                optimized = await self._meta_optimize(stage, report, state)

                if optimized is None:

                    if state.get(f"_stage_{stage.id}_skipped"):

                        # Phase 24: intentional skip by self-healing, not a failure

                        state["phase"] = PipelinePhase.DONE

                        state["_last_action_reason"] = "stage_skipped_by_healing"

                        break

                    state["error"] = "meta_optimize_failed"

                    state["phase"] = PipelinePhase.FAILED

                    state["_last_action_reason"] = "meta_optimize_failed"

                    break

            eval_state = await self._exec_stage(stage, state)

            state.update(eval_state)

            if _over_budget() or self._check_done(stage, state):

                state["phase"] = PipelinePhase.DONE if self._check_done(stage, state) else state.get("phase", "")

                break

            target = self._resolve_retry_target(stage, state)

            if not target:

                state["error"] = f"No retry target found for stage {stage.id}"

                state["phase"] = PipelinePhase.FAILED

                break

            fix = await self._exec_fix_stage(target, stage, state)

            state.update(fix)

            if _over_budget():

                state["error"] = "token_budget_exhausted"

                state["phase"] = PipelinePhase.FAILED

                break

            eval_state = await self._exec_stage(stage, state)

            state.update(eval_state)

            if attempt < max_attempts:

                delay = 2 ** (attempt - 1)

                await asyncio.sleep(delay)

        return state

    def _compress_pytest_output(raw: str) -> str:

        """RTK-style compression: keep summary + first N failures, drop stack traces.



        A 155-line pytest output (warnings, deprecation notices, full stack traces)

        compresses to ~10 lines: summary + failed test names + first failure details.

        """

        if not raw or len(raw) < 200:

            return raw

        lines = raw.split("\n")

        result_lines = []

        # Always keep the summary line (e.g. "3 passed, 1 failed in 2.34s")

        for line in lines:

            stripped = line.strip()

            if "passed" in stripped and ("failed" in stripped or "error" in stripped):

                result_lines.append(stripped)

                break

        if not result_lines:

            result_lines = [l.strip() for l in lines[-2:] if l.strip()]

        # Keep first 5 FAILED/ERROR test name lines

        fail_count = 0

        for line in lines:

            stripped = line.strip()

            if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):

                result_lines.append(stripped)

                fail_count += 1

                if fail_count >= 5:

                    break

        if len(lines) - len(result_lines) > 10:

            result_lines.append(f"[RTK: compressed {len(lines)} lines → {len(result_lines)} lines]")

        return "\n".join(result_lines)