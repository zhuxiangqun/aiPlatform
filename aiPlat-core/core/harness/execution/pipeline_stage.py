"""PipelineStageMixin — stage dispatch / execution domain for PipelineEngine.

Extracted from pipeline_engine.py (P2-A4 Phase 4, 2026-08). Pure structure
move: method bodies unchanged, no API/semantics change. Cross-domain helpers
(self._model / self._persist_callback / self._run_stage_skill / self._config /
self._exec_single_stage / self._run_stage_core / self._stage_runner ...) resolve
via the MRO at runtime from PipelineEngine / sibling mixins.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig


class PipelineStageMixin:
    """Stage dispatch tables, capability profiling, isolated/health execution."""

    async def _dispatch_execute(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        """Execute stage based on declarative execution_mode field."""

        import time as _time
        _t0 = _time.time()
        mode = getattr(stage, 'execution_mode', 'code_first') or 'code_first'



        # ── Lazy-init SkillRegistry for skill-based pipeline stages ──
        if not getattr(self, '_skills_loaded', False):
            try:
                from core.harness.integration import get_skill_registry
                _reg = get_skill_registry()
                if _reg and hasattr(_reg, 'seed_data'):
                    _reg.seed_data()
                self._skills_loaded = True
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # best-effort: fallback to ReAct if registry unavailable

        # ── Broadcast progress for ALL stages (not just skill-based) ──
        _stage_tag = getattr(stage, 'output_artifact', '') or stage.id
        state["_progress"] = {"stage": _stage_tag, "status": "running",
                              "started_at": _t0, "backend": "agent"}

        # ── Unified skill dispatch ──
        # Stages with skill_name must NOT fall through to ReAct.
        # _run_stage_skill handles all errors internally — even empty output
        # is a valid signal (no output for this stage), not a reason to bypass.
        if getattr(stage, 'skill_name', ''):
            _artifact_key = getattr(stage, 'output_artifact', '') or getattr(stage, 'skill_name', '')
            _max_json_retries = 5
            _batch_accumulator: list = []     # aggregate results across completeness retries
            _batch_complete = False
            for _json_try in range(_max_json_retries + 1):
                result = await self._run_stage_skill(stage, state)
                _output = str(result.get(_artifact_key, {}).get('raw_output', '') or '')
                if not _output.strip().startswith('{'):
                    break  # not JSON output, no validation needed
                try:
                    import json as _json_mod
                    _parsed = _json_mod.loads(_output)
                    # ── Completeness check: progressive batch execution ──
                    _cc = getattr(stage, 'completeness_check', None)
                    if _cc and not _batch_complete:
                        _cc_input_key = _cc.get("input_artifact", "")
                        _cc_output_key = _cc.get("output_key", "test_results")
                        _cc_max_per = _cc.get("max_per_call", 10)
                        _cc_input_raw = (state.get(_cc_input_key, {}).get("raw_output", "")
                            if isinstance(state.get(_cc_input_key, {}), dict) else "")
                        if _cc_input_raw:
                            try:
                                _cc_items_raw = _cc_input_raw
                                if isinstance(_cc_items_raw, str):
                                    _cc_items_raw = _cc_items_raw.strip()
                                    if not _cc_items_raw.startswith(('[', '{')):
                                        import re
                                        _m = re.search(r'\{.*\}|\[.*\]', _cc_items_raw, re.DOTALL)
                                        if _m:
                                            _cc_items_raw = _m.group(0)
                                _cc_items = _json_mod.loads(_cc_items_raw) if isinstance(_cc_items_raw, str) else _cc_items_raw
                                # Support nested fields (e.g., prd.functional_requirements)
                                _cc_input_field = _cc.get("input_field", "")
                                if _cc_input_field and isinstance(_cc_items, dict):
                                    _cc_items = _cc_items.get(_cc_input_field, [])
                                _expected = len(_cc_items) if isinstance(_cc_items, list) else 0
                                _batch_items = _parsed.get(_cc_output_key, [])
                                _batch_accumulator.extend(_batch_items)
                                _covered = len(_batch_accumulator)
                                if _expected > _covered and _json_try < _max_json_retries:
                                    _start = _covered
                                    _end = min(_start + _cc_max_per, _expected)
                                    _remaining = _cc_items[_start:_end]
                                    _err_msg = f"[complete {_json_try+1}/{_max_json_retries}] only covered {_covered}/{_expected} items. Continue items {_start+1}-{_end}: {_json_mod.dumps(_remaining, ensure_ascii=False)[:800]}"
                                    _log.getLogger("pipeline_engine").warning(
                                        "Skill %s completeness retry: %d/%d items", getattr(stage,'skill_name',''), _covered, _expected)
                                    state["_reject_feedback"] = _err_msg
                                    result.pop(_artifact_key, None)
                                    continue  # retry the JSON retry loop
                                else:
                                    _batch_complete = True
                                    # Merge all batch results into final output
                                    _merged = dict(_parsed)
                                    _merged[_cc_output_key] = _batch_accumulator
                                    result[_artifact_key] = {"raw_output": _json_mod.dumps(_merged, ensure_ascii=False),
                                                             "elapsed_sec": 0}
                                    _json_mod.loads(result[_artifact_key]["raw_output"])  # re-validate
                            except Exception:
                                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                    break  # valid JSON (or batch complete)
                except _json_mod.JSONDecodeError as _je:
                    if _json_try < _max_json_retries:
                        _err_msg = f"[Auto-Fix {_json_try+1}/{_max_json_retries}] JSON parse failed: {_je.msg} (line {_je.lineno}, col {_je.colno}). Please re-output valid JSON, no TypeScript syntax like `| null`, no trailing commas."
                        _log.getLogger("pipeline_engine").warning(
                            "Skill %s JSON invalid (retry %d/%d): %s", getattr(stage,'skill_name',''), _json_try+1, _max_json_retries, _je.msg)
                        state["_reject_feedback"] = _err_msg
                        result.pop(_artifact_key, None)  # clear bad output
                    else:
                        break  # max retries, let user see the bad output
        else:
            # code_first (default) — ReAct path ONLY for stages without skill_name
            result = await self._exec_stage(stage, state)

        # ── Safety net: normalize app_name/project_id in stage output to canonical value ──
        _canonical_app = state.get("app_name", "")
        if _canonical_app:
            _art_key = getattr(stage, 'output_artifact', '') or getattr(stage, 'skill_name', '')
            _raw = result.get(_art_key, {}).get('raw_output', '') if isinstance(result.get(_art_key), dict) else ''
            if isinstance(_raw, str) and _raw.strip():
                try:
                    import json as _norm_json
                    _parsed = _norm_json.loads(_raw)
                    if isinstance(_parsed, dict):
                        _changed = False
                        if "app_name" in _parsed and _parsed["app_name"] != _canonical_app:
                            _parsed["app_name"] = _canonical_app
                            _changed = True
                        if _changed:
                            result[_art_key] = {"raw_output": _norm_json.dumps(_parsed, ensure_ascii=False),
                                                "elapsed_sec": result.get(_art_key, {}).get("elapsed_sec", 0)}
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── Broadcast stage completion ──
        _elapsed_sec = round(_time.time() - _t0, 2)
        state["_progress"] = {"stage": _stage_tag, "status": "completed",
                              "elapsed_sec": _elapsed_sec, "backend": "agent"}

        # ── Record stage trace for reasoning visibility ──
        _trace_key = f"_trace_{stage.id}"
        if _trace_key not in result:
            _elapsed = round(_time.time() - _t0, 2)
            _model_meta = {}
            try:
                from core.harness.utils.model_injection import best_model_for_purpose_with_meta
                _model_meta = best_model_for_purpose_with_meta(getattr(stage, 'skill_model_purpose', '') or 'chat')
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            result[_trace_key] = {
                "stage_id": stage.id,
                "agent_id": getattr(stage, 'agent_id', '') or '',
                "phase": getattr(stage, 'phase', '') or '',
                "skill_name": getattr(stage, 'skill_name', '') or '',
                "model_name": _model_meta.get("model", self._model),
                "model_purpose": getattr(stage, 'skill_model_purpose', '') or 'chat',
                "elapsed_sec": _elapsed,
                "retry_count": result.get(f"_retry_{stage.id}", 0),
                "failure_strategy": getattr(stage, 'failure_strategy', 'fail_pipeline') or 'fail_pipeline',
                "strategy": "react",
                "model_tier": _model_meta.get("model_tier", ""),
            "complexity_range": _model_meta.get("complexity_range", []),

            }
        result.pop(f"_retry_{stage.id}", None)  # clean up retry counter from state

        # ── Evaluate stage health BEFORE persist (ensures report is written even if persist fails) ──
        await self._evaluate_stage_health(stage, result)

        # Persist state after every stage (skill or react) for frontend polling
        try:
            if self._persist_callback:
                self._persist_callback(dict(result))
        except Exception:
            _log.getLogger("pipeline_engine").warning(
                "persist_callback failed for stage=%s", stage.id, exc_info=True)
            pass

        return result


    # ═══ v3.0: Capability Profile — static inference + runtime injection ═══


    @staticmethod
    def _infer_profile_from_stage(stage) -> str:
        """Static inference — shared by team_planner (build time) and engine (runtime).
        orchestrator → collaborative | react/tool/subagent → autonomous
        required_tools/skills → full | hitl/gen_test_plan → full
        phase + depends_on → standard | else → minimal
        """
        agent_type = getattr(stage, 'agent_type', '') or ''
        tools = getattr(stage, 'required_tools', []) or []
        skills = getattr(stage, 'required_skills', []) or []
        pipeline_mode = getattr(stage, 'pipeline_mode', '') or ''

        if agent_type == "orchestrator" or pipeline_mode == "orchestrator":
            return "collaborative"
        if agent_type in ("react", "tool", "subagent"):
            return "autonomous"
        if tools or skills:
            return "full"
        if getattr(stage, 'hitl', False) or getattr(stage, 'generate_test_plan', False):
            return "full"
        if getattr(stage, 'phase', '') and getattr(stage, 'depends_on', []):
            return "standard"
        return "minimal"


    # ═══ v5.0: Runtime Profile Calibration ═══


    async def _calibrate_profile_from_history(self, stage, state) -> Dict[str, Any]:
        """v5.0: compare Agent declarations vs actual runtime behavior to calibrate the capability profile.

        Data source: execution_store.get_recent_syscall_events(run_id, limit=50)
        The kind + name fields distinguish tool calls from skill calls.

        Decision rules:
          - Cold start (<10 events) → insufficient_data
          - Used 2+ undeclared tools + currently zero declared tools + steps > 3 → upgrade_recommended→full
          - Agent executes declared Skills normally → tolerate implicit Skill dependencies
          - Declared tools but never used + ≥20 events → downgrade_suggested
        """
        import logging as _lg
        _logger = _lg.getLogger("pipeline_engine.calibration")

        run_id = state.get("_run_id", "") or state.get("run_id", "")
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            events = await store.get_recent_syscall_events(run_id, limit=50)
        except Exception:
            return {"status": "error", "reason": "execution_store unavailable"}

        # ── cold-start protection ──
        if len(events) < 10:
            return {"status": "insufficient_data", "samples": len(events)}

        # ── separate tool calls vs skill calls ──
        actual_tools: set = set()
        actual_skills: set = set()
        for e in events:
            name = e.get("name", "")
            kind = e.get("kind", "")
            if not name:
                continue
            if kind and "tool" in kind.lower():
                actual_tools.add(name)
            elif kind and ("skill" in kind.lower() or "exec" in kind.lower()):
                actual_skills.add(name)

        # ── declared vs actual comparison ──
        declared_tools = set(getattr(stage, 'required_tools', []))
        declared_skills = set(getattr(stage, 'required_skills', []))
        unused_tools = declared_tools - actual_tools
        undeclared_tools = actual_tools - declared_tools

        # ── fault tolerance: implicit Skill dependencies ──
        if actual_skills & declared_skills:
            undeclared_tools = set()

        # ── upgrade decision ──
        # NOTE: v5.1 avg_steps should read the historical average step count from execution_store
        avg_steps = int(state.get("step_count", 0) or 0)
        if undeclared_tools and not declared_tools:
            if len(undeclared_tools) >= 2 and avg_steps > 3:
                _logger.warning(
                    "undeclared tools %s in %d runs, recommending upgrade",
                    undeclared_tools, len(events))
                return {
                    "status": "upgrade_recommended",
                    "current_profile": getattr(stage, 'capability_profile', 'auto'),
                    "recommended_profile": "full",
                    "undeclared_tools": list(undeclared_tools),
                    "samples": len(events),
                }

        # ── downgrade suggestion ──
        if unused_tools and len(events) >= 20:
            _logger.info(
                "%d declared but unused tools in %d runs — consider cleanup",
                len(unused_tools), len(events))
            return {
                "status": "downgrade_suggested",
                "unused_tools": list(unused_tools),
                "samples": len(events),
            }

        return {"status": "consistent", "samples": len(events)}


    async def _apply_capability_profile(self, stage, state) -> str:
        """Inject capability set per tier. Returns effective tier.
        full/autonomous → agent backend + tools/skills + safety
        minimal/standard no tools → downgrade agent→llm to save resources
        """
        import logging as _log

        profile = getattr(stage, 'capability_profile', 'auto') or 'auto'
        if profile == "auto":
            profile = self._infer_profile_from_stage(stage)

        tools = getattr(stage, 'required_tools', []) or []
        skills = getattr(stage, 'required_skills', []) or []

        if profile in ("standard", "full", "autonomous", "collaborative", "self_evolving", "persistent"):
            state["_trace_enabled"] = True
            state["_metrics_enabled"] = True

        if profile in ("full", "autonomous", "collaborative", "self_evolving", "persistent"):
            state["_policy_gate_enabled"] = True
            state["_pii_detect_enabled"] = True

        if profile in ("autonomous", "collaborative", "self_evolving", "persistent"):
            state["_reflection_enabled"] = True
            state["_task_skills_enabled"] = True

        if profile == "collaborative":
            stage.pipeline_mode = "orchestrator"
            stage.agent_type = getattr(stage, 'agent_type', '') or "orchestrator"
            state["_subagent_coordinator_enabled"] = True
            state["_agent_message_bus_enabled"] = True
            # P2: require tool call rationale for traceability
            state["_tool_rationale_required"] = True

        if profile in ("self_evolving", "collaborative"):
            state["_adaptive_security"] = True
            state["_online_evolution_enabled"] = True

        if profile == "persistent":
            state["_auto_resume_on_failure"] = True

        if profile in ("minimal", "standard"):
            if getattr(stage, 'execution_backend', 'llm') == "agent":
                if not tools and not skills:
                    stage.execution_backend = "llm"

        # ── v5.0: Runtime profile calibration ──
        _cal = await self._calibrate_profile_from_history(stage, state)
        if _cal.get("status") == "upgrade_recommended":
            _new = _cal.get("recommended_profile")
            _mode = __import__("os").environ.get("AIPLAT_PROFILE_CALIBRATE", "log")
            _clog = __import__("logging").getLogger("pipeline_engine")
            if _mode in ("upgrade", "full"):
                _clog.warning("Profile auto-upgraded: %s → %s (%d undeclared tools)",
                              profile, _new, len(_cal.get("undeclared_tools", [])))
                profile = _new
                state["_profile_auto_upgraded"] = True
            else:
                _clog.info("Calibration suggests: %s → %s (mode=log, not applied)",
                           profile, _new)

        _log.getLogger("pipeline_engine").debug(
            "capability_profile=%s backend=%s calibration=%s", profile,
            getattr(stage, 'execution_backend', 'llm'), _cal.get("status", "n/a"))
        return profile


    def _build_handler_params(self, stage: PipelineStageConfig, state: PipelineState) -> Dict[str, Any]:
        """Construct handler params from input_artifacts (config-driven, no hardcoded keys).

        For each declared input_artifact, pass its raw_output to the handler.
        JSON-shaped artifacts (dict/array) are parsed; others passed as text.
        """
        import json as _hj
        params: Dict[str, Any] = {}
        for _key in (getattr(stage, 'input_artifacts', []) or []):
            _v = state.get(_key)
            if isinstance(_v, dict) and _v.get("raw_output"):
                _raw = str(_v["raw_output"]).strip()
                if _raw.startswith(("{", "[")):
                    try:
                        params[_key] = _hj.loads(_raw)
                    except Exception:
                        params[_key] = _raw
                else:
                    params[_key] = _raw
        params.setdefault("project", state.get("app_name") or state.get("description") or "")
        return params


    async def _exec_isolated_stage(

        self, *, stage_id: str, mock_input: dict, state_ctx: dict

    ) -> dict:

        """Step-Run: execute a single stage with mock input, no upstream dependency.

        

        Returns the stage output for debugging purposes.

        """

        # Find the stage config

        stage = None

        for s in self._config.stages:

            if getattr(s, 'id', '') == stage_id:

                stage = s

                break

        if not stage:

            raise ValueError(f"Stage not found: {stage_id}")



        # Build isolated state: inject mock data as if upstream completed

        isolated_state = dict(state_ctx)

        isolated_state["_mock_step_run"] = True

        isolated_state["_current_stage_idx"] = 999  # isolated, not part of real pipeline



        # Inject mock_input into state under the expected keys

        for k, v in mock_input.items():

            isolated_state[k] = v

            isolated_state[f"_stage_input_{stage_id}"] = json.dumps(mock_input, ensure_ascii=False)[:1000]



        # Mark upstream stages as done so skip-checks pass

        for i, s in enumerate(self._config.stages):

            if getattr(s, 'id', '') == stage_id:

                break

            isolated_state[s.output_artifact] = f"[mock] upstream stage {i} output"



        # Execute the single stage

        import time

        start = time.time()

        result, is_paused = await self._exec_single_stage(stage, 0, isolated_state) or ({}, False)

        elapsed = time.time() - start



        output = result.get(stage.output_artifact, "") if isinstance(result, dict) else str(result)

        return {

            "output": str(output)[:5000],

            "elapsed_ms": round(elapsed * 1000, 1),

            "artifact_key": stage.output_artifact,

            "is_paused": is_paused,

        }


    async def _exec_stage(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        """Generic stage execution with dynamic routing.



        Execution mode is chosen by priority:

        1. Sandbox (stage.sandbox=True) — isolated subprocess

        2. Dynamic upgrade from react → plan/reflection based on signals:

           - retry + errors → plan (structured repair)

           - large task → plan (break down first)

           - upstream errors → reflection (verify before proceed)

        3. Static agent_type (conversational/rag/plan_execute/etc.) → core_chat

        4. Default → react via StageRunner

        """

        artifact = None  # Prevent UnboundLocalError (Python 3.13 scoping)

        # Start/End are declarative — no execution needed (matching Dify/Coze pattern)

        node_type = getattr(stage, 'node_type', None) or ''

        if node_type in ('start', 'end'):

            state = dict(state)

            state[f"_stage_{stage.id}_done"] = True

            state[f"_stage_elapsed_{stage.id}"] = 0.0

            if node_type == 'start':

                nc = getattr(stage, 'node_config', None) or {}

                inputs = nc.get('inputs', {})

                state[f"_stage_input_{stage.id}"] = json.dumps(inputs, ensure_ascii=False) if inputs else ''

            return state



        state = dict(state)



        # v2.8: Sandbox validation before stage execution

        sandbox_mode = getattr(stage, 'sandbox_mode', 'none') or 'none'

        if sandbox_mode != 'none':

            try:

                from core.harness.infrastructure.gates.sandbox_gate import SandboxGate

                gate = SandboxGate()

                if not gate.passes(stage):

                    raise Exception(f"Stage '{getattr(stage, 'name', '?')}' blocked by sandbox gate")

            except ImportError:

                pass  # noqa: optional-dependency



        used = state.get("tokens_used", 0)

        budget = state.get("tokens_budget", self._config.max_tokens_per_run or 100000)

        if used >= budget:

            state["error"] = f"token_budget_exhausted ({used}/{budget})"

            state["_last_action_reason"] = "budget_exhausted"

            state["phase"] = PipelinePhase.FAILED

            return state

        # ── Cost budget (USD) — config-driven, mirrors token budget ──
        _cost_used = float(state.get("cost_used_usd", 0.0) or 0.0)
        _cost_budget = float(getattr(self._config, 'max_cost_per_run_usd', 0.0) or 0.0)
        if _cost_budget > 0 and _cost_used >= _cost_budget:
            state["error"] = f"cost_budget_exhausted ({_cost_used:.4f}/{_cost_budget:.4f})"
            state["_last_action_reason"] = "cost_budget_exhausted"
            state["phase"] = PipelinePhase.FAILED
            return state



        # ── Degradation strategy (CLAUDE.md §5.17) ──

        consecutive_failures = state.get("_consecutive_llm_failures", 0)

        max_failures = getattr(stage, 'max_consecutive_llm_failures', None) or 3

        if consecutive_failures >= max_failures:

            strategy = getattr(stage, 'failure_strategy', None) or 'fail_pipeline'

            logging.getLogger("pipeline_engine").warning(

                "degradation triggered: stage=%s failures=%d/%d strategy=%s",

                stage.id, consecutive_failures, max_failures, strategy

            )

            if strategy == 'skip_stage':

                state[f"_stage_{stage.id}_done"] = True

                state["_last_action_reason"] = f"degradation_{strategy}"

                return state

            elif strategy == 'use_fallback_result':

                fb_key = getattr(stage, 'fallback_result_key', None) or ''

                if fb_key and state.get(fb_key):

                    state[stage.output_artifact] = state[fb_key]

                    state[f"_stage_{stage.id}_done"] = True

                    state["_last_action_reason"] = f"degradation_{strategy}"

                    return state

            state["error"] = f"consecutive_llm_failures ({consecutive_failures}) triggered {strategy}"

            state["_last_action_reason"] = f"degradation_{strategy}"

            return state



        # ── Stage timeout enforcement (§5.17, per-dimension defense audit) ──

        stage_timeout = getattr(stage, 'stage_timeout_seconds', None) or 600

        stage_start = state.get(f"_stage_ts_{stage.id}")

        if stage_start and time.time() - float(stage_start) > stage_timeout:

            state["error"] = f"stage_timeout ({int(time.time() - float(stage_start))}s > {stage_timeout}s)"

            state["phase"] = PipelinePhase.FAILED

            state["_last_action_reason"] = "stage_timeout"

            # PR #3: Stage timeout — attributed to D4_orchestration

            try:

                from core.harness.meta.profile_registry import set_failure_domain

                set_failure_domain("D4_orchestration")

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
            return state



        # Track consecutive LLM failures for degradation

        retry_on_rate = getattr(stage, 'retry_llm_on_rate_limit', None)

        state["_llm_rate_limit_retry"] = retry_on_rate if retry_on_rate is not None else True



        state["iteration"] = state.get("iteration", 0) + 1

        print(f"    [stage] {stage.id} (iter {state['iteration']}, {used}/{budget} tokens)")

        prompt = self._build_prompt(stage, state)

        state[f"_stage_input_{stage.id}"] = prompt[:5000]



        # Render upstream outputs as context for current stage (TradingAgents-inspired)

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



        # ── Route: dynamic mode upgrade for ReAct agents under conditions ──

        agent_type = getattr(stage, 'agent_type', '') or 'react'

        is_react_like = agent_type not in self._CONVERSATIONAL_AGENT_TYPES and agent_type not in self._PLAN_UPGRADE_TYPES

        if is_react_like:

            is_retry = state.get("_auto_retry_count", 0) > 0 or state.get("iteration", 0) > 1

            has_errors = bool(state.get("issues") or state.get("_quick_check_issues"))

            is_large = len(str(state.get("description", ""))) > 500

            if is_retry and has_errors:

                agent_type = 'plan'  # Retrying with errors → structured approach

            elif is_large and state.get("iteration", 0) == 1:

                agent_type = 'plan'  # Complex first-run → plan before execute

            elif has_errors and not is_retry:

                agent_type = 'reflection'  # Errors from upstream → verify before proceed



        # ── Router: model downgrade for simple tasks ──

        # Use lower-cost model for trivial tasks; complex tasks keep specified model.

        # Lock prevents race when multiple stages execute in parallel via asyncio.gather.

        async with self._model_lock:

            original_model = self._stage_runner._model

            stage_model = original_model

            stage_cfg_model = getattr(stage, 'model', None)

            if stage_cfg_model:

                from core.harness.utils.model_injection import create_selected_adapter

                stage_model = create_selected_adapter(model_name=stage_cfg_model)

                self._stage_runner._model = stage_model

            else:

                has_errors = bool(state.get("issues") or state.get("_quick_check_issues"))

                is_short = len(str(state.get("description", ""))) < 200

                is_first_run = state.get("iteration", 0) <= 2

                if not has_errors and is_short and is_first_run:

                    simple_model = best_model_for_purpose("chat")

                    stage_model = PipelineEngine._load_default_model(simple_model)

                    self._stage_runner._model = stage_model

                    state.setdefault("_model_log", []).append({

                        "stage": stage.id, "agent": stage.agent_id,

                        "model": simple_model, "reason": "simple_task_downgrade",

                    })



        # ── Pre-stage HITL: pause for human input (human stages only) ──

        node_type = getattr(stage, 'node_type', None) or 'agent'

        if stage.hitl and node_type == 'human' and not state.get(f"_hitl_resolved_{stage.id}"):

            state["phase"] = PipelinePhase.PAUSED

            state["_hitl_phase_name"] = stage.hitl_phase or f"{stage.id}_human_input"

            state["_hitl_stage_id"] = stage.id

            self._audit_hitl(state, "hitl_paused", detail=f"pre_stage:{stage.id}")

            self._snapshot(state, f"stage_{stage.id}_hitl_pause")

            return state



        try:

            result_text = await self._run_stage_core(stage, state, prompt, agent_type, stage_model)

            # Accumulate token usage from StageRunner/ReActLoop

            stage_tokens = state.get("_stage_tokens_used", 0)

            state["tokens_used"] = state.get("tokens_used", 0) + int(stage_tokens or 0)

            state.pop("_stage_tokens_used", None)

        except Exception as e:

            # Phase 24: Save raw exception for _meta_optimize

            state["_last_error"] = e

            state["_last_error_stage"] = stage.id

            # Phase 24: Classify via ErrorTranslator → recovery hints for Harness

            try:

                from core.harness.infrastructure.gates.error_translator import classify_api_error

                classed = classify_api_error(e, provider="", model=stage_model or "")

                state["_last_classified_error"] = {

                    "reason": classed.reason.value,

                    "retryable": classed.retryable,

                    "should_compress": classed.should_compress,

                    "should_rotate_credential": classed.should_rotate_credential,

                    "should_fallback": classed.should_fallback,

                    "retry_after_seconds": getattr(classed, "retry_after_seconds", None) or 0,

                }

            except Exception:

                state["_last_classified_error"] = None

            # Classify failure and record constraint metadata for observability

            import os as _os

            if _os.getenv("AIPLAT_ENABLE_FAILURE_CLASSIFICATION", "1").lower() not in ("0", "false", "no"):

                err_msg = str(e)

                ex_type = type(e).__name__

                ftype = FailureClassifier.classify(err_msg, ex_type)

                constraint = FailureClassifier.get_constraint(ftype, getattr(stage, 'failure_mode_constraints', None))

                FailureClassifier.record_escalation(state, ftype)

                state["_failure_classification"] = {

                    "type": ftype,

                    "constraint_action": constraint.get("constraint_action", "") if constraint else "",

                    "escalation": state.get(f"_escalation_{ftype}", 0),

                    "max_escalation": constraint.get("max_escalation", 0) if constraint else 0,

                }

                if self._try_constraint_action(stage, state):

                    state["_constraint_retry_pending"] = True

                    return state

                # Auto-improve AGENT.md prompt: when same failure hits 3x on same stage, inject anti-pattern rule

                if ftype != "unknown":

                    hist = state.setdefault("_failure_type_history", {}).setdefault(stage.id, {})

                    hist[ftype] = hist.get(ftype, 0) + 1

                    rule = FailureClassifier.get_auto_rule(ftype)

                    if hist[ftype] >= 3 and rule:

                        existing = str(getattr(stage, 'prompt_extra', '') or '')

                        if rule not in existing:

                            stage.prompt_extra = f"{existing}\n[AUTO-INJECTED] {rule}".strip()

                            state.setdefault("_auto_improvement_log", []).append({

                                "stage_id": stage.id, "failure_type": ftype,

                                "count": hist[ftype], "rule": rule,

                            })

                            hist[ftype] = 0  # reset counter after injection

                            # Also store failure pattern in semantic memory

                            try:

                                from core.harness.memory.manager import get_memory_manager

                                mgr = get_memory_manager()

                                await mgr.capture_to_semantic(

                                    key=f"failure_pattern:{ftype}",

                                    content=f"Stage {stage.id} repeatedly encounters {ftype}. Rule: {rule}",

                                    metadata={"stage_id": stage.id, "failure_type": ftype, "count": 3},

                                )

                            except Exception as e:

                                logging.warning(str(e), exc_info=True)



        state["step_count"] = state.get("step_count", 0)  # carried from stage_runner via shared state dict

        parsed = self._parse_output(result_text)

        if stage.uses_file_output:

            files = self._extract_files_delimiter(str(result_text))

            if files:

                state[stage.output_artifact] = {"files": files}

            else:

                state[stage.output_artifact] = {"raw_output": str(result_text)}

            state["issues"] = []

        else:

            artifact = parsed.artifact if isinstance(parsed.artifact, dict) else {}

            # Extract conversation updates from output

            conv_update = artifact.pop('conversation_update', None)

            if isinstance(conv_update, dict):

                conv = dict(state.get('_conversation_state') or state.get('conversation_state') or {})

                conv.update(conv_update)

                state['_conversation_state'] = conv

                state['conversation_state'] = conv

            state[stage.output_artifact] = artifact

            state["issues"] = [i.model_dump() for i in parsed.issues]

        # JSON Schema validation (if configured in node_config)

        _nc = getattr(stage, 'node_config', None) or {}

        output_schema_str = _nc.get('output_schema', '')

        if output_schema_str.strip():

            try:

                import jsonschema

                schema = json.loads(output_schema_str) if isinstance(output_schema_str, str) else output_schema_str

                target = state[stage.output_artifact]

                jsonschema.validate(instance=target, schema=schema)

                state["_schema_valid"] = True

            except Exception as e:

                state["_schema_valid"] = False

                state["_schema_error"] = str(e)[:200]

                if stage.failure_strategy == 'fail_pipeline':

                    state["phase"] = PipelinePhase.FAILED

                    state["error"] = f"Schema validation failed: {e}"

                    state["_last_action_reason"] = "schema_validation_failed"

                    return state

        self._snapshot(state, f"stage_{stage.id}_output")

        if artifact:

            await asyncio.to_thread(self._persist_files, artifact, state.get("output_dir", ""))

        if parsed.decision == AgentDecision.NEEDS_CLARIFICATION:

            state["phase"] = PipelinePhase.FAILED

            state["error"] = f"Stage {stage.id} needs clarification"

            state["_last_action_reason"] = "needs_clarification"

            state["_consecutive_llm_failures"] = state.get("_consecutive_llm_failures", 0) + 1

            return state

        # Track consecutive failures for degradation strategy

        if state.get("error"):

            state["_consecutive_llm_failures"] = state.get("_consecutive_llm_failures", 0) + 1

        else:

            state["_consecutive_llm_failures"] = 0

        if stage.retry_target_id:

            state = await self._retry_loop(stage, state)

        return state


    async def _evaluate_stage_health(self, stage: PipelineStageConfig, state: PipelineState) -> None:
        """Compute per-dimension health scores from stage output (heuristic, zero-LLM-cost).

        Writes to state[f"_health_report_{stage.id}"] in the format expected by
        get_health_report() in builder_project_service.py.
        """
        dims = getattr(stage, 'scoring_dimensions', None)
        if not dims:
            return

        artifact = state.get(stage.output_artifact)
        if artifact is None:
            return

        raw_output = ""
        if isinstance(artifact, dict):
            raw_output = str(artifact.get("raw_output", ""))
        else:
            raw_output = str(artifact)

        output_len = len(raw_output) if raw_output else 0

        # ── Heuristic scoring per dimension ──
        dimension_scores = []
        for dim in dims:
            dim_name = dim.get("name", "")
            dim_weight = dim.get("weight", 0.0)
            dim_threshold = dim.get("threshold", 7.0)
            dim_desc = dim.get("description", dim_name)
            score = 5.0  # default midpoint

            # Completeness / coverage: based on output size and structural element count
            if dim_name in ("completeness", "coverage", "execution_completeness"):
                score = min(10.0, 3.0 + (output_len / 1500) * 7.0)
                struct_count = raw_output.count('## ') + raw_output.count('|') / 4.0
                struct_count += raw_output.count('FR-') + raw_output.count('AC')
                score = min(10.0, score + struct_count * 0.3)

            # Clarity / configurability: output structure and organization
            elif dim_name in ("clarity", "configurability"):
                sections = raw_output.count('## ') + raw_output.count('### ')
                score = min(10.0, 2.0 + sections * 1.5)
                if '```' in raw_output:
                    score += 1.0
                score = min(10.0, score)

            # Modularity / correctness / feasibility / interactivity / data_binding
            elif dim_name in ("modularity", "correctness", "feasibility", "interactivity",
                              "data_binding"):
                files = raw_output.count('## FILE:') + raw_output.count('"file"')
                files += raw_output.count('"path"')
                components = raw_output.count('"name"') / 2.0
                components += raw_output.count('"component"')
                score = min(10.0, 3.0 + files * 1.0 + components * 0.8)

            # Testability / evaluation_accuracy: based on test results
            elif dim_name in ("testability", "evaluation_accuracy"):
                if isinstance(artifact, dict):
                    tr = artifact.get("test_results") or artifact
                    if isinstance(tr, dict) and tr.get("total", 0) > 0:
                        rate = tr.get("pass_rate", 0)
                        score = rate * 10.0
                    else:
                        ac_count = raw_output.count('AC') + raw_output.count('acceptance_criteria')
                        score = min(10.0, 3.0 + ac_count * 0.5)
                else:
                    ac_count = raw_output.count('AC') + raw_output.count('acceptance_criteria')
                    score = min(10.0, 3.0 + ac_count * 0.5)

            # Functionality / robustness: based on output quality signals
            elif dim_name in ("functionality", "robustness"):
                if isinstance(artifact, dict) and artifact.get("pass_rate") is not None:
                    score = (artifact.get("pass_rate") or 0) * 10.0
                else:
                    score = min(10.0, 3.0 + (output_len / 2000) * 7.0)

            # Default: output size proxy
            else:
                score = min(10.0, 3.0 + (output_len / 2000) * 7.0)

            dimension_scores.append({
                "name": dim_name,
                "display_name": dim_desc,
                "score": round(score, 1),
                "max_score": 10.0,
                "weight": dim_weight,
                "pass_threshold": dim_threshold,
                "issues_count": 0,
            })

        # Compute weighted overall score (0-100 scale)
        total_weight = sum(d["weight"] for d in dimension_scores) or 1.0
        weighted_sum = sum(d["score"] * d["weight"] for d in dimension_scores)
        overall = round(weighted_sum / total_weight * 10.0, 1)

        verdict = "passed" if overall >= 70 else "partial" if overall >= 40 else "failed"

        report = {
            "stage_id": stage.id,
            "agent_id": getattr(stage, 'agent_id', '') or stage.id,
            "dimensions": dimension_scores,
            "overall_score": overall,
            "verdict": verdict,
        }
        state[f"_health_report_{stage.id}"] = report
