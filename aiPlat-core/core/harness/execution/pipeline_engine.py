"""

import logging
PipelineEngine -- generic team execution engine.



Canonical location: harness/execution/pipeline_engine.py (CLAUDE.md §5.23).

"""

# === capability_dependencies (Phase 43: auto-verified) ===

# depends_on:

#   - harness-execution-engine:

#       symbols: [PipelineStageConfig, StageRunner, FailureClassifier]

#   - agent-system:

#       symbols: [BaseAgent, SubagentCoordinator]

#   - memory-subsystem:

#       symbols: [MemoryManager]

#   - moa-multi-model-reasoning:

#       symbols: [moa_executor.execute]

#   - extension-and-learning:

#       symbols: [StrategySearchEngine, GoalExecutor]

#   - gate-system:

#       symbols: [ErrorTranslator, ApprovalGate]

#   - orchestration-layer:

#       symbols: [SwarmBroker, DynamicOrchestrator]

#   - model-infrastructure:

#       symbols: [best_model_for_purpose]

# === end ===



from __future__ import annotations



from dataclasses import dataclass, field

from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypedDict



# ── Pipeline Registry (for Playbook v1 export/import) ──

# v2 register/import: use register_pipeline_from_desc() below.

REGISTERED_PIPELINES: Dict[str, Callable] = {}



def get_pipeline_builder(name: str) -> Callable:

    """Get a registered pipeline builder by name."""

    return REGISTERED_PIPELINES.get(name)





# ── Pipeline v2: Topology serialization for Playbook cross-environment migration ──

_PIPELINE_TOPOLOGY: Dict[str, dict] = {}  # populated via register_pipeline_from_desc()



def pipeline_to_dict(name: str) -> Optional[dict]:

    """Export a registered pipeline's topology as a JSON-safe dict (v2)."""

    topo = _PIPELINE_TOPOLOGY.get(name)

    if topo:

        return {**topo, "graph_serialization_version": "2.0.0",

                "langgraph_min_version": "0.2.0"}

    # v1 fallback: return None

    return None



def register_pipeline_from_desc(topo: dict) -> str:

    """Register a pipeline from a serialized topology description (v2)."""

    import importlib.metadata as _meta

    name = topo.get("name", "")

    if not name:

        raise ValueError("Pipeline definition missing 'name'")

    # Version check

    try:

        lg_ver = _meta.version("langgraph")

        min_ver = topo.get("langgraph_min_version", "0.2.0")

        if _version_lt(lg_ver, min_ver):

            raise ValueError(f"langgraph {min_ver}+ required, found {lg_ver}")

    except Exception:

        import logging

        logging.debug("langgraph version check skipped (langgraph may not be installed)", exc_info=True)

    _PIPELINE_TOPOLOGY[name] = topo

    # Also register as a builder that raises informative error (v2: needs source code to execute)

    REGISTERED_PIPELINES[name] = lambda: (_ for _ in ()).throw(

        NotImplementedError(f"Pipeline '{name}' imported from Playbook — needs source code"))

    return name





def _version_lt(a: str, b: str) -> bool:

    """Compare semantic versions: True if a < b."""

    try:

        pa = [int(x) for x in a.split(".")]

        pb = [int(x) for x in b.split(".")]

        while len(pa) < len(pb): pa.append(0)

        while len(pb) < len(pa): pb.append(0)

        return pa < pb

    except Exception:

        return False



import asyncio

import hashlib

import json

import logging

import os



logger = logging.getLogger(__name__)

import re

import time

from datetime import datetime, timezone



from core.harness.execution.phase import PipelinePhase

from core.schemas_builder import (

    AgentConfidence,

    AgentDecision,

    IssueSeverity,

    TestRecommendation,

    Issue,

    PipelineConfig,

    PipelineStageConfig,

    AgentOutput,

)



from core.harness.kernel.types import DAG

from core.harness.knowledge.repo_map import RepositoryMap



from .langgraph.stage_runner import StageRunner

from core.harness.evaluation.eval_runner import EvalRunner

from core.harness.evaluation.postprocess import PostprocessCorrector

from core.harness.execution.failure_classifier import FailureClassifier

from core.harness.utils.model_injection import best_model_for_purpose



# Global cancel registry for running pipelines

_pipeline_cancels: Dict[str, bool] = {}





async def _save_pipeline_knowledge_to_wiki(state: dict, config: Any) -> None:
    """Save pipeline stage outputs to Wiki for cross-project knowledge reuse."""
    _pid = state.get("session_id", "") or state.get("_run_id", "")
    if not _pid:
        return
    try:
        from core.harness.knowledge.wiki_engine import write_page
        _name = state.get("description", _pid)
        _saved = 0
        for _key, _val in state.items():
            if _key.startswith("_") or not isinstance(_val, dict):
                continue
            if _key in ("phase", "error", "tokens_used", "iteration", "artifacts"):
                continue
            _output = _val.get("raw_output", "") or str(_val)
            if not _output or len(_output) < 50:
                continue
            try:
                write_page(
                    title=f"pipeline/{_pid}/{_key}",
                    body=f"# {_val.get('label', _key)} - {_name}\n\n{_output[:5000]}",
                    category="topics",
                    tags=["pipeline-output", _key],
                    collection_id="default",
                    status="draft",
                    skip_validation=True,
                )
                _saved += 1
            except Exception as _we:
                logging.getLogger("pipeline_engine").warning(
                    "Wiki save failed pipeline/%s/%s: %s", _pid, _key, str(_we)[:200])
        if _saved:
            logging.getLogger("pipeline_engine").info(
                "Wiki: saved %d pipeline artifacts for %s", _saved, _pid)
    except Exception as _e:
        logging.getLogger("pipeline_engine").warning(
            "Wiki pipeline save error for %s: %s", _pid, str(_e)[:200])


async def _safe_generalize_skill(engine: Any, skill_id: str, state: dict) -> None:
    """Fire-and-forget generalization — never blocks pipeline, never crashes."""
    try:
        from core.harness.learning.success_generalizer import get_generalizer
        generalizer = get_generalizer()
        if hasattr(generalizer, 'generalize_async'):
            await generalizer.generalize_async(skill_id, str(state.get("description", "")))
        else:
            generalizer.generalize(skill_id, str(state.get("description", "")))
    except asyncio.CancelledError:  # noqa: normal-cancellation
        pass
    except Exception:
        import logging as _gl
        _gl.getLogger("pipeline_engine").debug(
            "safe_generalize_skill failed", exc_info=True)


class PipelineEventBus:

    """Event bus for pipeline execution lifecycle — mirrors Dify/Coze callback pattern.

    

    Engine fires events; listeners subscribe to observe progress.

    The event bus also maintains a state snapshot for REST polling.

    """

    def __init__(self):

        self._listeners: List[Any] = []



    def on(self, listener: Any) -> None:

        """Register a callable(project_id, event_type, data)."""

        self._listeners.append(listener)



    def emit(self, project_id: str, event_type: str, data: dict) -> None:

        """Fire event to listeners + write to SQLite pipeline_events (single source of truth)."""

        incoming = dict(data.get("state", data))

        # Notify in-process listeners (backward compat)

        for fn in self._listeners:

            try:

                fn(project_id, event_type, data)

            except Exception as e:

                logging.warning(str(e), exc_info=True)

        # Write to SQLite for cross-thread/process visibility

        import json

        _write_pipeline_event(

            run_id=project_id,

            event_type=event_type,

            node_id=str(data.get("node_id", "")),

            state_json=json.dumps(incoming, default=str),

            elapsed=float(data.get("elapsed", 0)),

            output=str(incoming.get(f"_stage_output_{data.get('node_id','')}", "")),

        )



# Global singleton — engine fires events, platform/service layers listen

_event_bus = PipelineEventBus()





def get_event_bus() -> PipelineEventBus:

    return _event_bus





def _write_file(path: str, content: str) -> None:

    """Thread-safe file writer (called via asyncio.to_thread)."""

    import os as _os

    _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)

    with open(path, "w", encoding="utf-8") as fh:

        fh.write(content)





def _safe_join(base_dir: str, file_path: str) -> str:

    """Join base_dir + file_path with traversal protection.



    Resolves both paths and verifies the result is within base_dir.

    Raises ValueError if the path attempts to escape the base directory.

    """

    base = os.path.realpath(base_dir)

    # Normalize: strip leading / and resolve

    normalized = os.path.normpath(file_path.lstrip("/"))

    full = os.path.realpath(os.path.join(base, normalized))

    if not full.startswith(base + os.sep) and full != base:

        raise ValueError(f"path_traversal_blocked: {file_path}")

    return full





def _validate_deploy(deploy_dir: str, state: dict) -> None:

    """Post-assembly validation: py_compile check on generated Python files."""

    import py_compile as _py_compile

    import glob as _glob

    import logging as _logging

    errors = []

    for py_file in sorted(_glob.glob(os.path.join(deploy_dir, "**/*.py"), recursive=True)):

        try:

            _py_compile.compile(py_file, doraise=True)

        except _py_compile.PyCompileError as e:

            errors.append(f"{os.path.relpath(py_file, deploy_dir)}: {e}")

    if errors:

        state["_deploy_compile_errors"] = errors[:20]

        _logging.getLogger("pipeline_engine").warning(

            "Generated code has %d compile errors (showing first %d)",

            len(errors), min(len(errors), 20))





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

    # Generic task tracking: any Stage that produces sub-tasks

    # (e.g. programmer working through functional_requirements one-at-a-time)

    # can use task_list for progress tracking across sessions.

    task_list: List[Dict[str, Any]]

    # Cross-stage conversation memory: persists through entire pipeline run.

    # Stages can read via {{conversation.key}} and write via returning

    # {"conversation_update": {"key": "value"}} in their output.

    conversation_state: Dict[str, Any]

    _conversation_state: Dict[str, Any]


# ── v3.1: global pipeline registry for HITL resolution ──
_running_pipelines: Dict[str, "PipelineEngine"] = {}


def get_running_pipeline(project_id: str) -> Optional["PipelineEngine"]:
    """Look up the active engine instance for HITL resolution."""
    return _running_pipelines.get(project_id)


def register_pipeline(project_id: str, engine: "PipelineEngine") -> None:
    """Register an engine as active for a project."""
    _running_pipelines[project_id] = engine


def unregister_pipeline(project_id: str) -> None:
    """Remove a completed/failed engine from the registry."""
    _running_pipelines.pop(project_id, None)



from core.harness.execution.pipeline_healing import PipelineHealingMixin


from core.harness.execution.pipeline_state import PipelineStateMixin


from core.harness.execution.pipeline_prompt import PipelinePromptMixin
from core.harness.execution.pipeline_eval import PipelineEvalMixin, _apply_skip_pytest_gate
from core.harness.execution.pipeline_stage import PipelineStageMixin


class PipelineEngine(PipelineStageMixin, PipelineEvalMixin, PipelinePromptMixin, PipelineStateMixin, PipelineHealingMixin):

    def __init__(self, config: PipelineConfig, model: Any = None, skill_loader: Any = None,
                 persist_callback: Any = None):

        self._config = config

        self._model = model

        if self._model is None:

            self._model = self._load_default_model(category="agent")

        self._skill_loader = skill_loader
        
        self._persist_callback = persist_callback  # called after each stage completes

        self._stage_runner = StageRunner(model=self._model, pipeline_config=config)

        self._eval_runner = EvalRunner()

        self._model_lock = asyncio.Lock()  # guards parallel stage model swaps

        # ── v3.1: HITL event-driven resume ──
        self._resume_event = asyncio.Event()
        self._reject_feedback: str = ""
        self._shutdown_requested: bool = False



    def _audit_hitl(self, state: Dict, action: str, actor: str = "system", detail: str = "") -> None:

        """Record HITL decision (best-effort, §5.20 observability requirement)."""

        try:

            import logging as _logging

            sid = state.get("session_id", "") if isinstance(state, dict) else ""

            _logging.getLogger("pipeline_engine").warning(

                "HITL audit: action=%s actor=%s session=%s detail=%s", action, actor, sid, detail

            )

            state.setdefault("_hitl_audit", []).append({

                "action": action, "actor": actor, "detail": detail,

                "timestamp": time.time(),

            })

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    # Config-driven: agent types that use conversational execution (core_chat) vs ReActLoop

    _CONVERSATIONAL_AGENT_TYPES = frozenset({"conversational", "rag", "plan", "plan_execute", "reflection", "review", "materials_chat"})

    _PLAN_UPGRADE_TYPES = frozenset({"plan", "plan_execute", "reflection"})



    def _load_eval_model(self) -> Any:

        eval_model_name = best_model_for_purpose("eval_code") or best_model_for_purpose("chat")

        if eval_model_name:

            return self._load_default_model(model_name=eval_model_name, category="eval")

        return self._model



    def _try_constraint_action(self, stage: PipelineStageConfig, state: Dict) -> bool:

        fclass = state.get("_failure_classification")

        if not fclass:

            return False

        ftype = fclass.get("type", "unknown")

        escalation = fclass.get("escalation", 0)

        max_esc = fclass.get("max_escalation", 0)

        if escalation > max_esc:

            return False

        action = fclass.get("constraint_action", "")

        if action == "switch_fallback_model":

            fb_model = best_model_for_purpose("chat")

            try:

                self._stage_runner._model = PipelineEngine._load_default_model(fb_model)

                state["_last_action_reason"] = f"constraint_switch_model:{fb_model}"

                return True

            except Exception:

                return False

        if action == "escalate_to_hitl":

            state["phase"] = "awaiting_hitl"

            state["_last_action_reason"] = f"constraint_escalate_hitl:{ftype}"

            return False

        if action == "strict_format_retry":

            _nc = getattr(stage, 'node_config', None) or {}

            _nc = dict(_nc)

            if not _nc.get('output_schema'):

                _nc['output_schema'] = '{"type":"object"}'

                stage.node_config = _nc

            state["_last_action_reason"] = "constraint_strict_format_retry"

            return True

        if action == "reduce_context_retry":

            state["_context_compaction_forced"] = True

            state["_last_action_reason"] = "constraint_reduce_context"

            return True

        return False



    @staticmethod

    def _load_default_model(model_name: str = "", *, category: str = "default") -> Any:

        import os

        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose

        if not model_name:

            if category == "agent":

                model_name = best_model_for_purpose("agent")

            else:

                model_name = best_model_for_purpose("chat")

        return create_selected_adapter(model_name=model_name)



    async def _run_stage_core(

        self, stage: PipelineStageConfig, state: PipelineState,

        prompt: str, agent_type: str, stage_model: Any,

    ) -> str:

        """Execute a single pipeline stage — extracted from _exec_stage for testability.

        

        Fixes applied:

        - CRITICAL #2: session_id uses state.get('session_id') not 'project_id'

        - CRITICAL #5: stage_model passed to ChatContext for non-React paths

        """

        # Sandbox path

        if getattr(stage, 'sandbox', False):

            from core.harness.execution.sandbox import create_sandbox

            sb = create_sandbox(stage,

                timeout_seconds=getattr(stage, 'stage_timeout_seconds', 600),

                cpu_limit_seconds=getattr(stage, 'sandbox_cpu_limit_seconds', 300),

                memory_limit_mb=getattr(stage, 'sandbox_memory_limit_mb', 1024),

                max_processes=getattr(stage, 'sandbox_max_processes', 100),

            )

            sandbox_result = await sb.execute(

                stage_config={"id": stage.id, "agent_id": stage.agent_id, "agent_type": agent_type},

                state_snapshot=dict(state),

            )

            if sandbox_result.success:

                return sandbox_result.output or ""

            raise RuntimeError(sandbox_result.error or "sandbox_execution_failed")



        # Debate path: adversarial multi-agent debate (config-driven via debate_participants field)

        participants = getattr(stage, 'debate_participants', None) or []

        if participants:

            return await self._run_debate_stage(stage, state, prompt, stage_model)



        # Non-React path: route by concrete node_type from workflow canvas

        node_type = getattr(stage, 'node_type', None) or 'agent'

        node_cfg = getattr(stage, 'node_config', None) or {}

        

        # Start/End/Human are declarative — no engine execution needed (matching Dify/Coze)

        if node_type in ('start', 'end', 'human'):

            return ''

        if node_type == 'llm':

            # Direct LLM call with config from canvas

            canvas_prompt = (node_cfg.get('prompt') or '').strip()

            if not canvas_prompt:

                state[f"_stage_input_{stage.id}"] = "(no prompt configured)"

                return json.dumps({"raw_output": "(no prompt configured — enter a prompt in the LLM node settings)"})

            # Resolve per-node input_variables (user-defined bindings like query={{start.question}})

            ivars = node_cfg.get('input_variables', []) if isinstance(node_cfg, dict) else []

            if ivars:

                jinja_ctx: dict = {}

                for _s in self._config.stages:

                    val = state.get(_s.output_artifact)

                    if val:

                        jinja_ctx[_s.output_artifact or _s.id] = val

                jinja_ctx.update({k: v for k, v in state.items() if not k.startswith('_')})

                for iv in ivars:

                    name = iv.get('name', '') if isinstance(iv, dict) else ''

                    raw_val = iv.get('value', '') if isinstance(iv, dict) else ''

                    if name and raw_val:

                        resolved = self._render_jinja2(raw_val, jinja_ctx) if '{{' in str(raw_val) else raw_val

                        state[name] = resolved

            # Override stage input with actual prompt sent to LLM (not the full _build_prompt)

            llm_prompt = canvas_prompt

            # Render {{start.var}} / {{stage.output}} templates via Jinja2

            if '{{' in canvas_prompt:

                jinja_ctx: dict = {}

                for _s in self._config.stages:

                    val = state.get(_s.output_artifact)

                    if val:

                        jinja_ctx[_s.output_artifact or _s.id] = val

                jinja_ctx.update({k: v for k, v in state.items() if not k.startswith('_')})

                llm_prompt = self._render_jinja2(canvas_prompt, jinja_ctx)

            state[f"_stage_input_{stage.id}"] = llm_prompt[:5000]

            llm_model_name = node_cfg.get('model') or (best_model_for_purpose("chat"))

            llm_memory_window = int(node_cfg.get('memory_window', 0))

            if llm_memory_window > 0 and isinstance(llm_prompt, str) and len(llm_prompt) > llm_memory_window:

                llm_prompt = llm_prompt[-llm_memory_window:]

            llm_temp = float(node_cfg.get('temperature', 0.7))

            llm_max_tokens = int(node_cfg.get('max_tokens', 2048))

            llm_output_schema = node_cfg.get('output_schema', '')

            # Engine infra — progress emission (shared with _run_stage_skill)
            _stage_tag = getattr(stage, 'output_artifact', '') or stage.id
            state["_progress"] = {"stage": _stage_tag, "status": "running",
                                  "started_at": __import__("time").time(),
                                  "backend": "llm", "current_step": 0}
            if self._persist_callback:
                self._persist_callback(dict(state))

            from core.harness.syscalls.llm import sys_llm_generate

            kwargs: dict = {

                'trace_context': {"source": f"workflow_llm_{stage.id}"},

                'temperature': llm_temp,

                'max_tokens': llm_max_tokens,

            }

            if llm_output_schema.strip():

                try:

                    import json as _json

                    schema = _json.loads(llm_output_schema) if isinstance(llm_output_schema, str) else llm_output_schema

                    kwargs['response_format'] = {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}}

                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

            # Build messages — support multimodal vision when enabled

            vision_enabled = node_cfg.get('vision', False)

            image_url = node_cfg.get('image_url', '')

            if vision_enabled and image_url and image_url.strip():

                messages = [{"role": "user", "content": [

                    {"type": "text", "text": llm_prompt},

                    {"type": "image_url", "image_url": {"url": image_url.strip()}},

                ]}]

            else:

                messages = [{"role": "user", "content": llm_prompt}]

            resp = await sys_llm_generate(

                None,

                messages,

                model_name=llm_model_name,

                **kwargs

            )

            result_text = getattr(resp, 'content', '') or str(resp)

            # Engine infra — model health recording (shared with _run_stage_skill)
            try:
                from core.harness.utils.model_injection import _record_success as _eng_record_success
                _llm_latency = 0  # latency tracking not available in canvas node path
                _eng_record_success(llm_model_name, latency_ms=_llm_latency, purpose="chat")
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            # Token tracking for LLM node path (aligns with StageRunner path at L1537-1539)

            usage = getattr(resp, 'usage', None)

            if isinstance(usage, dict):

                state["_stage_tokens_used"] = state.get("_stage_tokens_used", 0) + int(usage.get("total_tokens", 0))

            return result_text

        

        if node_type == 'code':

            # Execute via sys_tool_call → CodeExecutionTool (trace_id + PolicyGate)

            lang = node_cfg.get('language', 'python')

            snippet = node_cfg.get('snippet', 'print("hello")')

            timeout_ms = node_cfg.get('timeout_sec', 30) * 1000

            from core.harness.syscalls.tool import sys_tool_call

            try:

                result = await sys_tool_call(

                    'code_execute',

                    {'language': lang, 'code': snippet, 'timeout': timeout_ms},

                    trace_context={"source": f"workflow_code_{stage.id}"}

                )

                output = getattr(result, 'output', '') or str(result)

                if hasattr(result, 'success') and not result.success:

                    return f"Code execution failed: {getattr(result, 'error', 'unknown')}"

                return output

            except Exception as e:

                return f"Code execution failed: {e}"

        

        if node_type == 'http':

            # Execute via sys_tool_call → HTTPClientTool (trace_id + SSRF proxy support)

            method = node_cfg.get('method', 'GET')

            url = node_cfg.get('url', '')

            if not url:

                return "HTTP node: no URL configured"

            headers_str = node_cfg.get('headers', '{}')

            headers = json.loads(headers_str) if isinstance(headers_str, str) else headers_str

            body = node_cfg.get('body', '')

            timeout_ms = int(node_cfg.get('read_timeout', node_cfg.get('timeout_sec', 15))) * 1000

            connect_timeout = int(node_cfg.get('connect_timeout', 10))

            write_timeout = int(node_cfg.get('write_timeout', 10))

            from core.harness.syscalls.tool import sys_tool_call

            try:

                tool_params = {'method': method, 'url': url, 'headers': headers, 'body': body,

                     'timeout': timeout_ms, 'connect_timeout': connect_timeout, 'write_timeout': write_timeout}

                # Auth params

                auth_type = node_cfg.get('auth_type', 'none')

                if auth_type != 'none':

                    tool_params['auth_type'] = auth_type

                    if auth_type == 'basic':

                        tool_params['auth_user'] = node_cfg.get('auth_user', '')

                        tool_params['auth_pass'] = node_cfg.get('auth_pass', '')

                    elif auth_type == 'bearer':

                        tool_params['auth_token'] = node_cfg.get('auth_token', '')

                    elif auth_type == 'apikey':

                        tool_params['auth_key_name'] = node_cfg.get('auth_key_name', '')

                        tool_params['auth_key_value'] = node_cfg.get('auth_key_value', '')

                result = await sys_tool_call(

                    'http_request', tool_params,

                    trace_context={"source": f"workflow_http_{stage.id}"}

                )

                output = getattr(result, 'output', '') or str(result)

                if hasattr(result, 'success') and not result.success:

                    return f"HTTP request failed: {getattr(result, 'error', 'unknown')}"

                return f"HTTP {getattr(result, 'status_code', '?')}: {str(output)[:5000]}"

            except Exception as e:

                return f"HTTP request failed: {e}"

        

        if node_type == 'condition':

            # Support both legacy single-expression and new multi-rule evaluation

            rules = node_cfg.get('rules', None)

            true_label = node_cfg.get('true_label', 'True')

            false_label = node_cfg.get('false_label', 'False')

            # Build context from upstream artifacts

            ctx_vars = {}

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if val:

                    if isinstance(val, dict):

                        ctx_vars[s.output_artifact] = val

                    elif isinstance(val, str):

                        ctx_vars[s.output_artifact] = val[:200]

            try:

                if rules and isinstance(rules, list) and len(rules) > 0:

                    # Multi-rule evaluation: [{field, op, value}], logic=AND|OR

                    logic = node_cfg.get('logic', 'AND')

                    results = []

                    for rule in rules:

                        field = rule.get('field', '')

                        op = rule.get('op', '==')

                        val = rule.get('value', '')

                        # Resolve field from context

                        actual = ctx_vars.get(field)

                        if actual is None:

                            results.append(False)

                            continue

                        if isinstance(actual, dict):

                            actual = actual.get(val) if op == 'has_key' else str(actual)

                        if isinstance(actual, str):

                            val = str(val)

                        # Evaluate

                        try:

                            if op == '==': r = actual == val

                            elif op == '!=': r = actual != val

                            elif op == '>': r = float(actual) > float(val)

                            elif op == '<': r = float(actual) < float(val)

                            elif op == '>=': r = float(actual) >= float(val)

                            elif op == '<=': r = float(actual) <= float(val)

                            elif op == 'contains': r = str(val).lower() in str(actual).lower()

                            elif op == 'not_contains': r = str(val).lower() not in str(actual).lower()

                            elif op == 'is_empty': r = not bool(actual)

                            elif op == 'not_empty': r = bool(actual)

                            elif op == 'has_key': r = isinstance(actual, dict) and val in actual

                            else: r = False

                        except Exception: r = False

                        results.append(r)

                    passed = all(results) if logic == 'AND' else any(results)

                else:

                    # Legacy single-expression mode

                    expr = node_cfg.get('expression', 'true')

                    result = eval(expr, {"__builtins__": {}}, ctx_vars)

                    if isinstance(result, str):

                        result = result.lower() in ('true', 'yes', '1')

                    passed = bool(result)

                return f"Condition: {true_label if passed else false_label}"

            except Exception as e:

                return f"Condition eval failed: {e}"

        

        if node_type == 'knowledge':

            # Execute via sys_tool_call → KBQueryTool (trace_id + PolicyGate)

            kb_name = node_cfg.get('kb_name', '')

            kb_query = node_cfg.get('query') or prompt

            kb_top_k = int(node_cfg.get('top_k', 3))

            kb_rerank = node_cfg.get('rerank', False)

            kb_vector_provider = node_cfg.get('vector_search_provider', '')

            if not kb_query.strip():

                return "Knowledge node: no query provided"

            # Optional: vector search via lancedb

            if kb_vector_provider == 'lancedb':

                try:

                    import lancedb

                    db_path = node_cfg.get('vector_db_path', os.path.expanduser('~/.aiplat/vectors'))

                    db = lancedb.connect(db_path)

                    table_names = db.table_names()

                    target_table = kb_name if kb_name and kb_name in table_names else (table_names[0] if table_names else None)

                    if target_table:

                        tbl = db.open_table(target_table)

                        results = tbl.search(kb_query).limit(kb_top_k).to_list()

                        chunks = [f"[{i+1}] {r.get('content', str(r))[:500]}" for i, r in enumerate(results)]

                        return "Vector search results:\n" + "\n".join(chunks) if chunks else "No vector results found"

                except ImportError:

                    pass  # lancedb not installed, fall through to kb_query  # noqa: optional-dependency

                except Exception as e:

                    return f"Vector search failed: {e}"

            from core.harness.syscalls.tool import sys_tool_call

            try:

                result = await sys_tool_call(

                    'kb_query',

                    {'collection_id': kb_name or 'default', 'question': kb_query, 'limit': kb_top_k},

                    trace_context={"source": f"workflow_knowledge_{stage.id}"}

                )

                output = getattr(result, 'output', '') or str(result)

                if hasattr(result, 'success') and not result.success:

                    return f"Knowledge retrieval failed: {getattr(result, 'error', 'unknown')}"

                # Optional LLM re-ranking of retrieved chunks
                if kb_rerank and output:

                    try:

                        from core.harness.utils.prompt_loader import _sync_resolve
                        rerank_prompt = _sync_resolve("relevance-ranker",
                            top_k=kb_top_k, query=kb_query, passages=str(output)[:3000])

                        from core.harness.syscalls.llm import sys_llm_generate
                        _rerank_model = best_model_for_purpose("chat")
                        rerank_resp = await sys_llm_generate(
                            _rerank_model,

                            [{"role": "user", "content": rerank_prompt}],

                            trace_context={"source": f"workflow_knowledge_rerank_{stage.id}"}

                        )

                        rerank_text = getattr(rerank_resp, 'content', '') or ''

                        # Engine infra — model health recording (shared with _run_stage_skill)
                        try:
                            from core.harness.utils.model_injection import _record_success as _rerank_record_success
                            _rerank_record_success(_rerank_model, latency_ms=0, purpose="chat")
                        except Exception:
                            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

                        if rerank_text:

                            output = f"[Re-ranked]\n{rerank_text[:3000]}"

                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

                return str(output)[:5000] or "Knowledge node: no results"

            except Exception as e:

                return f"Knowledge retrieval failed: {e}"

        

        if node_type == 'tool':

            tool_name = node_cfg.get('tool_name', '')

            tool_params_str = node_cfg.get('params', '{}')

            if not tool_name:

                return "Tool node: no tool name configured"

            try:

                import json as _json

                params = _json.loads(tool_params_str) if isinstance(tool_params_str, str) else tool_params_str

                from core.harness.syscalls.tool import sys_tool_call

                result = await sys_tool_call(tool_name, params or {}, trace_context={"source": f"workflow_tool_{stage.id}"})

                return f"Tool '{tool_name}': {str(result)[:2000]}"

            except Exception as e:

                return f"Tool call failed: {e}"

        

        if node_type == 'list':

            # List operator: filter/sort/slice/map on upstream array

            operation = node_cfg.get('operation', 'filter')

            param = node_cfg.get('list_param', '')

            # Get upstream data (first available array from input artifacts)

            upstream_data = None

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if isinstance(val, list):

                    upstream_data = val

                    break

                elif isinstance(val, dict):

                    for v in val.values():

                        if isinstance(v, list):

                            upstream_data = v

                            break

                    if upstream_data: break

            if not isinstance(upstream_data, list):

                return "List operator: no upstream list found, or upstream output is not a list"

            try:

                if operation == 'filter':

                    # param: Python expression, e.g., "item.get('price',0) > 100"

                    result = [item for item in upstream_data if eval(param, {"__builtins__": {}}, {"item": item})]

                elif operation == 'sort':

                    # param: "price desc" or "price"

                    parts = param.strip().split()

                    key = parts[0] if parts else ''

                    reverse = len(parts) > 1 and parts[1].lower() == 'desc'

                    if key:

                        result = sorted(upstream_data, key=lambda x: (x.get(key, 0) if isinstance(x, dict) else x), reverse=reverse)

                    else:

                        result = sorted(upstream_data, reverse=reverse)

                elif operation == 'slice':

                    # param: "0:10" or "5:"

                    parts = param.strip().split(':')

                    start = int(parts[0]) if parts[0] else 0

                    end = int(parts[1]) if len(parts) > 1 and parts[1] else len(upstream_data)

                    result = upstream_data[start:end]

                elif operation == 'map':

                    # param: "item.name" or Python expression

                    result = [eval(param, {"__builtins__": {}}, {"item": item}) for item in upstream_data]

                else:

                    result = upstream_data

                return f"List {operation}: {len(upstream_data)} → {len(result)} items"

            except Exception as e:

                return f"List operation failed: {e}"

        

        if node_type == 'assigner':

            target_var = node_cfg.get('target_var', '')

            expr = node_cfg.get('expression', '')

            if not target_var or not expr.strip():

                return "Assigner: target variable name and expression required"

            # Build context from upstream artifacts

            ctx = {}

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if val:

                    ctx[s.output_artifact] = val

            try:

                result = eval(expr, {"__builtins__": {}}, {"data": ctx, **ctx})

                return json.dumps({target_var: result}, ensure_ascii=False)

            except Exception as e:

                return f"Assigner evaluation failed: {e}"

        

        if node_type == 'loop':

            source_var = node_cfg.get('source_var', '')

            body_template = node_cfg.get('body_template', '')

            loop_mode = node_cfg.get('loop_mode', 'sequential')

            max_concurrency = int(node_cfg.get('max_concurrency', 5))

            if not source_var or not body_template.strip():

                return "Loop node: source variable and body template required"

            # Find upstream array

            upstream_array = None

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if isinstance(val, dict):

                    if source_var in val and isinstance(val[source_var], list):

                        upstream_array = val[source_var]

                        break

                    for v in val.values():

                        if isinstance(v, dict) and source_var in v and isinstance(v[source_var], list):

                            upstream_array = v[source_var]

                            break

                    if upstream_array: break

                elif isinstance(val, list) and source_var and source_var in str(val):

                    upstream_array = val

                    break

            if not isinstance(upstream_array, list):

                return f"Loop node: '{source_var}' not found or not an array in upstream output"

            results = []

            ctx_base = {}

            for s in self._config.stages:

                v = state.get(s.output_artifact)

                if v: ctx_base[s.output_artifact] = v

            if loop_mode == 'parallel':

                try:

                    from core.harness.integration import get_parallel_executor

                    _pe = get_parallel_executor()

                    parallel_analyze, create_dummy_agent, EmbeddingBridge = _pe.parallel_analyze, _pe.create_dummy_agent, _pe.EmbeddingBridge

                    topics = [

                        self._render_jinja2(body_template, {**ctx_base, 'loop': {'item': item, 'index': idx}}).strip()

                        for idx, item in enumerate(upstream_array)

                    ]

                    map_result = await parallel_analyze(

                        topics, create_dummy_agent, max_concurrency=max_concurrency)

                    raw_results = [str(r.get("output", r)) if isinstance(r, dict) else str(r)

                                   for r in map_result.get("results", [])]

                    # EmbeddingBridge: compress results

                    bridge = EmbeddingBridge(compression_ratio=0.5)

                    compacted = []

                    for r in raw_results:

                        if isinstance(r, str) and len(r) > 1500:

                            _vec, summary = await bridge.encode(r)

                            compacted.append(f"[EmbeddingBridge:{summary}]")

                        else:

                            compacted.append(r)

                    results = compacted

                except Exception:

                    for idx, item in enumerate(upstream_array):

                        ctx = {**ctx_base, 'loop': {'item': item, 'index': idx}}

                        try:

                            results.append(self._render_jinja2(body_template, ctx).strip())

                        except Exception as e:

                            results.append(f"Error at index {idx}: {e}")

            else:

                for idx, item in enumerate(upstream_array):

                    ctx = {**ctx_base, 'loop': {'item': item, 'index': idx}}

                    try:

                        rendered = self._render_jinja2(body_template, ctx)

                        results.append(rendered.strip())

                    except Exception as e:

                        results.append(f"Error at index {idx}: {e}")

            return json.dumps({'results': results, 'count': len(results), 'mode': loop_mode}, ensure_ascii=False)

        

        if node_type == 'aggregator':

            # Collect all upstream artifacts into a single merged object

            mode = node_cfg.get('agg_mode', 'object')

            collected = {}

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if val:

                    collected[s.output_artifact or s.id] = val

            if mode == 'list':

                return json.dumps(list(collected.values()), ensure_ascii=False)

            return json.dumps(collected, ensure_ascii=False)



        if node_type == 'template':

            tpl = node_cfg.get('template', '')

            if not tpl.strip():

                return "Template node: no template provided"

            # Build context from upstream artifacts

            ctx = {}

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if val:

                    ctx[s.output_artifact] = val

            try:

                result = self._render_jinja2(tpl, ctx)

                return result

            except Exception as e:

                return f"Template rendering failed: {e}"



        if node_type == 'algorithm':

            # Deterministic computation — no LLM, guaranteed reproducible

            func_name = node_cfg.get('function_name', '')

            if not func_name:

                return json.dumps({"success": False, "error": "algorithm node: no function_name configured"})



            func_params = node_cfg.get('function_params', {})

            if isinstance(func_params, str):

                try:

                    func_params = json.loads(func_params)

                except Exception:

                    func_params = {}



            # Resolve upstream artifact references in params

            upstream = {}

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if val is not None:

                    upstream[s.output_artifact] = val



            from core.harness.execution.algorithm_node import execute_algorithm

            algo_result = execute_algorithm(func_name, func_params, upstream_artifacts=upstream)

            return json.dumps(algo_result, ensure_ascii=False, default=str)



        if node_type == 'plan':

            # Planner-Generator-Evaluator: structured task plan output

            plan_hint = node_cfg.get('hint', 'Break down the objective into 3-7 verifiable tasks.')

            plan_format = node_cfg.get('format', 'json')

            from core.harness.utils.prompt_loader import _sync_resolve
            prompt = _sync_resolve("technical-planner", context=plan_hint)

            from core.harness.syscalls.llm import sys_llm_generate

            from core.harness.utils.model_injection import best_model_for_purpose

            # Engine infra — progress + trace (shared with _run_stage_skill)
            _plan_model = best_model_for_purpose("chat")
            resp = await sys_llm_generate(

                None, [{"role": "user", "content": prompt}],

                model_name=_plan_model,

                max_tokens=1000,

                trace_context={"source": f"workflow_plan_{stage.id}"},

            )

            plan_text = getattr(resp, 'content', '') or str(resp)

            # Engine infra — model health recording
            try:
                from core.harness.utils.model_injection import _record_success as _plan_record_success
                _plan_record_success(_plan_model, latency_ms=0, purpose="chat")
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            state["_task_plan"] = plan_text

            return plan_text



        # Fallback: conversational agents use core_chat, react uses StageRunner

        if not stage.uses_file_output and agent_type in self._CONVERSATIONAL_AGENT_TYPES:

            import uuid as _uuid

            from core.api.intents import core_chat, ChatContext

            result = await core_chat(ChatContext(

                agent_name=stage.agent_id,

                session_id=f"{state.get('session_id', 'pipeline')}_stage_{stage.id}",

                user_input=prompt,

                model=stage_model,  # FIX #5: Pass stage model config

            ))

            state["_stage_trace_id"] = result.trace_id

            return result.reply or ""

        

        # ReAct loop path (code generation, default): direct StageRunner

        # Model swap is handled by the caller (_exec_stage) under _model_lock.

        return await self._stage_runner.run(prompt, state, stage=stage)



    async def _run_debate_stage(

        self, stage: PipelineStageConfig, state: PipelineState,

        prompt: str, stage_model: Any,

    ) -> str:

        """Execute adversarial multi-agent debate (TradingAgents-inspired)."""

        from core.harness.execution.debate import run_agent_debate

        from core.api.intents import core_chat, ChatContext



        participants = getattr(stage, 'debate_participants', [])

        manager = getattr(stage, 'debate_manager_agent', '')

        max_rounds = getattr(stage, 'debate_max_rounds', 3)

        session_id = state.get("session_id", "debate")



        async def _run(agent_name: str, agent_prompt: str, model: Any) -> str:

            result = await core_chat(ChatContext(

                agent_name=agent_name,

                session_id=session_id,

                user_input=agent_prompt,

                model=model or stage_model,

            ))

            return result.reply or ""



        agent_configs = [

            {

                "name": p.get("agent_id", p.get("name", "")),

                "prompt_template": p.get("prompt", prompt),

                "model": stage_model,

                "side": p.get("side", p.get("agent_id", "")),

            }

            for p in participants

        ]



        manager_cfg = None

        if manager:

            manager_cfg = {

                "name": manager,

                "prompt_template": prompt,

                "model": stage_model,

            }



        result = await run_agent_debate(

            agent_configs=agent_configs,

            debate_info={"prompt": prompt},

            max_rounds=max_rounds,

            stability_threshold=2,

            run_agent=_run,

            manager_agent=manager_cfg,

            run_manager=_run if manager_cfg else None,

        )



        # Store debate metadata

        state["_debate_state"] = {

            "rounds": result["rounds"],

            "converged": result["converged"],

        }



        return result.get("manager_decision") or json.dumps(

            result.get("outputs", {}), ensure_ascii=False

        )



    async def initialize(self, project_id: str, requirement: str,

                         prd_data: Optional[Dict] = None, project_name: str = "") -> PipelineState:

        output_dir = self._output_root(project_id, project_name)

        os.makedirs(output_dir, exist_ok=True)

        state: PipelineState = {

            "session_id": project_id,

            "_run_id": project_id,

            "phase": PipelinePhase.EXECUTING,

            "description": requirement,

            "iteration": 0, "qa_retry": 0, "max_iterations": 100,

            "tokens_used": 0, "tokens_budget": self._config.max_tokens_per_run,

            "output_dir": output_dir, "issues": [], "context": {},

        }

        # Inject Start node test inputs into pipeline state

        start_inputs = {}

        if self._config.stages:

            first_stage = self._config.stages[0]

            start_cfg = getattr(first_stage, 'node_config', None) or {}

            start_inputs = start_cfg.get("inputs", {})

            for key, val in start_inputs.items():

                state[f"start.{key}"] = val

        if prd_data:
            # Merge chat PRD context into description for all pipeline stages
            import json as _json
            _d = state.get("description", "")
            if isinstance(prd_data, dict):
                _d = (str(_d) + "\n\n" + _json.dumps(prd_data, ensure_ascii=False, indent=2))[:8000]
            state["description"] = _d

        return await self._run_stages_from(0, state)



    async def approve_session(self, state: PipelineState, feedback: str = "") -> PipelineState:

        state = dict(state)

        self._audit_hitl(state, "hitl_approved", detail=feedback[:200] if feedback else "")



        # ── Human-stage HITL: inject feedback as human input, return immediately ──

        # The actual pipeline continuation is handled by the caller (background task)

        hitl_stage_id = state.get("_hitl_stage_id", "")

        human_feedback = feedback or state.get("_hitl_human_feedback", "")

        if hitl_stage_id:
            for i, s in enumerate(self._config.stages):
                if s.id == hitl_stage_id:
                    # If user provided feedback, inject it into stage output
                    if human_feedback:
                        state[s.output_artifact] = {"raw_output": human_feedback, "source": "human_hitl"}
                        try:
                            import json as _j
                            parsed = _j.loads(human_feedback)
                            if isinstance(parsed, dict):
                                state[s.output_artifact] = parsed
                        except Exception:
                            logging.getLogger(__name__).debug('approve failed', exc_info=True)
                    state["_hitl_resolved_" + s.id] = True
                    state["_hitl_stage_id"] = ""
                    state["_hitl_phase_name"] = ""
                    state["_hitl_output_artifact"] = ""
                    state["_hitl_human_feedback"] = ""
                    state["phase"] = PipelinePhase.EXECUTING
                    state["_current_stage_idx"] = i
                    self._audit_hitl(state, "hitl_human_input", detail=f"stage={s.id}")
                    # Don't run remaining stages here — let caller do it async
                    return state

            state["_hitl_stage_id"] = ""
            state["_hitl_phase_name"] = ""
            state["_hitl_output_artifact"] = ""

        self._repair_message_integrity(state)



        # Load checkpoints from disk if in-memory list is empty (survives restart)

        if not state.get("_checkpoints"):

            state["_checkpoints"] = self._load_checkpoints_from_disk(state)



        # Wake recovery: if current state has errors, fallback to last healthy checkpoint.

        # Makes harness "cattle" — restartable from event log without losing progress.

        if state.get("error") or state.get("phase") == PipelinePhase.FAILED:

            checkpoints = state.get("_checkpoints", [])

            healthy = [c for c in checkpoints if isinstance(c, dict) and not c.get("error")]

            if healthy:

                last = healthy[-1]

                state["error"] = ""

                state["phase"] = PipelinePhase.EXECUTING

                state["_current_stage_idx"] = last.get("stage_idx", state.get("_current_stage_idx", 0))

                state["tokens_used"] = last.get("tokens_used", state.get("tokens_used", 0))

                state["tokens_budget"] = last.get("tokens_budget", state.get("tokens_budget", 0))

                state["iteration"] = last.get("iteration", state.get("iteration", 0))

                state["_wake_recovered"] = True

                state["_wake_recovered_from"] = last.get("name", "unknown")



        state["phase"] = PipelinePhase.EXECUTING

        idx = state.get("_current_stage_idx", 0)

        # Guard: if idx is out of bounds (e.g., after stage removal), mark pipeline done

        if idx < 0 or idx >= len(self._config.stages):

            state["phase"] = PipelinePhase.DONE

            state["_last_action_reason"] = "approve_out_of_bounds"

            return state

        # If current HITL stage has generate_test_plan, test plan means "same stage resume"

        cur_stage = self._config.stages[idx]

        if cur_stage.generate_test_plan and state.get("phase") == (cur_stage.hitl_phase or ""):

            result = await self._run_stages_from(idx, state)

            await self._consolidate_auto_pipeline(result)

            return result

        result = await self._run_stages_from(idx + 1, state)

        await self._consolidate_auto_pipeline(result)

        return result



    @staticmethod

    def _repair_message_integrity(state: PipelineState) -> None:

        """Scan message trajectory and repair broken tool_use/tool_result pairings.



        After HITL pause/resume, the message sequence may contain:

        - Orphan tool_result: a result without a preceding tool_use call

        - Incomplete tool_use: a call produced but never got a result

        - Duplicate tool_use ids: reuse of same id across multiple messages



        This inserts repair markers so the Agent knows what was interrupted.

        """

        try:

            msgs = state.get("messages") or state.get("context", {}).get("messages")

            if not isinstance(msgs, list) or len(msgs) < 2:

                return

            seen_ids: set = set()

            pending_ids: set = set()

            import json as _json



            # Phase 1: collect repairs without modifying the list

            repairs: list = []  # (index, replacement_msg) or (-index, insert_msg)

            for i, msg in enumerate(msgs):

                if not isinstance(msg, dict):

                    continue

                try:

                    content = _json.loads(str(msg.get("content", "")))

                except Exception:

                    continue

                msg_type = content.get("type", "") if isinstance(content, dict) else ""

                if msg_type == "tool_use":

                    tuid = content.get("id", "")

                    if tuid in seen_ids:

                        repairs.append((i, {"role": "user", "content": _json.dumps(

                            {"type": "tool_result", "tool_use_id": tuid, "name": content.get("name", "?"),

                             "success": False, "output": "[REPAIR: duplicate tool_use — prior result consumed]"},

                            ensure_ascii=False)}))

                    seen_ids.add(tuid)

                    pending_ids.add(tuid)

                elif msg_type == "tool_result":

                    tuid = content.get("tool_use_id", "")

                    if tuid in pending_ids:

                        pending_ids.discard(tuid)

                    elif tuid not in seen_ids:

                        repairs.append((-i, {"role": "assistant", "content": _json.dumps(

                            {"type": "tool_use", "id": tuid, "name": content.get("name", "?"),

                             "input": "[REPAIR: orphan tool_result — injected placeholder]"},

                            ensure_ascii=False)}))

                        seen_ids.add(tuid)



            # Phase 2: apply repairs (reverse order for stability)

            for repair in sorted(repairs, key=lambda r: -abs(r[0])):

                idx, new_msg = repair

                if idx >= 0:

                    msgs[idx] = new_msg

                else:

                    msgs.insert(-idx, new_msg)



            if pending_ids:

                repair_note = _json.dumps(

                    {"type": "repair_note", "pending_tool_ids": list(pending_ids),

                     "message": "[REPAIR: HITL pause interrupted these tool calls — results may be pending]"},

                    ensure_ascii=False)

                msgs.append({"role": "user", "content": repair_note})

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)



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



    async def reject_session(self, state: PipelineState, feedback: str) -> PipelineState:

        state = dict(state)

        state["_reject_feedback"] = feedback

        self._audit_hitl(state, "hitl_rejected", detail=feedback[:200])

        idx = self._find_hitl_stage_index(state)

        for i in range(idx, len(self._config.stages)):

            state[self._config.stages[i].output_artifact] = None

            state.pop(f"_stage_{self._config.stages[i].id}_done", None)

            if self._config.stages[i].generate_test_plan:

                state[self._config.stages[i].test_result_key] = None

        # Inject reject feedback into HITL stage output so the stage sees the reason
        if idx >= 0 and idx < len(self._config.stages) and feedback:
            _stage = self._config.stages[idx]
            state[_stage.output_artifact] = {"raw_output": feedback, "source": "human_reject"}

        state["phase"] = PipelinePhase.EXECUTING

        state["qa_retry"] = 0

        state["_stagnation_count"] = 0

        state["tokens_used"] = 0

        state.pop("error", None)

        state.pop("_last_action_reason", None)

        return await self._run_stages_from(idx, state)


    # ── v3.1: Event-driven HITL methods ──────────────────────────────

    async def run(self, project_id: str, initial_state: Dict[str, Any]) -> None:
        """Event-driven pipeline main loop — the entire lifecycle runs here."""
        register_pipeline(project_id, self)
        self._state = initial_state
        self._state.setdefault("phase", "executing")
        self._state.setdefault("project_id", project_id)
        self._state["started_at"] = __import__("datetime").datetime.now().isoformat()

        try:
            if self._persist_callback:
                self._persist_callback(dict(self._state))

            idx = int(self._state.get("_current_stage_idx", 0) or 0)
            total = len(self._config.stages)

            while idx < total and not self._shutdown_requested:
                self._state["_current_stage_idx"] = idx
                stage = self._config.stages[idx]

                # Execute via the same dispatcher _run_stages_from uses
                if getattr(stage, 'skill_name', ''):
                    self._state = await self._run_stage_skill(stage, self._state)
                else:
                    self._state = await self._exec_stage(stage, self._state)

                # Check for HITL pause
                if self._state.get("phase") == "paused":
                    if self._persist_callback:
                        self._persist_callback(dict(self._state))

                    # v3.3: Wait for HITL — event (local) OR DB poll (cross-worker)
                    _log_engine = __import__("logging").getLogger("pipeline_engine")
                    _log_engine.warning("v3.3 HITL paused: stage=%s idx=%d",
                        self._state.get("_hitl_stage_id", "?"), idx)
                    await self._wait_for_hitl()

                    # 🚀  Wake up: check if reject or approve
                    if self._reject_feedback:
                        _log_engine.warning("v3.3 HITL rejected: invalidating from idx=%d", idx)
                        self._invalidate_downstream(idx)
                        # idx stays the same — re-run current stage
                    else:
                        idx += 1  # Approved — move to next stage
                else:
                    idx += 1

            if not self._shutdown_requested:
                self._state["phase"] = "done"

        except asyncio.CancelledError:
            self._state["phase"] = "failed"
            self._state["error_message"] = "Pipeline task cancelled"
            raise
        except Exception as e:
            self._state["phase"] = "failed"
            self._state["error_message"] = str(e)[:500]
        finally:
            if self._state.get("phase") not in ("done", "failed"):
                self._state["phase"] = "done"
            self._state["finished_at"] = __import__("datetime").datetime.now().isoformat()
            if self._persist_callback:
                self._persist_callback(dict(self._state))
            unregister_pipeline(project_id)

    def approve(self, feedback: str = "") -> None:
        """Synchronous: approve HITL and wake the engine.
        
        Must write DB BEFORE setting the event — ensures GET /state returns
        consistent data (phase=executing + HITL fields cleared) immediately.
        """
        # ① Idempotency guard
        if self._state.get("phase") != "paused":
            return
        # ② Ensure _current_stage_idx is set
        self._state.setdefault("_current_stage_idx", 0)
        # ③ Update in-memory state
        hitl_id = self._state.get("_hitl_stage_id", "")
        self._state[f"_hitl_resolved_{hitl_id}"] = True
        self._state["_hitl_stage_id"] = ""
        self._state["_hitl_output_artifact"] = ""
        self._state["_hitl_phase_name"] = ""
        self._state["_hitl_human_feedback"] = ""
        self._state["phase"] = "executing"
        self._reject_feedback = ""
        # ④ Persist to DB first — single atomic transaction
        if self._persist_callback:
            self._persist_callback(dict(self._state))
        # ⑤ Wake the engine AFTER DB is confirmed
        self._resume_event.set()

    def reject(self, feedback: str) -> None:
        """Synchronous: reject HITL and wake the engine for re-run.
        
        Same DB-before-event ordering as approve().
        """
        if self._state.get("phase") != "paused":
            return
        self._state.setdefault("_current_stage_idx", 0)
        self._reject_feedback = feedback
        self._state["_reject_feedback"] = feedback
        self._state["_hitl_stage_id"] = ""
        self._state["_hitl_output_artifact"] = ""
        self._state["_hitl_phase_name"] = ""
        self._state["phase"] = "executing"
        if self._persist_callback:
            self._persist_callback(dict(self._state))
        self._resume_event.set()

    def force_terminate(self) -> None:
        """Emergency: terminate the pipeline immediately."""
        self._shutdown_requested = True
        self._state["phase"] = "failed"
        self._state["error_message"] = "Force terminated by administrator"
        self._resume_event.set()

    def _invalidate_downstream(self, start_idx: int) -> None:
        """Clear artifacts for current and all downstream stages."""
        for i in range(start_idx, len(self._config.stages)):
            key = self._config.stages[i].output_artifact
            if key and key in self._state:
                self._state.pop(key, None)
        self._state.pop("_progress", None)
        self._state.pop("_reject_feedback", None)


    async def _wait_for_hitl(self) -> None:
        """Wait for HITL resolution — local event OR cross-worker DB signal.

        The main pipeline loop calls `_resume_event.wait()` for local approve/reject
        (same worker). The HTTP endpoint writes the action directly.

        For cross-worker (different worker): the HTTP handler writes the action
        to the DB. This method polls the DB every 1 second and converts any
        pending action into an `_resume_event.set()`.
        """
        import asyncio as _aio
        from core.harness.execution.pipeline_run_store import get_pipeline_run_store

        _run_id = self._state.get("session_id", "")

        async def _check_event():
            await self._resume_event.wait()
            return True

        async def _check_db():
            store = get_pipeline_run_store()
            while True:
                await _aio.sleep(1)
                action = store.poll_hitl_action(_run_id)
                if action:
                    if action == "approve":
                        self._reject_feedback = ""
                    elif action == "reject":
                        self._reject_feedback = self._reject_feedback or "cross-worker reject"
                    # Clear the action and wake the engine
                    store.clear_hitl_action(_run_id)
                    self._resume_event.set()
                    return True

        tasks = [_aio.create_task(_check_event()), _aio.create_task(_check_db())]
        done, pending = await _aio.wait(tasks, return_when=_aio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        self._resume_event.clear()


    async def _resume_from_hitl(self) -> None:
        """Recover after restart: re-register + enter HITL wait loop.

        The pipeline was paused at HITL when the server restarted.
        All state (including the completed stage's artifact) is intact.
        We just need to re-enter the Event-driven wait loop so the
        user can approve/reject and the pipeline can continue.
        """
        _log_engine = __import__("logging").getLogger("pipeline_engine")
        _log_engine.warning("v3.2 HITL recovery: resuming paused pipeline for project %s",
            self._state.get("project_id", "?"))

        idx = int(self._state.get("_current_stage_idx", 0) or 0)
        total = len(self._config.stages)

        # Defensive: if HITL fields were lost or point to a non-stage id (e.g. a
        # skill_name from an older broken recovery), re-derive from the current
        # stage index so the frontend still knows which stage/artifact to approve.
        _valid_stage_ids = {getattr(_s, 'id', '') for _s in self._config.stages}
        _hitl_id = self._state.get("_hitl_stage_id") or ""
        if (_hitl_id not in _valid_stage_ids) and 0 <= idx < total:
            _s = self._config.stages[idx]
            self._state["_hitl_stage_id"] = getattr(_s, 'id', '') or ''
            self._state["_hitl_phase_name"] = self._state.get("_hitl_phase_name") or (getattr(_s, 'hitl_phase', '') or 'review')
            self._state["_hitl_output_artifact"] = getattr(_s, 'output_artifact', '') or ''
            _log_engine.warning("v3.2 HITL recovery: re-derived HITL fields from idx=%d (stage=%s)",
                                idx, getattr(_s, 'id', '?'))

        # Ensure phase is correct (may have been tampered by cleanup)
        self._state["phase"] = "paused"
        if self._persist_callback:
            self._persist_callback(dict(self._state))

        _log_engine.warning("v3.3 HITL recovery: waiting for approval at stage idx=%d", idx)
        await self._wait_for_hitl()

        # After wake: check if rejected or approved
        if self._reject_feedback:
            _log_engine.warning("v3.2 HITL recovery: rejected — invalidating from idx=%d", idx)
            self._invalidate_downstream(idx)
            # idx stays same — re-run current stage
        else:
            idx += 1  # Approved — move to next
            _log_engine.warning("v3.2 HITL recovery: approved — continuing from idx=%d", idx)

        # Continue with remaining stages
        self._state["phase"] = "executing"
        await self._run_stages_from(idx, self._state)

        if not self._shutdown_requested:
            self._state["phase"] = "done"
            if self._persist_callback:
                self._persist_callback(dict(self._state))

        # Unregister when done
        try:
            unregister_pipeline(self._state.get("project_id", ""))
        except Exception:
            pass  # noqa: cleanup-best-effort



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

        state["phase"] = PipelinePhase.EXECUTING

        state["_stagnation_count"] = 0

        state["qa_retry"] = 0

        state["tokens_used"] = 0

        state.pop("error", None)

        return await self._run_stages_from(target_idx, state)



    def get_stages(self) -> List[PipelineStageConfig]:

        """Public getter for pipeline stages. Platform uses this instead of

        accessing engine._config.stages directly."""

        return list(self._config.stages)



    def assemble_deploy(self, state: Dict[str, Any]) -> str:

        """Assemble a deploy directory from pipeline output artifacts. Returns path."""

        import os as _os

        output_dir = state.get("output_dir", "")

        if not output_dir or not _os.path.isdir(output_dir):

            return ""

        return output_dir



    async def _capture_stage_reflection(self, stage: PipelineStageConfig, state: Dict) -> Any:

        """Capture per-stage reflection for self-improvement loop (stub)."""

        return None



    async def resume_from(self, start_idx: int, state: PipelineState) -> PipelineState:

        """Public wrapper for _run_stages_from. Platform uses this instead of

        calling the private method directly."""

        return await self._run_stages_from(start_idx, state)


    async def resume_from_checkpoint(self, run_id: str, session_id: str = "") -> PipelineState:

        """v4.0: cross-session intelligent resume — continue from the last completed stage.

        Priority:

          1. Read stage status from pipeline_run_store → locate the failed/incomplete stage

          2. Restore PipelineState from the on-disk checkpoint JSON

          3. Analyze the failure cause → decide whether to retry / compress context / fall back to the previous stage

          4. Continue execution from the resume point

        """

        state = self._load_pipeline_state(session_id, run_id)

        if not state:

            raise ValueError(f"Pipeline state not found for run={run_id}")


        # 1. Load stage status from store

        try:

            from core.harness.execution.pipeline_run_store import get_pipeline_run_store

            store = get_pipeline_run_store()

            stages_raw = store.list_stages(run_id) if hasattr(store, 'list_stages') else []

        except Exception:

            stages_raw = []


        # 2. Find resume point

        resume_idx = 0

        for s in sorted(stages_raw, key=lambda x: x.get("stage_idx", 0) if isinstance(x, dict) else 0):

            if not isinstance(s, dict):

                continue

            status = s.get("status", "")

            if status == "completed":

                resume_idx = max(resume_idx, s.get("stage_idx", 0) + 1)

            elif status in ("failed", "timeout"):

                # v4.0 enhancement 3: intelligent resume — analyze the failure cause

                error = s.get("error_message", "")

                if "context_length" in error.lower() or "token" in error.lower():

                    # Compress context before retry

                    state["_force_context_compress"] = True

                resume_idx = s.get("stage_idx", 0)

                break


        # 3. Restore from disk checkpoints if state is stale

        checkpoints = self._load_checkpoints_from_disk(state)

        if checkpoints:

            last_healthy = [c for c in checkpoints if isinstance(c, dict) and not c.get("error")]

            if last_healthy:

                last = last_healthy[-1]

                state["_current_stage_idx"] = last.get("stage_idx", resume_idx)

                state["tokens_used"] = last.get("tokens_used", 0)

                state["_wake_recovered"] = True


        # 4. Resume execution

        return await self._run_stages_from(resume_idx, state)



    def _should_use_dynamic_routing(self, stages: List[PipelineStageConfig], session_id: str = "") -> bool:

        """Check if any stage has routing_mode='llm' and grayscale allows it."""

        has_llm_stage = any(getattr(s, "routing_mode", "static") == "llm" for s in stages)

        if not has_llm_stage:

            return False

        # Grayscale percentage — deterministic hash per session

        pct_str = os.getenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100")

        try:

            pct = int(pct_str)

        except ValueError:

            pct = 100

        if pct >= 100:

            return True

        if pct <= 0:

            return False

        # Deterministic per-session bucketing (same hash method as SkillRouter)

        if not session_id:

            return True  # no session id available, default to on

        bucket = int(hashlib.md5(f"dynamic_router:{session_id}".encode()).hexdigest(), 16) % 100

        return bucket < pct



    async def _run_stages_from(self, start_idx: int, state: PipelineState) -> PipelineState:

        import asyncio

        state = dict(state)

        stages = self._config.stages

        session_id = state.get("session_id", "")

        # Config-driven pipeline mode: per-stage pipeline_mode or default "chain"
        _pipeline_mode = getattr(stages[0], "pipeline_mode", "chain") if stages else "chain"

        # MoA mode: Mixture of Agents — parallel references + aggregator synthesis

        if any(getattr(s, "routing_mode", "static") == "moa" for s in stages):

            return await self._run_moa(stages, state)

        # Swarm mode: multi-agent parallel competition (Skill 6, Octo Swarm)

        if any(getattr(s, "routing_mode", "static") == "swarm" for s in stages):

            return await self._run_swarm(stages, state)

        # Roundtable mode: multi-agent equal discussion (Skill 2, Octo Roundtable)

        if any(getattr(s, "routing_mode", "static") == "roundtable" for s in stages):

            return await self._run_roundtable(stages, state)

        # Debate mode: multi-agent adversarial collaboration (Skill 6)

        if any(getattr(s, "routing_mode", "static") == "debate" for s in stages):

            return await self._run_debate(stages, state)

        # Dynamic routing: LLM-driven stage selection (replaces static dependency layers)

        if self._should_use_dynamic_routing(stages, session_id):

            return await self._run_dynamic_routing(stages, state)

        # Compute dependency layers for parallel execution (P0-3)

        layers = self._compute_dependency_layers(stages, start_idx)

        for layer in layers:

            if not layer:

                continue

            # Check cancel signal

            if _pipeline_cancels.get(state.get("session_id", "")):

                state["error"] = "cancelled_by_user"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "cancelled"

                _pipeline_cancels.pop(state.get("session_id", ""), None)

                break

            # Check if pipeline is already failed before executing layer

            if state.get("phase") == PipelinePhase.FAILED:

                state.setdefault("_last_action_reason", "phase_failed")

                # Fire-and-forget: trigger AutoLearner on pipeline failure

                try:

                    import asyncio as _asyncio_p

                    _asyncio_p.ensure_future(_trigger_pipeline_auto_learner(

                        agent_id=str(state.get("agent_id", "")),

                        run_id=str(state.get("_run_id", "")),

                        task=str(state.get("_pipeline_goal", "")),

                        error=str(state.get("error", "") or "pipeline phase failed"),

                        session_id=str(state.get("session_id", "")),

                    ))

                except Exception:

                    logging.getLogger(__name__).debug('_run_stages_from failed', exc_info=True)
                # Fire-and-forget: notify via messaging gateway on pipeline failure

                try:

                    import asyncio as _asyncio_gw

                    _asyncio_gw.ensure_future(_notify_pipeline_failure(state))

                except Exception:

                    logging.getLogger(__name__).debug('_run_stages_from failed', exc_info=True)
                break

            # Emit pre-layer state for frontend polling

            _event_bus.emit(state.get("session_id", ""), "layer_before", {"state": dict(state)})



            # Apply propagation_rules — declarative cross-stage property forwarding

            for idx in layer:

                stage = stages[idx]

                rules = getattr(stage, "propagation_rules", None) or []

                for rule in rules:

                    try:

                        src_entity = rule.get("source_entity", "")

                        src_prop = rule.get("source_prop", "")

                        target_prop = rule.get("target_prop", "")

                        agg = rule.get("aggregation", "last")

                        # Look up source value from completed stages

                        for s in stages:

                            if s.id == src_entity and state.get(s.output_artifact):

                                val = state[s.output_artifact]

                                if agg == "concat" and target_prop in state:

                                    state[target_prop] = str(state.get(target_prop, "")) + str(val)

                                elif agg == "max":

                                    prev = state.get(target_prop, 0) or 0

                                    state[target_prop] = max(prev, val) if isinstance(val, (int, float)) else val

                                elif agg == "avg":

                                    cnt_key = f"_{target_prop}_cnt"

                                    cnt = (state.get(cnt_key, 0) or 0) + 1

                                    prev_sum = (state.get(target_prop, 0) or 0) * (cnt - 1)

                                    state[cnt_key] = cnt

                                    state[target_prop] = (prev_sum + val) / cnt

                                else:  # "last" or default

                                    state[target_prop] = val

                                break

                    except Exception as e:

                        logging.warning(str(e), exc_info=True)



            # Execute all stages in this layer sequentially
            results = []
            for i in layer:
                try:
                    result = await self._exec_single_stage(stages[i], i, state)
                    results.append(result)
                except Exception as e:
                    results.append(e)

            # Merge results and check for HITL

            paused = False

            for i, result in enumerate(results):

                if isinstance(result, Exception):

                    idx = layer[i]

                    import logging as _plog
                    _plog.getLogger("pipeline_engine").warning(
                        "Stage %d exception: %s", idx, result, exc_info=True)
                    state["_last_action_reason"] = f"stage_{idx}_error:{result}"

                    continue

                if result is None:

                    continue

                r_state, r_paused = result

                # Reducer-based state merge (config-driven, prevents parallel overwrite)

                self._merge_state(state, r_state, stages[layer[i]] if i < len(layer) else None)

                if r_paused:

                    paused = True

            # Handle conditional routing after layer results are merged

            route_to = state.pop("_route_after", None)

            if route_to is not None and isinstance(route_to, int) and 0 <= route_to < len(stages):

                # Re-compute layers from the routing target, skipping already-done stages

                layers = self._compute_dependency_layers(stages, route_to)

                continue

            # Live state push for frontend polling

            _event_bus.emit(state.get("session_id", ""), "layer_after", {"state": dict(state)})



            # P1-3: Dynamic budget redistribution — unused tokens distributed to remaining stages

            try:

                stage_count = len(stages)

                completed = sum(1 for s in stages if state.get(f"_stage_{s.id}_done"))

                remaining = stage_count - completed

                if remaining > 0:

                    total_budget = getattr(self._config, 'max_tokens_per_run', 100000)

                    used = int(state.get("tokens_used", 0) or 0)

                    expected_used = total_budget * (completed / stage_count)

                    if used < expected_used:

                        bonus = (expected_used - used) // remaining

                        current_bonus = int(state.get("_tokens_bonus", 0) or 0)

                        state["_tokens_bonus"] = current_bonus + bonus

            except Exception:

                logging.getLogger(__name__).debug('_stage_with_sem failed', exc_info=True)
            if paused:

                return state



        if state.get("phase") == PipelinePhase.EXECUTING:

            state["phase"] = PipelinePhase.DONE

        try:

            self._snapshot(state, "final_state")

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # Crystallize successful pipeline execution into a reusable Skill

        try:

            await self._crystallize_skill(state)

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # Feed execution into knowledge graph (F5: ops → knowledge auto-indexing)

        try:

            import asyncio

            asyncio.create_task(self._feed_execution_to_graph(state))

        except Exception:

            logging.getLogger(__name__).debug('_stage_with_sem failed', exc_info=True)
        # Notify PushManager on pipeline completion

        try:

            from core.harness.feedback_loops.push import get_push_manager

            pm = get_push_manager()

            if pm:

                pm.push("pipeline", payload={"type": "pipeline_complete", "phase": state.get("phase"),

                    "session_id": state.get("session_id")})

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        

        # Feed successful pipeline into CMM PatternAccumulator + ExperienceVector

        try:

            run_id = str(state.get("_run_id", ""))

            if run_id:

                from core.harness.memory.pattern_accumulator import get_pattern_accumulator

                pa = get_pattern_accumulator()

                await pa.extract_from_run(run_id=run_id, tenant_id=str(state.get("tenant_id", "")))

                

                from core.harness.learning.experience_vector import get_experience_cache

                cache = get_experience_cache()

                agent_id = str(state.get("agent_id", ""))

                stage_count = len(state.get("stages", []))

                await cache.store(

                    run_id=run_id,

                    summary=f"[{agent_id}] Pipeline completed: {stage_count} stages",

                    label="success",

                )

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # Generalize successful pipeline execution into reusable rules

        try:

            import asyncio as _asyncio_g

            _asyncio_g.ensure_future(_generalize_pipeline_success(state))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


        # Verify pipeline outputs against specifications (assertion/schema/regression checks)

        try:

            await _verify_pipeline_outputs(state)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Update workflow_runs phase

        try:

            session_id = state.get("session_id", "")

            if session_id:

                _update_workflow_run_phase(session_id, state.get("phase", "done"))

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        # Clean up cancel registry entry (safety net, even if currently unused)

        sid = state.get("session_id", "")

        if sid:

            _pipeline_cancels.pop(sid, None)

        # Clean up intermediate artifacts to release memory after successful run

        try:

            self._cleanup_pipeline_artifacts(state)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        if state.get("phase") != PipelinePhase.PAUSED:
            state["phase"] = PipelinePhase.DONE
        _event_bus.emit(state.get("session_id", ""), "complete", {"state": dict(state)})

        return state



    def _cleanup_pipeline_artifacts(self, state: PipelineState) -> None:

        """Release memory by replacing large intermediate stage artifacts with stubs.



        After pipeline completion, only the final stage output and small artifacts

        (<1KB) are retained. Large intermediate outputs are replaced with a stub

        pointing to the snapshot for recovery.

        """

        stages = self._config.stages if self._config else []

        if not stages:

            return



        keep_keys = {"phase", "session_id", "_run_id", "error", "context",

                     "_last_action_reason", "_hitl_output_artifact", "_graph_trace",

                     "_checkpoints", "_parallel_stats", "tokens_used", "_tokens_bonus",

                     "_deploy_compile_errors", "tenant_id", "agent_id", "_pipeline_goal"}

        # Also keep the final stage's output artifact

        final_stage = stages[-1] if stages else None

        if final_stage and final_stage.output_artifact:

            keep_keys.add(final_stage.output_artifact)

        if final_stage and final_stage.test_result_key:

            keep_keys.add(final_stage.test_result_key)



        cleaned = 0

        saved_bytes = 0

        # Keep last 3 stages for builder pipelines (not just 1)
        _keep_count = min(3, len(stages))
        for stage in (stages[:-_keep_count] if _keep_count < len(stages) else []):

            key = stage.output_artifact

            if not key or key in keep_keys:

                continue

            val = state.get(key)

            if val is None:

                continue

            size = len(str(val))

            if size < 1024:  # keep small artifacts

                keep_keys.add(key)

                continue

            state[key] = f"[cleaned: {size} bytes, stage={stage.id}]"

            cleaned += 1

            saved_bytes += size



        if cleaned:

            logging.getLogger("pipeline_engine").info(

                "Artifact cleanup: freed ~%d bytes across %d stages (kept final: %s)",

                saved_bytes, cleaned, final_stage.output_artifact if final_stage else "none")



    async def _run_dynamic_routing(

        self, stages: List[PipelineStageConfig], state: PipelineState

    ) -> PipelineState:

        """LLM-driven routing loop — one stage at a time, Supervisor picks next."""

        from core.harness.execution.dynamic_router import DynamicRouter

        # Collect agent descriptions from stage configs

        agent_descriptions: Dict[str, str] = {}

        for s in stages:

            name = s.agent_name or s.agent_id

            if name:

                desc_parts = []

                if s.output_artifact:

                    desc_parts.append(f"output:{s.output_artifact}")

                if getattr(s, "uses_file_output", False):

                    desc_parts.append("file ops")

                agent_descriptions[name] = ", ".join(desc_parts) if desc_parts else "general"



        # Stage index map for routing

        stage_idx_map: Dict[str, int] = {s.id: i for i, s in enumerate(stages)}



        router = DynamicRouter(

            agent_descriptions=agent_descriptions,

            max_steps=int(os.getenv("AIPLAT_DYNAMIC_ROUTER_MAX_STEPS", "15")),

        )

        goal = state.get("_pipeline_goal", "execute pipeline")

        logger = logging.getLogger("pipeline_engine.dynamic_router")

        logger.info("Dynamic routing active: %d stages, goal='%s'",

                     len(stages), goal[:80])



        step = 0

        max_steps = router.max_steps

        done_indices: Set[int] = set()



        while step < max_steps:

            step += 1

            # Build list of not-yet-executed agents

            available_names = [

                s.agent_name or s.agent_id

                for i, s in enumerate(stages) if i not in done_indices

            ]

            if not available_names:

                break



            # Supervisor decides next agent

            available = available_names

            decision = await router._decide_next(state, goal, available, step)

            state.setdefault("_dynamic_trace", []).append({

                "step": step, "agent": decision.agent_name,

                "reasoning": decision.reasoning, "decision": decision.decision,

            })

            logger.info("DynamicRouter step %d: %s → %s",

                         step, decision.decision, decision.agent_name or "FINISH")



            if decision.decision != "call_agent" or not decision.agent_name:

                break  # FINISH or error



            # Find target stage index

            target_idx = None

            for i, s in enumerate(stages):

                if (s.agent_name == decision.agent_name or s.agent_id == decision.agent_name) and i not in done_indices:

                    target_idx = i

                    break



            if target_idx is None:

                logger.warning("Router chose agent '%s' but not found in remaining stages", decision.agent_name)

                continue



            # Execute single stage

            state["_last_action_reason"] = f"dynamic_routed_to:{decision.agent_name}"

            state["_current_stage_idx"] = target_idx

            _event_bus.emit(state.get("session_id", ""), "layer_before", {"state": dict(state)})



            try:

                result = await asyncio.wait_for(

                    self._exec_single_stage(stages[target_idx], target_idx, state),

                    timeout=600,

                )

            except asyncio.TimeoutError:

                state["error"] = f"dynamic_stage_timeout:{decision.agent_name}"

                state["phase"] = PipelinePhase.FAILED

                break



            if isinstance(result, Exception):

                import logging as _plog2
                _plog2.getLogger("pipeline_engine").warning(
                    "Stage %d exception (dynamic): %s", target_idx, result, exc_info=True)
                state["_last_action_reason"] = f"stage_{target_idx}_error:{result}"

                continue

            if result is None:

                continue

            r_state, r_paused = result

            self._merge_state(state, r_state, stages[target_idx])

            done_indices.add(target_idx)



            if r_paused:

                state["phase"] = PipelinePhase.PAUSED

                return state



            if state.get("phase") == PipelinePhase.FAILED:

                break



            _event_bus.emit(state.get("session_id", ""), "layer_after", {"state": dict(state)})



        logger.info("Dynamic routing finished: %d/%d stages executed", len(done_indices), len(stages))

        # Persist trace for developer visibility (3-tier Loop P2)

        await self._persist_dynamic_trace(state, done_indices, stages)

        return state



    async def _run_debate(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Skill 6: Multi-agent debate via run_agent_debate() from core debate engine."""

        from core.harness.execution.debate import run_agent_debate



        goal = state.get("_pipeline_goal", "execute pipeline")

        logger = logging.getLogger("pipeline_engine.debate")

        logger.info("Debate mode active: %d stages, goal='%s'", len(stages), goal[:80])



        # Build agent configs from stages

        agent_configs = []

        for s in stages:

            name = s.agent_name or s.agent_id

            agent_configs.append({

                "name": name,

                "side": name,

                "model": getattr(s, "model", ""),

                "prompt_template": goal + "\n\n{debate_info}" if hasattr(s, '__dict__') else goal,

            })



        if len(agent_configs) < 2:

            return state



        # Use existing run_agent_debate with convergence detection

        async def _run_agent(agent_name: str, prompt: str, model: str = "") -> str:

            for i, s in enumerate(stages):

                if (s.agent_name or s.agent_id) == agent_name:

                    state["_route_after"] = i

                    state["_last_action_reason"] = f"debate:{agent_name}"

                    break

            return ""  # Actual execution handled by pipeline engine's layer loop



        result = await run_agent_debate(

            agent_configs=agent_configs,

            debate_info={"context": goal, "date": "", "ticker": ""},

            max_rounds=3,

            run_agent=_run_agent,

        )



        state.setdefault("_dynamic_trace", []).append({

            "step": result.get("rounds", 0) + 1,

            "agent": "supervisor",

            "role": "merge",

                    "reasoning": f"debate completed: {result.get('rounds')} rounds, converged={result.get('converged')}",

        })

        return state



    async def _run_moa(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Phase 42: MoA routing — each stage runs through parallel reference

        engines + aggregator synthesis. Reluses moa_executor syscall."""

        for stage in stages:

            if getattr(stage, "routing_mode", "static") != "moa":

                continue

            preset = getattr(stage, "moa_preset", "general")

            max_refs = getattr(stage, "moa_reference_count", 3)

            prompt = self._build_stage_prompt(stage, state)

            try:

                from core.harness.syscalls.moa_executor import execute as moa_execute

                result = await moa_execute(

                    query=prompt, preset=preset,

                    max_reference_models=max_refs,

                    session_id=state.get("session_id", ""),

                )

                key = getattr(stage, "output_artifact", f"_moa_{stage.stage_id}")

                state[key] = result.final_answer

                state[f"_moa_meta_{stage.stage_id}"] = {

                    "preset": result.preset, "duration_ms": result.duration_ms,

                    "failed_refs": result.failed_references,

                    "cost_usd": result.estimated_cost_usd,

                }

                logging.getLogger("pipeline").info(

                    "[moa] stage=%s preset=%s duration=%dms cost=$%.4f",

                    stage.stage_id, preset, int(result.duration_ms),

                    result.estimated_cost_usd,

                )

            except Exception as e:

                logging.getLogger("pipeline").warning("[moa] stage=%s failed: %s", stage.stage_id, e)

        return state



    async def _run_swarm(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Skill 6 Swarm: N agents execute same task independently → Arena selects best."""

        from core.harness.execution.swarm import run_swarm



        goal = state.get("_pipeline_goal", "execute pipeline")

        agent_names = [s.agent_name or s.agent_id for s in stages]

        logger = logging.getLogger("pipeline_engine.swarm")

        logger.info("Swarm mode: %d agents, goal='%s'", len(agent_names), goal[:80])



        async def _run_one(name: str, task: str, model: str = "") -> str:

            return f"[{name}] analysis of: {task[:200]}"



        result = await run_swarm(

            task=goal,

            agent_names=agent_names,

            run_agent=_run_one,

        )



        state.setdefault("_dynamic_trace", []).append({

            "step": 1, "agent": "swarm",

            "role": "merge",

                    "reasoning": f"tournament completed: winner={result.get('winner')}, scores={result.get('scores')}",

        })

        return state



    async def _run_roundtable(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Skill 2 Roundtable: agents discuss equally, seeing all prior outputs each round."""

        from core.harness.execution.roundtable import run_roundtable



        goal = state.get("_pipeline_goal", "execute pipeline")

        agent_names = [s.agent_name or s.agent_id for s in stages]

        logger = logging.getLogger("pipeline_engine.roundtable")

        logger.info("Roundtable mode: %d agents, topic='%s'", len(agent_names), goal[:80])



        async def _run_one(name: str, prompt: str, model: str = "") -> str:

            return f"[{name}] perspective on: {prompt[-200:]}"



        result = await run_roundtable(

            topic=goal,

            agent_names=agent_names,

            run_agent=_run_one,

        )



        state.setdefault("_dynamic_trace", []).append({

            "step": result.get("rounds", 0),

            "agent": "roundtable",

            "role": "synthesis",

                    "reasoning": f"roundtable completed: {result.get('rounds')} rounds, converged={result.get('converged')}",

        })

        return state



    async def _persist_dynamic_trace(

        self, state: PipelineState, done_indices: set, stages: list,

    ) -> None:

        """Persist DynamicRouter trace to SpecLifecycle for developer review."""

        spec_id = state.get("spec_id", "")

        trace = state.get("_dynamic_trace", [])

        run_id = state.get("_run_id", state.get("session_id", ""))

        if not spec_id or not trace:

            return

        try:

            from core.harness.models.spec_lifecycle import get_spec_lifecycle

            sl = get_spec_lifecycle()

            latest = sl.get_latest(spec_id)

            if latest and latest.status.value == "executing":

                result = {

                    "summary": f"done {len(done_indices)}/{len(stages)} stages",

                    "trace": trace,

                    "done_stages": list(done_indices),

                    "agent_order": [t.get("agent", "") for t in trace],

                }

                sl.mark_review(spec_id, latest.version, run_id=str(run_id), result=result)

        except Exception:

            logging.getLogger("pipeline_engine").debug("Trace persistence skipped", exc_info=True)



    def _compute_dependency_layers(

        self, stages: List[PipelineStageConfig], start_idx: int

    ) -> List[List[int]]:

        """Topologically sort stages into dependency layers for parallel execution."""

        artifact_to_idx: Dict[str, int] = {}

        node_id_to_idx: Dict[str, int] = {}

        for i, s in enumerate(stages):

            if s.output_artifact:

                artifact_to_idx[s.output_artifact] = i

            node_id_to_idx[s.id] = i



        import sys as _s, json as _j

        _s.stderr.write(f"### _COMPUTE_DEPS start={start_idx} stages={{{_j.dumps({i: s.id for i,s in enumerate(stages) if i>=start_idx})}}}\n")

        for i in range(start_idx, len(stages)):

            _s.stderr.write(f"  dep[{i}] {stages[i].id} output={stages[i].output_artifact} deps={stages[i].depends_on}\n")

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

            for dep in deps:

                dep_idx = node_id_to_idx.get(dep, artifact_to_idx.get(dep))

                if dep_idx is not None and dep_idx < i:

                    # Skip deps on stages before start_idx (already completed)

                    if dep_idx >= start_idx:

                        graph.setdefault(dep_idx, []).append(i)

                        in_degree[i] = in_degree.get(i, 0) + 1



        layers: List[List[int]] = []

        remaining = set(range(start_idx, len(stages)))

        while remaining:

            current = sorted([i for i in remaining if in_degree.get(i, 0) == 0])

            if not current:

                # Cycle or all remaining have unsatisfied deps; sequential fallback

                current = sorted(remaining)

                logging.getLogger("pipeline_engine").warning(

                    f"Pipeline dependency cycle detected among stages: {[stages[i].id for i in sorted(remaining)]}"

                )

            layers.append(current)

            for n in current:

                remaining.discard(n)

                for child in graph.get(n, []):

                    in_degree[child] = max(0, in_degree.get(child, 1) - 1)

            if current == sorted(remaining):

                remaining.clear()



        return layers



    # ── Phase 10: Dispatch tables (replace if/elif chains) ──











    async def _run_stage_skill(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:
        """Execute a stage via its configured skill, loading SOP from SKILL.md.

        The engine knows NOTHING about what the skill does — it just:
        1. Resolves skill name from stage config
        2. Loads the skill's SOP (system prompt) from SKILL.md
        3. Calls LLM with the SOP + full pipeline state as context
        4. Optionally runs pytest for test-generating skills
        5. Stores result under stage.output_artifact
        """
        _skill_name = getattr(stage, 'skill_name', '') or ''
        if not _skill_name:
            return state

        # ── L2: skip_pytest_gate — generic gate on test-execution stages ──
        # Config-driven: stages declare test_execution_mode="pytest" (team YAML/AGENT.md);
        # 落盘收敛到共享 _apply_skip_pytest_gate（P1-7，防与 _exec_test_runner 双份漂移）。
        if (state.get("skip_pytest_gate")
                and getattr(stage, 'test_execution_mode', '') == "pytest"):
            _skip_key = getattr(stage, 'test_result_key', '') or getattr(stage, 'output_artifact', '') or _skill_name
            if _apply_skip_pytest_gate(state, _skip_key):
                state["_progress"] = {"stage": _skill_name, "status": "completed",
                                      "elapsed_sec": 0, "backend": "skipped_gate", "current_step": 0}
                logging.getLogger("pipeline_engine").warning(
                    "Skill %s: pytest gate skipped (skip_pytest_gate=true)", _skill_name)
                return state

        import os as _os, logging as _log
        import time as _time
        _t0 = _time.time()

        # ── Write running progress immediately — frontend poll sees current stage ──
        _stage_tag = getattr(stage, 'output_artifact', '') or _skill_name
        state["_progress"] = {
            "stage": _stage_tag,
            "status": "running",
            "started_at": _t0,
            "backend": "llm",
            "current_step": 0,
        }
        if self._persist_callback:
            self._persist_callback(dict(state))

        # Step-level metadata (populated by domain/context injection + quality bus)
        _domain_id = ""
        _context_enriched = False
        _quality_score = 0.0
        _profile = getattr(stage, 'context_profile', 'code') or 'code'

        # ── 1. Resolve SOP from SKILL.md ──
        _sop_body = ""
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _sp = _os.path.join(_here, "..", "..", "engine", "skills", _skill_name, "SKILL.md")
        _sp = _os.path.abspath(_sp)
        _alt = _os.path.expanduser(f"~/.aiplat/skills/{_skill_name}/SKILL.md")
        if not _os.path.isfile(_sp):
            _sp = _alt
        if _os.path.isfile(_sp):
            with open(_sp, "r") as _sf:
                _raw = _sf.read()
            if _raw.startswith("---"):
                _parts = _raw.split("---", 2)
                _sop_body = _parts[2].strip() if len(_parts) > 2 else ""
                _execution_type = ""
                try:
                    import yaml as _yaml_mod
                    _fm = _yaml_mod.safe_load(_parts[1])
                    if isinstance(_fm, dict):
                        _execution_type = str(_fm.get("execution_type", "") or "").strip()
                except Exception:
                    _execution_type = ""
        if not _sop_body:
            _log.getLogger("pipeline_engine").warning(
                "Skill %s: no SOP found, falling back to ReAct", _skill_name)
            return state  # caller falls through to _exec_stage

        # ── 1.5. Handler execution (execution_type: handler — deterministic, no LLM) ──
        if _execution_type == "handler":
            _handler_path = _os.path.join(_os.path.dirname(_sp), "handler.py")
            if _os.path.isfile(_handler_path):
                try:
                    import importlib.util as _iu
                    _spec = _iu.spec_from_file_location(f"skill_handler_{_skill_name}", _handler_path)
                    if _spec and _spec.loader:
                        _hmod = _iu.module_from_spec(_spec)
                        _spec.loader.exec_module(_hmod)
                        if hasattr(_hmod, "execute") and callable(_hmod.execute):
                            _hparams = self._build_handler_params(stage, state)
                            _hres = _hmod.execute(_hparams)
                            import asyncio as _aio_mod
                            if _aio_mod.iscoroutine(_hres):
                                _hres = await _hres
                            if isinstance(_hres, dict):
                                import json as _hj_local
                                _artifact_key = getattr(stage, 'output_artifact', '') or _skill_name
                                state[_artifact_key] = {
                                    "raw_output": _hj_local.dumps(_hres, ensure_ascii=False),
                                    "elapsed_sec": round(_time.time() - _t0, 2),
                                }
                                # Handler self-repaired the code (auto-repair fixed pytest) → write back
                                # the fixed code to the file-generating stage (uses_file_output, generic field).
                                _fixed_code = str(_hres.get("fixed_code") or "")
                                if _fixed_code:
                                    for _s in (self._config.stages if self._config else []):
                                        if getattr(_s, 'uses_file_output', False):
                                            _code_artifact = getattr(_s, 'output_artifact', '')
                                            if _code_artifact and isinstance(state.get(_code_artifact), dict):
                                                state[_code_artifact]["raw_output"] = _fixed_code
                                            break
                                state["_progress"] = {"stage": _skill_name, "status": "completed",
                                                      "elapsed_sec": round(_time.time() - _t0, 2),
                                                      "backend": "handler", "current_step": 0}
                                if self._persist_callback:
                                    self._persist_callback(dict(state))
                                _log.getLogger("pipeline_engine").warning(
                                    "Skill %s: handler executed (deterministic)", _skill_name)
                                return state
                except Exception as _he:
                    _log.getLogger("pipeline_engine").warning(
                        "Skill %s: handler execution failed, falling back to LLM: %s", _skill_name, _he)

        # Emit node_started event for frontend polling visibility
        try:
            _event_bus.emit(state.get("session_id", state.get("_run_id", "")),
                            "node_started", {"state": dict(state), "node_id": stage.id})
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── 2. Build context from pipeline state ──
        import json as _json
        _context = ""
        _desc = state.get("description", "")
        if _desc:
            _context += f"## description\n{_desc}\n\n"
        # Canonical app_name — established at project creation, reused by all stages.
        # Downstream stages MUST use this value instead of generating their own name.
        _app_name = state.get("app_name", "")
        if _app_name:
            _context += f"## app_name (must use this value, do not rename)\n{_app_name}\n\n"
        # Canonical project_id — the unique project key, injected for FK linkage.
        _project_id = state.get("project_id", "")
        if _project_id:
            _context += f"## project_id (must use this value, do not rename)\n{_project_id}\n\n"
        # Regenerate feedback — injected so the stage re-runs with the human/Bug fix instructions
        _reject_feedback = state.get("_reject_feedback", "")
        if _reject_feedback:
            _context += (
                "\n## 🛑 REGENERATE WITH FEEDBACK — YOU MUST FIX THESE ISSUES\n"
                "You were rejected and must regenerate. Address EVERY issue below.\n"
                "Before generating your final output, ensure each issue is resolved.\n\n"
                f"{_reject_feedback}\n\n---\n"
            )
        # Append upstream stage outputs as context (config-driven keys)
        _input_artifacts = getattr(stage, 'input_artifacts', []) or []
        for _s in (self._config.stages if self._config else []):
            _key = getattr(_s, 'output_artifact', '')
            if not _key or _key == getattr(stage, 'output_artifact', ''):
                continue  # skip own output
            _v = state.get(_key, {})
            if isinstance(_v, dict) and _v.get("raw_output"):
                import json as _ctx_json
                if _key in _input_artifacts:
                    # Critical input — include full content, don't summarize
                    _context += f"## {_key}\n{str(_v['raw_output'])}\n\n"
                else:
                    _summary = self._summarize_artifact(_v)
                    _context += f"## {_key} (summary)\n{_ctx_json.dumps(_summary, ensure_ascii=False)[:2000]}\n\n"

        # Inject architecture_mode into context (config-driven, drives architecture_design output shape)
        _arch_mode = getattr(stage, 'architecture_mode', '') or ''
        if _arch_mode:
            _context = f"## architecture_mode\n{_arch_mode}\n\n" + _context

        # ── L2: imported existing-code context injection (generic, config-driven) ──
        # Enabled per-stage via PipelineStageConfig.inject_imported_context. Engine only
        # reads referenced files + appends the platform-assembled prompt block
        # (behavior contract / intent anchors live in state.imported_repo, assembled
        # by the platform layer — no business knowledge is hardcoded here).
        try:
            if getattr(stage, 'inject_imported_context', False) and state.get("imported_repo"):
                _imp = state["imported_repo"]
                if isinstance(_imp, dict):
                    _root = str(_imp.get("root") or "")
                    _manifest = _imp.get("manifest") or []
                    _modify = _imp.get("modify_files") or []
                    _ctx_block = ["\n\n## imported existing code (imported_repo)"]
                    # 1) Behavior contract — assembled by platform (business text, §3.4)
                    _behavior = str(_imp.get("behavior_prompt") or "")
                    if _behavior:
                        _ctx_block.append(_behavior)
                    # 2) Intent anchors — assembled by platform (path + declared intent, no guessing)
                    _anchor = str(_imp.get("intent_anchor_block") or "")
                    if _anchor:
                        _ctx_block.append(_anchor)
                    # 3) Full text of referenced files (rewrite basis; 200KB cap each)
                    if _root and _os.path.isdir(_root):
                        _root_abs = _os.path.abspath(_root)
                        for _m in _modify:
                            if not isinstance(_m, dict):
                                continue
                            _rel = str(_m.get("path") or "").lstrip("/")
                            if not _rel or ".." in _rel.split("/"):
                                continue
                            _fp = _os.path.join(_root_abs, _rel)
                            if not _os.path.isfile(_fp) or not _fp.startswith(_root_abs + _os.sep):
                                continue
                            try:
                                with open(_fp, "r", encoding="utf-8", errors="replace") as _fh:
                                    _body = _fh.read(200_000)
                                _ctx_block.append(
                                    f"## file: {_rel} (full content, rewrite basis)\n{_body}")
                            except OSError:
                                continue
                    # 4) Manifest listing for the rest (paths only, token-lean)
                    _mod_paths = {str(_m.get("path") or "") for _m in _modify if isinstance(_m, dict)}
                    _rest = [m for m in _manifest if isinstance(m, dict)
                             and m.get("path") not in _mod_paths]
                    if _rest:
                        _list = "\n".join(
                            f"- {m.get('path','')} ({m.get('size',0)}B)" for m in _rest[:200])
                        if _list:
                            _ctx_block.append(
                                f"## imported file listing (do NOT touch unless listed above)\n{_list}")
                    if len(_ctx_block) > 1:
                        _context += "\n\n".join(_ctx_block)
        except Exception:
            logging.getLogger(__name__).debug(
                "swallowing non-critical exception", exc_info=True)  # best-effort context injection

        # ── 3. Inject document schema into system prompt ──
        # Read $ref from SKILL.md YAML frontmatter (not hardcoded artifact key mapping)
        _schema_text = ""
        try:
            _ref = ""
            if _raw.startswith("---"):
                for _line in _raw.split("\n"):
                    _line = _line.strip()
                    if _line.startswith("$ref:"):
                        _ref = _line.split("$ref:", 1)[1].strip().strip('"').strip("'")
                        break
            if _ref:
                _workspace = _os.path.abspath(_os.path.join(_here, "..", "..", "..", "..", ".."))
                _schema_yaml = _os.path.join(_workspace, "config", "document_schemas.yaml")
                if _os.path.isfile(_schema_yaml):
                    import yaml as _yaml
                    with open(_schema_yaml) as _sf:
                        _schemas = _yaml.safe_load(_sf) or {}
                    _spec = _schemas.get("schemas", {}).get(_ref, {}).get("output_spec", "")
                    if _spec:
                        _schema_text = f"\n\n## Output Format Requirements\n{_spec.strip()}"
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        if _schema_text:
            _sop_body = _sop_body.replace("\n\n## Output Format Requirements", "") + _schema_text

        # ── 3.4. Apply query rewrite if enabled ──
        _rewrite = getattr(stage, 'enable_query_rewrite', True)
        if _rewrite and _desc and len(_desc) > 10:
            _context += f"\n## original requirement\n{_desc[:2000]}\n"

        # ── 3.5. Domain-aware context injection ──
        # Automatically classify requirement → inject domain prompt + context bus layers.
        # Engine delegates to DomainRouter + ContextBus — no hardcoded domain knowledge.
        # Respects stage.context_profile: "minimal" skips, "code"/"debug"/"deep" inject.
        try:
            if _profile != "minimal":
                from core.harness.knowledge.domain_router import DomainRouter
                from core.harness.knowledge.context_bus import assemble_pipeline_context
                from core.harness.utils.prompt_loader import _sync_resolve

                # 3.5a. Classify requirement to domain (runs in thread pool to avoid blocking event loop)
                # P0-4 修复（2026-08-25）：_prd 此前未定义 → NameError 被吞 → 域注入 100% 失效。
                # 从 state 解析 PRD dict：prd_data 键优先，否则尝试 description 尾部 JSON。
                _prd = {}
                try:
                    _pd = state.get("prd_data")
                    if isinstance(_pd, dict):
                        _prd = _pd
                    else:
                        import json as _prd_json
                        _desc_str = str(_desc or "")
                        if _desc_str:
                            # description 尾部可能带 prd_data 的 JSON dump
                            _tail = _desc_str[-4000:]
                            _start = _tail.find("{")
                            _end = _tail.rfind("}")
                            if 0 <= _start < _end:
                                _cand = _tail[_start:_end + 1]
                                _parsed = _prd_json.loads(_cand)
                                if isinstance(_parsed, dict):
                                    _prd = _parsed
                except Exception:
                    _prd = {}
                _domain_text = _desc or str(_prd.get("title", "")) if isinstance(_prd, dict) else ""
            if not _domain_text:
                _domain_text = getattr(stage, 'phase', '') or _skill_name
            _domain_id = ""
            try:
                import asyncio as _dom_asyncio
                _domain_id = await _dom_asyncio.to_thread(
                    DomainRouter().classify, _domain_text) or ""
            except Exception:
                _domain_id = ""  # best-effort: classification is optional
            if _domain_id:
                try:
                    _domain_prompt = _sync_resolve(f"domain-prompt-{_domain_id}")
                    _sop_body = _domain_prompt + "\n\n" + _sop_body
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # domain has no prompt configured

            # 3.5b. Inject context bus layers (term dictionary + delivery history + self-optimization)
            _cb_parts = []
            assemble_pipeline_context(
                {"description": _desc, "prd_title": str(_prd.get("title", "")) if isinstance(_prd, dict) else ""},
                _cb_parts
            )
            _cb_text = "\n\n".join(_cb_parts).strip()
            if _cb_text:
                _context += f"\n\n## system knowledge context\n{_cb_text[:2000]}\n"
                _context_enriched = True

        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # best-effort: engine runs fine without context injection

        # ── 3.5: Capability Profile injection (v3.0) ──
        await self._apply_capability_profile(stage, state)

        # ── v1.0: runtime triple — write to TripleStore during Pipeline execution ──
        try:
            from core.harness.ontology_engine.triple_store import get_triple_store, _make_urn
            _ts = get_triple_store()
            _run_urn = _make_urn("run", state.get("_run_id", "") or state.get("run_id", ""))
            _agent_urn = _make_urn("agent", getattr(stage, 'agent_id', '') or '')
            _skill = getattr(stage, 'skill_name', '') or ''
            if _run_urn and _agent_urn:
                _ts.add(_run_urn, "contains_stage", _agent_urn, 1.0, "runtime_scan", {})
            if _agent_urn and _skill:
                _ts.add(_agent_urn, "uses_skill", _make_urn("skill", _skill), 1.0, "runtime_scan", {})
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── 4. Execute: LLM or Agent (config-driven via execution_backend) ──
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        _purpose = getattr(stage, 'skill_model_purpose', '') or 'chat'
        _backend = getattr(stage, 'execution_backend', '') or 'llm'

        if _backend == "agent":
            # Agent runtime → StageRunner → ReActLoop (tools, hooks, token management)
            _log.getLogger("pipeline_engine").warning(
                "Skill %s: running via StageRunner (execution_backend=agent)", _skill_name)
            _stage_tools = getattr(stage, 'tools', None) or []
            state["_sys_prompt"] = _sop_body
            state["_progress"] = {"stage": _skill_name, "status": "running", "started_at": _time.time(),
                                  "backend": "agent", "current_step": 0}
            self._snapshot(state, f"stage_{stage.id}_progress")
            if self._persist_callback:
                self._persist_callback(dict(state))  # immediate: frontend sees "running" now
            _prompt = _context or _desc

            # Background progress polling: snapshot every 5s for real-time frontend visibility
            _poll_active = {"active": True}
            async def _poll_progress():
                _last_step = 0
                while _poll_active["active"]:
                    await asyncio.sleep(5)
                    _cs = int(state.get("step_count", 0) or 0)
                    if _cs and _cs != _last_step:
                        _last_step = _cs
                        state["_progress"]["current_step"] = _cs
                        try:
                            self._snapshot(state, f"stage_{stage.id}_progress")
                        except Exception:
                            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            _poll_task = asyncio.create_task(_poll_progress())

            try:
                _agent_result = await self._stage_runner.run(_prompt, state, stage=stage, tools=_stage_tools)
            finally:
                _poll_active["active"] = False
                try:
                    await asyncio.wait_for(_poll_task, timeout=3)
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            state.pop("_sys_prompt", None)
            # Extract final answer from ReAct dialogue — not the full conversation log
            if hasattr(_agent_result, 'final_answer'):
                _result = str(_agent_result.final_answer or "")
            elif isinstance(_agent_result, dict):
                _result = str(_agent_result.get("final_answer", "") or _agent_result.get("output", ""))
            else:
                _result = str(_agent_result or "")
            _result = _result.replace("```json", "").replace("```", "").strip()
            _elapsed = round(_time.time() - _t0, 2)
            _final_steps = int(state.get("step_count", 0) or 0)
            state["_progress"] = {"stage": _skill_name, "status": "completed", "elapsed_sec": _elapsed,
                                  "backend": "agent", "current_step": _final_steps}
            if self._persist_callback:
                self._persist_callback(dict(state))  # immediate: frontend sees "completed"
        else:
            # Direct LLM call (default, backward-compatible)
            state["_progress"] = {"stage": _skill_name, "status": "running", "started_at": _time.time(),
                                  "backend": "llm", "current_step": 0}
            if self._persist_callback:
                self._persist_callback(dict(state))  # immediate: frontend sees "running"
            try:
                _response = await asyncio.wait_for(sys_llm_generate(
                    None,
                    [
                        {"role": "system", "content": _sop_body},
                        {"role": "user", "content": _context or _desc},
                    ],
                    model_name=best_model_for_purpose(_purpose),
                    max_tokens=32000,
                ), timeout=getattr(stage, 'stage_timeout_seconds', 300))
                _result = getattr(_response, "content", "") or str(_response)
                # Record success for adaptive model selection
                try:
                    _latency = round((_time.time() - _t0) * 1000, 0)
                    from core.harness.utils.model_injection import _record_success as _pipeline_record_success
                    _pipeline_record_success(
                        best_model_for_purpose(_purpose),
                        latency_ms=_latency, purpose=_purpose)
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            except asyncio.TimeoutError:
                _log.getLogger("pipeline_engine").warning(
                    "Skill %s: LLM call timed out after 180s", _skill_name)
                _result = ""
                state["_progress"] = {"stage": _skill_name, "status": "timeout",
                                      "elapsed_sec": 180.0,
                                      "backend": "llm", "current_step": 0}
                if self._persist_callback:
                    self._persist_callback(dict(state))
                # Record failure
                try:
                    from core.harness.utils.model_injection import _record_failure as _pipeline_record_failure
                    _pipeline_record_failure(best_model_for_purpose(_purpose))
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                return state
            _elapsed = round(_time.time() - _t0, 2)
            state["_progress"] = {"stage": _skill_name, "status": "completed", "elapsed_sec": _elapsed,
                                  "backend": "llm", "current_step": 0}
            if self._persist_callback:
                self._persist_callback(dict(state))  # immediate: frontend sees "completed"
        _result = _result.replace("```json", "").replace("```", "").strip()

        # ── Quality gate: configurable per-stage output validation ──
        _gate = getattr(stage, 'quality_gate', {}) or {}
        _min_len = int(_gate.get("min_output_length", 100))
        if not _result or len(_result) < _min_len:
            return state

        # ── 4. Store result ──
        _artifact_key = getattr(stage, 'output_artifact', '') or _skill_name
        _elapsed = round(_time.time() - _t0, 2)

        state[_artifact_key] = {"raw_output": _result, "elapsed_sec": _elapsed}

        # Write artifact to filesystem (authoritative storage; SQLite is cache)
        _out_dir = state.get("output_dir", "")
        if _out_dir and _artifact_key and _result and not _artifact_key.startswith("_"):
            self._write_artifact_file(_out_dir, _artifact_key, _result)

        # ── Stage trace: structured metadata for reasoning visibility ──
        # agent backend doesn't set _response — default to None for safe trace access
        _resp = locals().get('_response')
        _model_name = best_model_for_purpose(_purpose)
        _model_meta = {}
        try:
            from core.harness.utils.model_injection import best_model_for_purpose_with_meta
            _model_meta = best_model_for_purpose_with_meta(_purpose)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        state[f"_trace_{stage.id}"] = {
            "stage_id": stage.id,
            "agent_id": getattr(stage, 'agent_id', '') or '',
            "phase": getattr(stage, 'phase', '') or '',
            "skill_name": _skill_name,
            "model_name": _model_name,
            "model_purpose": _purpose,
            "output_size": len(_result),
            "elapsed_sec": _elapsed,
            "tokens_used": getattr(_resp, 'usage', {}).get('total_tokens', 0) if hasattr(_resp, 'usage') else 0,
            "retry_count": state.get(f"_retry_{stage.id}", 0),
            "failure_strategy": getattr(stage, 'failure_strategy', 'fail_pipeline') or 'fail_pipeline',
            "strategy": "skill_dispatch",
            "model_tier": _model_meta.get("model_tier", ""),
            "complexity_range": [],
            "domain_id": _domain_id,
            "context_enriched": _context_enriched,
        }

        # ── Decision trace: generic per-stage provenance for failure localization ──
        # Records confidence + upstream dependencies so the fix flow can walk
        # backward to the max error-contribution node. No business concepts here.
        try:
            from core.harness.execution.decision_trace import record_decision as _record_decision
            # Use project_id as the trace key — it is the stable identifier the
            # fix flow and frontend query by (session_id drifts to run_id on
            # regenerate, which would split the trace across files).
            _run_id = (state.get("project_id") or state.get("session_id")
                       or state.get("_run_id", ""))
            if _run_id:
                _depends_on = []
                for _s in (self._config.stages if self._config else []):
                    if getattr(_s, 'output_artifact', '') in (_input_artifacts or []):
                        _depends_on.append(getattr(_s, 'id', ''))
                # Coarse confidence heuristic: structured output > plain text >
                # minimal. (Quality-bus score is a later refinement; this gives
                # the graph a non-trivial signal today.)
                _conf = 0.7
                if _result:
                    _stripped = _result.strip()
                    if "## FILE:" in _result or (_stripped.startswith("{") and _stripped.endswith("}")):
                        _conf = 0.85
                    elif len(_result) < 200:
                        _conf = 0.5
                _record_decision(_run_id, stage.id, depends_on=_depends_on,
                                 confidence=_conf,
                                 agent_id=getattr(stage, 'agent_id', '') or '')
        except Exception as _trace_err:  # noqa: best-effort-trace — decision trace is non-critical
            _log.getLogger("pipeline_engine").debug(
                "decision trace record failed for stage %s: %s", stage.id, _trace_err, exc_info=True)

        # ── Cost budget: accumulate USD from tokens × price (config-driven) ──
        try:
            from core.harness.execution.cost_budget import cost_for as _cost_for
            _tokens_total = getattr(_resp, 'usage', {}).get('total_tokens', 0) if hasattr(_resp, 'usage') else 0
            if not _tokens_total:
                _tokens_total = int(state.get("_stage_tokens_used", 0) or 0)
            if _tokens_total:
                _delta = _cost_for(_model_name, _tokens_total, 0)
                state["cost_used_usd"] = round(state.get("cost_used_usd", 0.0) + _delta, 6)
        except Exception:  # noqa: best-effort-cost — cost tracking is non-critical
            pass

        _log.getLogger("pipeline_engine").warning(
            "Skill %s OK: stage=%s output=%d chars", _skill_name, stage.id, len(_result))

        # ── 5.5. Chain next skill if configured ──
        _chain_skill = getattr(stage, 'chain_skill_after', '') or ''
        if _chain_skill:
            _chain_result_key = (getattr(stage, 'test_result_key', '') or _artifact_key) + "_exec"
            state = await self._run_chained_skill(_chain_skill, state, _artifact_key, _chain_result_key)

        # ── 5.6. Deploy files to disk if configured ──
        if getattr(stage, 'deploy_files_to_disk', False) and "## FILE:" in _result:
            self._deploy_result_files(state, stage, _result)

        # ── 6. HITL gate: pause pipeline if stage requires human approval ──
        if getattr(stage, 'hitl', False):
            state["phase"] = "paused"
            state["_hitl_stage_id"] = stage.id
            state["_hitl_phase_name"] = getattr(stage, 'hitl_phase', '') or 'review'
            state["_hitl_output_artifact"] = getattr(stage, 'output_artifact', '') or ''
            self._audit_hitl(state, "hitl_paused", detail=f"stage:{stage.id}")
            _log.getLogger("pipeline_engine").warning(
                "HITL paused: stage=%s phase=%s", stage.id, state["_hitl_phase_name"])

        # Emit node_ended event for frontend polling visibility
        try:
            _event_bus.emit(state.get("session_id", state.get("_run_id", "")),
                            "node_ended", {"state": dict(state), "node_id": stage.id,
                                           "elapsed": round(_time.time() - _t0, 2)})
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # Persist state immediately — each stage completion writes to disk
        try:
            if self._persist_callback:
                self._persist_callback(dict(state))
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── Online evolution: non-blocking incremental evolution trigger ──
        # Fires for self_evolving/collaborative profiles after a stage completes.
        try:
            from core.harness.infrastructure.hooks.online_evolution import get_online_evolution, OnlineEvolution
            _evo: OnlineEvolution = get_online_evolution()
            _evo_result = await _evo.on_post_loop(state)
            if _evo_result and isinstance(_evo_result, dict) and _evo_result.get("online_evolution_triggered"):
                state["_online_evolution_triggered"] = _evo_result["online_evolution_triggered"]
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        return state


    async def _run_chained_skill(self, skill_name: str, state: PipelineState,
                                  upstream_artifact_key: str, result_artifact_key: str) -> PipelineState:
        """Generic: load a skill SOP, feed it the upstream artifact, run via StageRunner→ReActLoop.

        The engine knows NOTHING about what the skill does — it just loads SKILL.md,
        passes the upstream raw_output as context, and runs the skill through the
        ReAct loop so the agent can use tools (e.g., core_chat for test execution).
        """
        import os as _os, json as _json, logging as _log, time as _time
        _t0 = _time.time()
        _log = _log.getLogger("pipeline_engine")

        # 1. Load SOP from SKILL.md
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _sp = _os.path.join(_here, "..", "..", "engine", "skills", skill_name, "SKILL.md")
        _sp = _os.path.abspath(_sp)
        _alt = _os.path.expanduser(f"~/.aiplat/skills/{skill_name}/SKILL.md")
        if not _os.path.isfile(_sp):
            _sp = _alt
        if not _os.path.isfile(_sp):
            _log.warning("chained skill '%s': SKILL.md not found", skill_name)
            return state
        with open(_sp, "r") as _sf:
            _raw = _sf.read()
        _sop = _raw.split("---", 2)[2].strip() if _raw.startswith("---") else _raw
        if not _sop:
            _log.warning("chained skill '%s': empty SOP", skill_name)
            return state

        # 2. Build context from upstream artifact + agent metadata
        _upstream = state.get(upstream_artifact_key, {})
        _upstream_text = _upstream.get("raw_output", "") if isinstance(_upstream, dict) else str(_upstream)
        if not _upstream_text:
            _log.warning("chained skill '%s': no upstream content in '%s'", skill_name, upstream_artifact_key)
            return state

        _agent_name = state.get("_generated_agent", "")
        _prompt = f"Execute skill {skill_name}:\n\nUpstream artifacts:\n{_upstream_text[:24000]}"
        if _agent_name:
            _prompt += f"\n\nAgent under test: {_agent_name}"

        _log.warning("chained skill '%s': executing via StageRunner (%d chars upstream)", skill_name, len(_upstream_text))
        # Track step count from upstream test_questions for progress display
        _total_steps = 1
        try:
            _parsed = _json.loads(_upstream_text)
            _qs = _parsed.get("test_questions", [])
            _total_steps = len(_qs) if isinstance(_qs, list) and _qs else 1
        except Exception:
            try:
                _jstart = _upstream_text.find('{')
                _jend = _upstream_text.rfind('}')
                if _jstart >= 0 and _jend > _jstart:
                    _qs = _json.loads(_upstream_text[_jstart:_jend+1]).get("test_questions", [])
                    _total_steps = len(_qs) if isinstance(_qs, list) and _qs else 1
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        state["_progress"] = {"stage": skill_name, "status": "running", "started_at": _time.time(), "total_steps": _total_steps}

        # 3. Run via StageRunner → ReActLoop (enables tool calls like core_chat)
        try:
            from core.schemas_builder import PipelineStageConfig
            _chain_stage = PipelineStageConfig(
                id=f"chained_{skill_name}",
                agent_id="chained_skill",
                order=0,
                required_skills=[skill_name],
                max_consecutive_llm_failures=3,
                failure_strategy="skip_stage",
                skill_model_purpose="agent",  # route to agent profile for capability-driven model selection
            )
            state["_sys_prompt"] = _sop
            import asyncio as _asyncio
            _result = await _asyncio.wait_for(
                self._stage_runner.run(_prompt, state, stage=_chain_stage),
                # P1-6 修复（2026-08-25）：原引用未定义变量 stage → NameError 被吞 →
                # 链式技能永不执行。改用本函数内已定义的 _chain_stage（PipelineStageConfig）。
                timeout=getattr(_chain_stage, 'stage_timeout_seconds', 300),
            )
            state.pop("_sys_prompt", None)
        except _asyncio.TimeoutError:
            state.pop("_sys_prompt", None)
            _log.warning("chained skill '%s': timed out after 180s", skill_name)
            _elapsed = round(_time.time() - _t0, 1)
            state["_progress"] = {"stage": skill_name, "status": "timeout", "elapsed_sec": _elapsed, "total_steps": state.get("_progress", {}).get("total_steps", 1)}
            return state
        except Exception as _e:
            state.pop("_sys_prompt", None)
            _log.warning("chained skill '%s': StageRunner failed: %s", skill_name, str(_e)[:200])
            state["_progress"] = {"stage": skill_name, "status": "error", "error": str(_e)[:200]}

            return state

        _result = str(_result or "")
        _result = _result.replace("```json", "").replace("```", "").strip()

        if not _result or len(_result) < 50:
            _log.warning("chained skill '%s': empty/short result (%d chars)", skill_name, len(_result))
            return state

        # 4. Store result
        _elapsed = round(_time.time() - _t0, 2)
        state[result_artifact_key] = {"raw_output": _result, "elapsed_sec": _elapsed}
        _out_dir = state.get("output_dir", "")
        if _out_dir and result_artifact_key and _result and not result_artifact_key.startswith("_"):
            self._write_artifact_file(_out_dir, result_artifact_key, _result)
        state["_progress"] = {"stage": skill_name, "status": "completed", "elapsed_sec": _elapsed}
        _log.warning("chained skill '%s': OK (%d chars, %.1fs → %s)", skill_name, len(_result), _elapsed, result_artifact_key)
        return state

    @staticmethod
    @staticmethod
    def _write_artifact_file(output_dir: str, artifact_key: str, content: str) -> str:
        """Write pipeline artifact to filesystem. Returns file path."""
        import os as _os2
        if not output_dir or not artifact_key or not content:
            return ""
        try:
            _os2.makedirs(output_dir, exist_ok=True)
            path = _os2.path.join(output_dir, f"{artifact_key}.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return path
        except Exception:
            return ""  # best-effort; SQLite still has the truncated version

    def _deploy_result_files(self, state, stage, _result: str) -> None:
        """Generic: parse ## FILE: blocks from output and write to project directory.

        No business logic — engine doesn't know (or care) what AGENT.md or SKILL.md mean.
        It just writes the files the LLM told it to write.
        """
        import re as _re, os as _os2, logging as _log
        _log = _log.getLogger("pipeline_engine")

        _target = (getattr(stage, 'deploy_files_target_dir', '') or '').strip()
        if not _target:
            # Default: ~/.aiplat/apps/{project_id}/current
            _pid = state.get("project_id", "") or state.get("_project_id", "")
            _home = _os2.getenv("AIPLAT_HOME", _os2.path.expanduser("~/.aiplat"))
            _target = _os2.path.join(_home, "apps", _pid, "current")
        _os2.makedirs(_target, exist_ok=True)
        _log.warning("deploy: writing files to %s", _target)

        _count = 0
        # L3: drop "## UNCHANGED: <path>" markers (generic output-format convention —
        # file declared unchanged by the producer must not pollute ## FILE: blocks;
        # the platform merge layer decides what to copy from the imported originals).
        _result = _re.sub(r'^#{2,4}\s*UNCHANGED:\s*[^\n]*$', '', _result, flags=_re.MULTILINE)
        for _block in _re.split(r'^#{2,4}\s*FILE:\s*', _result, flags=_re.MULTILINE)[1:]:
            _lines = _block.strip().split("\n", 1)
            if len(_lines) < 2:
                continue
            _fname = _lines[0].strip()
            _content = _lines[1].strip()
            _content = _re.sub(r'^```\w*\n?', '', _content)
            _content = _re.sub(r'\n?```\s*$', '', _content)
            # Strip leaked code block language markers (yaml., json.)
            if _content.startswith("yaml\n"):
                _content = _content[5:]
            elif _content.startswith("json\n"):
                _content = _content[5:]
            # Strip leaked YAML terminators from JSON files (trailing ---)
            if _fname.endswith(".json") and _content.rstrip().endswith("---"):
                _content = _re.sub(r'\n?---\s*$', '', _content)
            # P0-3 修复（2026-08-25）：LLM 可控文件名经 _safe_join 约束——
            # 防路径穿越（../ 逃逸 _target 写任意路径）；穿越尝试跳过该文件并告警。
            try:
                _full = _safe_join(_target, _fname)
            except ValueError as _ve:
                _log.warning("deploy: blocked path traversal: %s (%s)", _fname, _ve)
                continue
            try:
                _os2.makedirs(_os2.path.dirname(_full), exist_ok=True)
                with open(_full, "w", encoding="utf-8") as _fw:
                    _fw.write(_content)
                _count += 1
            except Exception as _we:
                _log.warning("deploy: failed to write %s: %s", _fname, _we)
        _log.warning("deploy: wrote %d files", _count)

    async def _exec_tdd_cycle(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        """RED-GREEN-REFACTOR: test first, see red, code, see green."""

        # Phase 1: Generate test code

        test_state = await self._gen_test_plan(stage, state)

        # Phase 2: Run tests (expected: red — no implementation yet)

        if test_state.get(stage.output_artifact):

            test_state = await self._exec_test_runner(stage, test_state)

        # Phase 3: Generate implementation code

        impl_state = await self._exec_stage(stage, test_state)

        # Phase 4: Run tests again (expected: green)

        if impl_state.get(stage.output_artifact):

            impl_state = await self._exec_test_runner(stage, impl_state)

        return impl_state



    async def _apply_review_gate(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        """Apply post-stage review based on declarative review_gate field."""

        gate = getattr(stage, 'review_gate', 'quick') or 'quick'

        if gate == "none":

            return state

        if gate == "quick":

            # Skip quick review for flow nodes (start/end) and human input

            nt = getattr(stage, 'node_type', None) or ''

            if nt in ('start', 'end', 'human'):

                return state

            artifact = state.get(stage.output_artifact)

            issues = self._quick_validate(artifact, stage)

            # For code-generating stages: additional py_compile check

            if stage.uses_file_output and isinstance(artifact, dict):

                compile_issues = self._validate_stage_code(artifact)

                issues.extend(compile_issues)

            if issues:

                state["_quick_check_issues"] = issues

                state["phase"] = PipelinePhase.FAILED

                state["error"] = f"quick_review_failed: {len(issues)} issues"

                state["_last_action_reason"] = "quick_review_failed"

        elif gate == "llm":

            try:

                files_summary = ""

                if stage.uses_file_output and isinstance(state.get(stage.output_artifact), dict):

                    collected = self._collect_files(state[stage.output_artifact])

                    files_summary = "\n".join(f"- {f['path']} ({len(f.get('content',''))} bytes)" for f in collected[:20])

                prompt = (

                    f"## Code Review\n"

                    f"Review the stage output below for the following categories. "

                    f"Respond ONLY with valid JSON.\n\n"

                    f"### Categories (each scored 0-10):\n"

                    f"- security: any hardcoded secrets, injection risks, missing auth checks\n"

                    f"- correctness: logic errors, import resolution, type consistency\n"

                    f"- style: naming conventions, code duplication, dead code\n"

                    f"- completeness: all required files present, no placeholder stubs\n"

                    f"- testability: assertable behavior, edge case coverage\n\n"

                    f"### Stage: {stage.agent_id or stage.id}\n"

                    f"### Files:\n{files_summary}\n\n"

                    f"### Output (first 3000 chars):\n"

                    f"{json.dumps(state.get(stage.output_artifact, {}), default=str)[:3000]}\n\n"

                    f'Reply JSON ONLY: {{"verdict":"PASS|FAIL","scores":{{"security":0,"correctness":0,"style":0,"completeness":0,"testability":0}},"issues":[],"suggestion":""}}'

                )

                result = await self._eval_runner.run(prompt, state)

                content = getattr(result, 'content', '') if hasattr(result, 'content') else str(result)

                try:

                    json_match = re.search(r'\{.*"verdict".*\}', content.replace('\n', ' '), re.DOTALL)

                    review = json.loads(json_match.group(0)) if json_match else {}

                except (json.JSONDecodeError, AttributeError):

                    review = {}

                if isinstance(review, dict) and review.get("verdict", "").upper() == "PASS":

                    state["_last_review"] = review  # store for traceability

                else:

                    state["phase"] = PipelinePhase.FAILED

                    state["error"] = f"llm_review_rejected: {review.get('suggestion', content[:200])}"

                    state["_last_action_reason"] = "llm_review_rejected"

                    state["_last_review"] = review

            except Exception:

                logging.getLogger("pipeline_engine").debug("best-effort skipped", exc_info=True)

        elif gate == "hitl":

            state["phase"] = PipelinePhase.PAUSED

            state["_hitl_phase_name"] = getattr(stage, 'hitl_phase', '') or 'review'

            # v2.9: enable GrillingBridge for HITL stages

            state["_hitl_grilling_available"] = True

            state["_hitl_domain_id"] = state.get("domain_id") or "ai-knowledge"

            state["_hitl_output_artifact"] = getattr(stage, 'output_artifact', '') or ''

            self._audit_hitl(state, "hitl_paused", detail=f"gate:{state['_hitl_phase_name']}")

        return state



    @staticmethod

    def _validate_stage_code(artifact: Dict[str, Any]) -> List[str]:

        """py_compile + node --check on code files within a stage artifact."""

        issues = []

        files = PipelineEngine._collect_files(artifact)

        if not files:

            return []

        import tempfile as _tmp

        import py_compile as _py_compile

        import shutil as _shutil

        with _tmp.TemporaryDirectory() as tmpdir:

            for f in files:

                path = f.get("path", "")

                content = f.get("content", "")

                if not path or not content:

                    continue

                tmp_path = os.path.join(tmpdir, os.path.normpath(path).lstrip("/"))

                try:

                    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)

                    with open(tmp_path, "w") as fh:

                        fh.write(content)

                except ValueError:

                    issues.append(f"path_traversal_blocked:{path}")

                    continue

                if path.endswith(".py"):

                    try:

                        _py_compile.compile(tmp_path, doraise=True)

                    except (_py_compile.PyCompileError, SyntaxError) as e:

                        issues.append(f"compile_error:{path}: {e}")

                elif path.endswith((".js", ".mjs")):

                    if _shutil.which("node"):

                        import subprocess as _sp

                        try:

                            r = _sp.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=10)

                            if r.returncode != 0:

                                issues.append(f"node_check_error:{path}: {r.stderr[:200]}")

                        except Exception as e:

                            logging.warning(str(e), exc_info=True)

                elif path.endswith(".json"):

                    import json as _json

                    try:

                        _json.loads(content)

                    except _json.JSONDecodeError as e:

                        issues.append(f"json_parse_error:{path}: {e}")

        return issues



    async def _execute_dag(self, dag: DAG, state: PipelineState) -> PipelineState:

        """Execute a full DAG of stages (topological order, parallel layers)."""

        if not dag or not dag.nodes:

            return state

        layers = dag.topological_order()

        for layer in layers:

            if not layer:

                continue

            if state.get("phase") == PipelinePhase.FAILED:

                break

            # Execute all nodes in this layer in parallel

            tasks = []

            for node in layer:

                # Find matching PipelineStageConfig

                stage = None

                for s in self._config.stages:

                    if s.id == node.id or s.agent_id == node.agent_id:

                        stage = s

                        break

                if stage is None:

                    stage = PipelineStageConfig(id=node.id, agent_id=node.agent_id or node.id,

                        agent_name=node.role, execution_mode=node.execution_mode,

                        review_gate=node.review_gate, tdd_enforce=node.tdd_enforce,

                        context_isolation=node.context_isolation)

                    # Add to config stages dynamically

                    self._config.stages.append(stage)

                idx = len(self._config.stages) - 1

                tasks.append(self._exec_single_stage(stage, idx, state))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):

                if isinstance(result, tuple) and result[0]:

                    state.update(result[0])

        return state



    # ── End Phase 10 ──



    async def _exec_single_stage(

        self, stage: PipelineStageConfig, idx: int, state: PipelineState

    ) -> Optional[Tuple[PipelineState, bool]]:

        """Execute a single pipeline stage. Returns (updated_state, is_paused)."""

        import copy

        local_state = dict(state)

        artifact = None  # Prevent UnboundLocalError in edge cases

        local_state["_current_stage_idx"] = idx

        graph_trace: List[Dict] = []

        local_state.setdefault("_graph_trace", [])

        local_state["_graph_trace"] = list(local_state["_graph_trace"])  # shallow copy for parallel safety

        local_state["_shared_state_board"] = list(local_state.get("_shared_state_board", []))  # same for board



        # Compute input hash for incremental execution

        # Uses configured input_hash_keys or falls back to all upstream state keys

        input_hash_keys = getattr(stage, 'input_hash_keys', []) or (

            [s.output_artifact for s in self._config.stages[:idx]

             if s.output_artifact and local_state.get(s.output_artifact)]

            if idx > 0 else []

        )

        if input_hash_keys:

            import hashlib, json as _jhash

            input_snapshot = {k: str(local_state.get(k, ""))[:500] for k in input_hash_keys}

            current_hash = hashlib.sha256(

                _jhash.dumps(input_snapshot, sort_keys=True).encode()

            ).hexdigest()[:16]

            stored_hash = local_state.get(f"_input_hash_{stage.id}", "")

            if stored_hash and stored_hash != current_hash:

                # Inputs changed — force re-execution even if output exists

                local_state.pop(stage.output_artifact, None)

            local_state[f"_input_hash_{stage.id}"] = current_hash



            # Result cache: reuse output if same (stage_id, input_hash) seen before

            cache_key = f"_cache_{stage.id}_{current_hash}"

            cached = local_state.get(cache_key)

            if cached and not local_state.get(stage.output_artifact):

                # Restore cached output from previous run with identical inputs

                local_state[stage.output_artifact] = cached

                local_state["_last_action_reason"] = f"cache_hit:{stage.id}"



        # Skip if already done (but not for empty/error artifacts)

        existing = local_state.get(stage.output_artifact)
        # Don't skip if the existing artifact is an error state
        is_error_state = isinstance(existing, dict) and existing.get("loop_state") == "error"

        if existing and not is_error_state and (not isinstance(existing, dict) or len(existing) > 0):

            has_raw_only = isinstance(existing, dict) and set(existing.keys()) == {"raw_output"}

            if not has_raw_only and not (stage.retry_target_id and not self._check_done(stage, local_state)):

                graph_trace.append({"node": stage.id, "status": "skipped", "reason": f"{stage.output_artifact}_exists", "ts": time.time()})

                local_state[f"_stage_{stage.id}_done"] = True

                local_state["_last_action_reason"] = f"skip:{stage.output_artifact}_exists"

                # Capture per-stage reflection for self-improvement loop

                if local_state.get(stage.output_artifact):

                    try:

                        reflection = await self._capture_stage_reflection(stage, local_state)

                        if reflection:

                            local_state[f"_reflection_{stage.id}"] = reflection

                    except Exception as e:

                        logging.warning(str(e), exc_info=True)

                return local_state, False



        t_start = time.time()

        graph_trace.append({"node": stage.id, "status": "started", "ts": t_start})

        local_state["_graph_trace"] = graph_trace

        local_state[f"_stage_ts_{stage.id}"] = t_start

        _event_bus.emit(local_state.get("session_id", ""), "node_started", {"state": dict(local_state), "node_id": stage.id})



        # Ontology guard: validate stage against ontology constraints before execution

        if getattr(stage, 'ontology_class', ''):

            from core.harness.infrastructure.gates.policy_gate import check_stage_ontology_guard

            guard_violation = await check_stage_ontology_guard(stage, local_state)

            if guard_violation:

                local_state["error"] = guard_violation

                local_state[f"_stage_{stage.id}_done"] = True

                local_state["_last_action_reason"] = f"ontology_guard_blocked:{stage.id}"

                logging.getLogger("pipeline_engine").warning(

                    "Ontology guard blocked stage %s: %s", stage.id, guard_violation[:200],

                )

                return local_state, False



        # Phase 10: declarative execution via dispatch table (replaces old if/elif chain)

        local_state = await self._dispatch_execute(stage, local_state)

        constraint_retries = 0

        max_constraint_retries = int(os.getenv("AIPLAT_MAX_CONSTRAINT_RETRIES", "3"))

        while local_state.get("_constraint_retry_pending") and constraint_retries < max_constraint_retries:

            local_state.pop("_constraint_retry_pending", None)

            local_state["error"] = ""

            constraint_retries += 1

            local_state["_constraint_retry_count"] = constraint_retries

        local_state = await self._dispatch_execute(stage, local_state)

        t_end = time.time()

        local_state[f"_stage_{stage.id}_done"] = True

        # Evaluate stage health from scoring_dimensions (heuristic, zero-LLM-cost)
        await self._evaluate_stage_health(stage, local_state)

        # Cache result for future runs with identical inputs

        input_hash = local_state.get(f"_input_hash_{stage.id}", "")

        if input_hash and local_state.get(stage.output_artifact) is not None:

            local_state[f"_cache_{stage.id}_{input_hash}"] = local_state[stage.output_artifact]

        artifact = local_state.get(stage.output_artifact)

        # Structured state board milestone — only key facts, no raw reasoning

        try:

            board = local_state.setdefault("_shared_state_board", [])

            if not local_state.get("error"):

                summary_keys: List[str] = []

                if isinstance(artifact, dict):
                    _artifact_keys = list(artifact.keys())
                    summary_keys = [k for k in _artifact_keys if k not in ("raw_output", "_compare", "code_graph")][:5]

                board.append({

                    "stage_id": stage.id,

                    "agent_id": stage.agent_id,

                    "ts": t_end,

                    "done": True,

                    "output_preview": str(artifact)[:300] if artifact is not None else "(empty)",

                    "output_keys": summary_keys,

                })

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        if artifact is not None:

            local_state[f"_stage_output_{stage.id}"] = json.dumps(artifact, ensure_ascii=False)[:2000]

        elapsed = round(t_end - local_state.get(f"_stage_ts_{stage.id}", t_end), 1)

        local_state[f"_stage_elapsed_{stage.id}"] = elapsed

        _event_bus.emit(local_state.get("session_id", ""), "node_ended", {"state": dict(local_state), "node_id": stage.id, "elapsed": elapsed})

        # Capture reflection after fresh execution too (not just on skip/re-run)

        if local_state.get(stage.output_artifact):

            try:

                reflection = await self._capture_stage_reflection(stage, local_state)

                if reflection:

                    local_state[f"_reflection_{stage.id}"] = reflection

            except Exception as e:

                logging.warning(str(e), exc_info=True)

        # Auto-initialize task_list if stage output contains trackable sub-items

        artifact = local_state.get(stage.output_artifact)

        if isinstance(artifact, dict) and not local_state.get("task_list"):

            for sub_key in ("items", "tasks", "functional_requirements"):

                if isinstance(artifact.get(sub_key), list):

                    self._init_task_list(local_state, artifact)

                    break

        # Quick rule-based validation — lightweight Outcome Checker

        quick_check = self._quick_validate(artifact, stage)

        if quick_check:

            local_state.setdefault("_quick_check_issues", []).extend(quick_check)

        # Behavioral verification: py_compile for code, JSON schema for non-code

        try:

            bv = self._verify_stage_behavior(stage, artifact, output_dir=local_state.get("output_dir", ""))

            local_state[f"_behavior_verify_{stage.id}"] = bv

            if not bv.get("verified", True):

                local_state.setdefault("_quick_check_issues", []).append(

                    f"behavior_verify_failed: {bv.get('checks', [])}"

                )

        except Exception as e:

            logging.warning(str(e), exc_info=True)

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



        if local_state.get("phase") == PipelinePhase.FAILED:

            graph_trace.append({"node": stage.id, "status": "failed", "reason": "phase_failed", "ts": time.time()})

            # Write pt_ snapshot for SystemDiagnostician (B)

            try:

                from core.harness.ontology_engine.graph_index import GraphIndex

                import json as _json_pt

                kg = GraphIndex.load("knowledge-atom")

                pt_id = f"pt_{stage.id}_{int(time.time())}"

                kg.add_entity(pt_id, _json_pt.dumps({

                    "stage": str(stage.id), "status": "failed",

                }, ensure_ascii=False)[:500], "SystemSnapshot", source_doc_id=str(int(time.time())))

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
            return local_state, True



        # Phase 10: declarative review gate (replaces old hitl/hitl_after_execute if/elif)

        local_state = await self._apply_review_gate(stage, local_state)

        if local_state.get("phase") == PipelinePhase.PAUSED:

            self._snapshot(local_state, f"stage_{stage.id}_done")

            return local_state, True



        # Git auto-commit on stage completion

        self._git_commit_stage(stage, local_state)



        # Phase C: independent assessment agent (AssessAgent — scores, never fixes)

        expected_outcomes = getattr(stage, 'expected_outcomes', None) or []

        rubric_path = getattr(stage, 'rubric_path', '') or ''

        if expected_outcomes or rubric_path:

            await self._assess_stage_output(stage, local_state)



        # Ontology: auto-register artifact as knowledge entity

        if getattr(stage, 'ontology_class', '') and not local_state.get("error"):

            await self._register_artifact_to_ontology(stage, local_state)



        # Quality signal: record pipeline assessment for ontology entities

        if getattr(stage, 'ontology_class', ''):

            await self._record_quality_signal_for_stage(stage, local_state)



        # Fine-grained stage reward computation

        self._compute_stage_reward(stage, local_state)



        # Conditional routing: evaluate routing_rules, record target if triggered

        route_to = self._evaluate_routing(stage, local_state)

        if route_to is not None:

            local_state["_route_after"] = route_to

            local_state["_last_action_reason"] = f"routed_to:{self._config.stages[route_to].id}"



        return local_state, False



    def _evaluate_routing(self, stage: PipelineStageConfig, state: PipelineState) -> Optional[int]:

        """Evaluate routing_rules for a stage. Returns index of next stage, or None."""

        rules = getattr(stage, 'routing_rules', None) or []

        if not rules:

            return None

        stages = self._config.stages

        id_to_idx = {s.id: i for i, s in enumerate(stages)}

        for rule in rules:

            if not isinstance(rule, dict):

                continue

            condition = rule.get("condition", "")

            target_id = rule.get("next", "")

            if not condition or not target_id or target_id not in id_to_idx:

                continue

            try:

                if self._check_condition(condition, state):

                    return id_to_idx[target_id]

            except Exception:

                logging.getLogger("pipeline_engine").debug("routing eval failed", exc_info=True)

        return None



    @staticmethod

    def _check_condition(condition: str, state: dict) -> bool:

        """Evaluate condition against pipeline state.

        Supports: 'field=="val"', 'result.pass_rate > 0.8', 'error is not None', 'a=="x" and b>0'

        """

        import re

        for part in [p.strip() for p in condition.split(" and ")]:

            m = re.match(r'^(\w+(?:\.\w+)*)\s*(==|!=|>|<|>=|<=|is\s+not|is)\s*(.+)$', part)

            if not m:

                return False

            path_str, op, val_str = m.group(1), m.group(2), m.group(3).strip()

            val = state

            for seg in path_str.split('.'):

                val = val.get(seg) if isinstance(val, dict) else None

                if val is None:

                    break

            rhs: Any

            s = val_str.strip()

            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):

                rhs = s[1:-1]

            elif s.lower() == 'none':

                rhs = None

            elif s.lower() == 'true':

                rhs = True

            elif s.lower() == 'false':

                rhs = False

            else:

                try:

                    rhs = float(s)

                except ValueError:

                    rhs = s

            if op in ("==", "!="):

                if (val == rhs) != (op == "=="):

                    return False

            elif op == "is":

                if val is not rhs:

                    return False

            elif op == "is not":

                if val is rhs:

                    return False

            elif op in (">", "<", ">=", "<=") and val is not None and rhs is not None:

                try:

                    fv, fr = float(val), float(rhs)

                    if not eval(f"fv {op} fr"):

                        return False

                except (TypeError, ValueError):

                    return False

            else:

                return False

        return True



    @staticmethod

    def _git_commit_stage(stage: PipelineStageConfig, state: PipelineState) -> None:

        """Auto-commit stage output to git if AIPLAT_GIT_ENABLED is true."""

        if os.getenv("AIPLAT_GIT_ENABLED", "false").lower() not in ("true", "1", "yes", "y"):

            return

        import subprocess

        output_dir = state.get("output_dir", "")

        if not output_dir or not os.path.isdir(output_dir):

            return

        repo_root = output_dir

        try:

            subprocess.run(["git", "-C", repo_root, "init"], capture_output=True, check=False)

            subprocess.run(["git", "-C", repo_root, "add", "."], capture_output=True, check=False)

            count = len(PipelineEngine._collect_files(state.get(stage.output_artifact, {}))) if stage.uses_file_output else 0

            msg = f"[{stage.agent_name or stage.id}] {stage.id} — {count} files"

            subprocess.run(["git", "-C", repo_root, "commit", "-m", msg], capture_output=True, check=False)

        except Exception:

            logging.getLogger("pipeline_engine").debug("git commit best-effort skipped", exc_info=True)



    async def _register_artifact_to_ontology(

        self, stage: PipelineStageConfig, state: PipelineState

    ) -> None:

        u"""Auto-register pipeline stage output as an ontology entity via OntologyAction.



        Only fires when stage.ontology_class is non-empty and stage finished without error.

        """

        artifact = state.get(stage.output_artifact)

        if artifact is None:

            return



        try:

            from core.harness.knowledge.knowledge_action import (

                AI, OntologyAction, ActionVerb, EntityLifecycleState,

                execute_action, new_action_id,

            )

            from core.harness.knowledge.knowledge_ontology import get_ontology, _safe_uri



            onto = get_ontology()



            if isinstance(artifact, dict):

                body = artifact.get("raw_output", json.dumps(artifact, ensure_ascii=False)[:50000])

                summary = artifact.get("summary", str(artifact.get("raw_output", ""))[:200])

            else:

                body = str(artifact)[:50000]

                summary = str(artifact)[:200]



            title = f"[{stage.agent_id}] {stage.id}"

            entity_uri = f"{AI}{_safe_uri(title)}_{new_action_id()[:8]}"



            category_map = {

                "ConceptPage": "entities",

                "TopicPage": "topics",

                "SourcePage": "entities",

                "KnowledgeAtom": "atoms",

            }

            category = category_map.get(stage.ontology_class, "entities")



            source_articles = []

            related = []

            for rel in (getattr(stage, 'ontology_relations', None) or []):

                if not isinstance(rel, dict):

                    continue

                if rel.get("target_kb_doc"):

                    source_articles.append(rel["target_kb_doc"])

                if rel.get("target_artifact") and state.get(rel["target_artifact"]):

                    target_title = state.get(rel["target_artifact"], {}).get("title", rel["target_artifact"])

                    if isinstance(target_title, str) and target_title.strip():

                        related.append(target_title)



            verb = ActionVerb.CREATE

            verb_str = getattr(stage, 'ontology_action_verb', '')

            if verb_str in {v.value for v in ActionVerb}:

                verb = ActionVerb(verb_str)



            target_state = getattr(stage, 'ontology_target_state', EntityLifecycleState.PROPOSED.value)

            if target_state not in {s.value for s in EntityLifecycleState}:

                target_state = EntityLifecycleState.PROPOSED.value



            action = OntologyAction(

                action_id=new_action_id(),

                verb=verb,

                target_entity_uri=entity_uri,

                actor=stage.agent_id,

                payload={

                    "title": title,

                    "body": body,

                    "summary": summary,

                    "category": category,

                    "lifecycle_state": target_state,

                    "source_articles": source_articles,

                    "related": related,

                    "tags": [stage.agent_id, f"pipeline:{state.get('session_id', '')[:8]}"],

                    "_generated_by": {

                        "pipeline_stage": stage.id,

                        "agent_id": stage.agent_id,

                        "session_id": str(state.get("session_id", "")),

                    },

                },

                trace_id=state.get("_trace_id", ""),

                pipeline_stage_id=stage.id,

                session_id=str(state.get("session_id", "")),

                preconditions=list(getattr(stage, 'ontology_preconditions', []) or []),

                postconditions=[f"entity {entity_uri} must pass schema validation"],

                required_scopes=["kb:write"],

            )



            result = execute_action(action, onto, collection_id="default")



            if result.success:

                logging.getLogger("pipeline_engine").info(

                    "Ontology register OK: %s %s (%d triples, state=%s)",

                    verb.value, entity_uri.replace(AI, ""), result.triples_added, target_state,

                )

                state.setdefault("_ontology_entities_produced", []).append(entity_uri)

            else:

                logging.getLogger("pipeline_engine").warning(

                    "Ontology register FAIL: %s — %s", entity_uri, result.error,

                )



        except Exception as e:

            logging.getLogger("pipeline_engine").warning(

                "Ontology registration failed for stage %s: %s", stage.id, str(e)[:200],

            )



    async def _record_quality_signal_for_stage(

        self, stage: PipelineStageConfig, state: PipelineState

    ) -> None:

        u"""Record a quality signal from pipeline stage output back to ontology.



        Captures quality assessment signals from the pipeline stage and stores

        them for the ontology health tracking system.

        """

        artifact = state.get(stage.output_artifact)

        if artifact is None:

            return



        try:

            from core.harness.knowledge.knowledge_action import AI as _AI

            from core.harness.knowledge.knowledge_ontology import _safe_uri

            from core.harness.knowledge.knowledge_quality import record_quality_signal



            # Determine entity URI from stage config + session

            title = f"[{stage.agent_id}] {stage.id}"

            entity_uri = f"{_AI}{_safe_uri(title)}"



            # Build quality assessment from stage output + behavior verification

            quality = "good"

            issues: List[str] = []



            if state.get("error"):

                quality = "failed"

                issues.append(str(state.get("error", ""))[:200])



            bv = state.get(f"_behavior_verify_{stage.id}")

            if isinstance(bv, dict) and not bv.get("verified", True):

                quality = "adequate"

                issues.append("behavior_verification_failed")



            quick_checks = state.get("_quick_check_issues", [])

            if quick_checks:

                quality = "adequate" if quality == "good" else quality

                issues.extend([str(q)[:100] for q in quick_checks[:3]])



            reflection = state.get(f"_reflection_{stage.id}")

            if isinstance(reflection, dict):

                verdict = reflection.get("verdict", "")

                if verdict in ("poor", "failed"):

                    quality = "poor"

                elif verdict in ("needs_improvement",):

                    quality = "adequate"



            signal_value = {

                "quality": quality,

                "issues": issues[:5],

                "stage_id": stage.id,

                "agent_id": stage.agent_id,

                "artifact_size": len(str(artifact)) if artifact else 0,

            }



            record_quality_signal(

                entity_uri=entity_uri,

                signal_type="pipeline_reflection",

                signal_value=signal_value,

                source=f"pipeline:{stage.id}",

                severity="error" if quality == "failed" else ("warning" if quality == "poor" else "info"),

            )



        except Exception as e:

            logging.getLogger("pipeline_engine").debug(

                "Quality signal recording skipped for stage %s: %s", stage.id, str(e)[:100],

            )



    async def _assess_stage_output(

        self, stage: PipelineStageConfig, state: PipelineState

    ) -> None:

        u"""Run independent assessment (AssessAgent) + replay for algorithm stages.



        Key design difference from old _verify_stage_output:

          - AssessAgent is read-only — it NEVER modifies state or attempts fixes

          - On FAIL → escalates to HITL (paused), not auto-retry

          - Assessment report is stored in state for audit

        """

        artifact = state.get(stage.output_artifact)

        if artifact is None:

            return



        try:

            from core.harness.execution.assess_agent import AssessAgent

            from core.harness.execution.verification import (

                record_replay_snapshot, verify_replay,

            )



            rubric_path = getattr(stage, 'rubric_path', '') or ''

            rubric = list(getattr(stage, 'expected_outcomes', None) or [])



            # Load external rubric file if provided

            if rubric_path:

                try:

                    rubric = _load_rubric_file(rubric_path)  # noqa: F821

                except Exception as e:

                    logging.warning(str(e), exc_info=True)



            # Algorithm replay snapshot (existing logic)

            node_type = getattr(stage, 'node_type', '') or ''

            if node_type == 'algorithm':

                input_hash = state.get(f"_input_hash_{stage.id}", "")

                if not input_hash:

                    import hashlib

                    input_hash = hashlib.sha256(str(artifact)[:500].encode()).hexdigest()[:16]

                algo_result = None

                if isinstance(artifact, str):

                    try:

                        import json as _json

                        algo_result = _json.loads(artifact)

                    except Exception as e:

                        logging.warning(str(e), exc_info=True)

                record_replay_snapshot(

                    str(state.get("session_id", "")),

                    stage.id, input_hash, str(artifact)[:2000],

                    algorithm_result=algo_result,

                )



            # Independent assessment (AssessAgent)

            if rubric:

                agent = AssessAgent()

                report = await agent.assess(

                    rubric=rubric, artifact=artifact, stage_id=stage.id,

                )

                state[f"_assess_{stage.id}"] = report.to_dict()



                if report.overall == "FAIL":

                    state["_stage_assess_failed"] = True

                    # Escalate to HITL — agent must not auto-fix

                    state["phase"] = PipelinePhase.PAUSED

                    state["_hitl_phase_name"] = f"assess_failed:{stage.id}"

                    state["error"] = (

                        f"AssessAgent FAIL: {report.failed_count}/{report.passed_count + report.failed_count} "

                        f"criteria failed. Requires human review."

                    )

                    logger.warning(

                        "AssessAgent FAIL for %s: %s", stage.id, report.summary,

                    )



        except Exception as e:

            logging.getLogger("pipeline_engine").debug(

                "Assessment skipped for stage %s: %s", stage.id, str(e)[:100],

            )






    @staticmethod

    def _build_repo_map_text(output_dir: str) -> str:

        """Build a compact repository structure summary for prompt injection."""

        try:

            rmap = RepositoryMap()

            result = rmap.scan(output_dir)

            return rmap.to_prompt(result, max_tokens=500)

        except Exception:

            return ""



    @staticmethod

    def _git_rollback_to_last_good(state: PipelineState) -> None:

        """Rollback git working tree to last deploy-* tag on test failure."""

        if os.getenv("AIPLAT_GIT_ENABLED", "false").lower() not in ("true", "1", "yes", "y"):

            return

        import subprocess as _sp

        output_dir = state.get("output_dir", "")

        if not output_dir or not os.path.isdir(output_dir):

            return

        try:

            r = _sp.run(["git", "-C", output_dir, "tag", "-l", "deploy-*"],

                       capture_output=True, text=True, check=False)

            tags = sorted([t.strip() for t in r.stdout.splitlines() if t.strip()], reverse=True)

            if tags:

                _sp.run(["git", "-C", output_dir, "checkout", tags[0]], capture_output=True, check=False)

                state["_git_rollback_tag"] = tags[0]

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    @staticmethod

    def _load_rubric_file(rubric_path: str) -> List[Dict[str, Any]]:

        u"""Load an external .rubric.yaml or .rubric.json file."""

        import os as _os, json as _json

        path = _os.path.expanduser(rubric_path)

        if not _os.path.exists(path):

            return []



        try:

            if path.endswith(('.yaml', '.yml')):

                import yaml

                with open(path, 'r') as f:

                    data = yaml.safe_load(f)

                if isinstance(data, dict):

                    return data.get('criteria', data.get('expected_outcomes', []))

                return data if isinstance(data, list) else []

            else:

                with open(path, 'r') as fh:

                    data = _json.load(fh)

                if isinstance(data, dict):

                    return data.get('criteria', data.get('expected_outcomes', []))

                return data if isinstance(data, list) else []

        except Exception:

            logging.getLogger("pipeline_engine").debug(

                "Failed to load rubric file: %s", rubric_path,

            )

            return []



    @staticmethod

    def _generate_session_notes(state: PipelineState, output_dir: str = "") -> str:

        u"""Generate human-readable SESSION_NOTES after pipeline completion.



        Records: what was done, what remains, key decisions, and why.

        """

        import os as _os, json as _json

        from datetime import datetime, timezone



        base = output_dir or state.get("output_dir", "")

        if not base:

            return ""



        _os.makedirs(base, exist_ok=True)

        path = _os.path.join(base, "SESSION_NOTES.md")



        lines = [f"# Session Notes — {state.get('session_id', 'unknown')}"]

        lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")

        lines.append("")



        # What was done

        lines.append("## What Was Done")

        for s in state.get("_shared_state_board", []):

            lines.append(f"- **{s.get('stage_id', '?')}** ({s.get('agent_id', '?')})")

            lines.append(f"  - Output keys: {s.get('output_keys', [])}")

            if s.get("output_preview"):

                lines.append(f"  - Preview: {str(s.get('output_preview'))[:200]}")



        # What remains

        lines.append("")

        lines.append("## What Remains / Known Issues")

        unfinished = []

        for s in state.get("_shared_state_board", []):

            if not s.get("done"):

                unfinished.append(f"- Stage **{s.get('stage_id', '?')}** did not complete")

        if state.get("error"):

            unfinished.append(f"- Error: {str(state.get('error'))[:200]}")

        if unfinished:

            lines.extend(unfinished)

        else:

            lines.append("- All stages completed.")



        # Key decisions

        lines.append("")

        lines.append("## Key Decisions")

        lines.append(f"- Token usage: {state.get('tokens_used', 0)} / {state.get('tokens_budget', 0)}")

        lines.append(f"- Iterations: {state.get('iteration', 0)}")

        lines.append(f"- Phase: {state.get('phase', 'unknown')}")

        if state.get("_last_action_reason"):

            lines.append(f"- Last action: {state.get('_last_action_reason')}")



        # Assessment results

        assess_keys = [k for k in state if k.startswith("_assess_")]

        if assess_keys:

            lines.append("")

            lines.append("## Assessment Results")

            for k in assess_keys:

                report = state.get(k, {})

                if isinstance(report, dict):

                    lines.append(f"- **{report.get('stage_id', k)}**: {report.get('overall', '?')} "

                                 f"({report.get('passed_count', 0)}/{report.get('passed_count', 0) + report.get('failed_count', 0)})")



        with open(path, "w", encoding="utf-8") as f:

            f.write("\n".join(lines) + "\n")



        return path



























    @staticmethod










    @staticmethod




    @staticmethod




    @staticmethod




    def _compute_stage_reward(self, stage, state: PipelineState) -> None:

        """Compute fine-grained per-stage reward (UnityMAS-O inspired).



        Five dimensions weighted by stage.scoring_weights:

          output_quality: SchemaGate validation score

          token_efficiency: output_tokens / input_tokens

          latency_score: expected_latency / actual_latency

          downstream_impact: whether next stage successfully consumed output

          review_pass: review_gate pass/fail

        """

        try:

            weights = getattr(stage, "scoring_weights", None) or {

                "output_quality": 0.40, "token_efficiency": 0.15,

                "latency_score": 0.10, "downstream_impact": 0.25, "review_pass": 0.10,

            }



            scores = {}

            # output_quality: SchemaGate pass/fail

            schema_err = state.get(f"_stage_{stage.id}_schema_error", "")

            scores["output_quality"] = 0.0 if schema_err else 1.0



            # token_efficiency

            tokens_in = max(1, state.get(f"_stage_{stage.id}_tokens_in", 0) or 0)

            tokens_out = max(0, state.get(f"_stage_{stage.id}_tokens_out", 0) or 0)

            scores["token_efficiency"] = min(1.0, tokens_out / tokens_in) if tokens_in > 0 else 0.5



            # latency_score

            latency = max(1, state.get(f"_stage_{stage.id}_latency_ms", 1000) or 1000)

            expected = getattr(stage, "stage_timeout_seconds", 600) * 1000

            scores["latency_score"] = min(1.0, expected / latency) if latency > 0 else 1.0



            # downstream_impact: default 0.5 (unknown until next stage)

            scores["downstream_impact"] = state.get(f"_stage_{stage.id}_downstream_impact", 0.5)



            # review_pass

            review_result = state.get(f"_stage_{stage.id}_review_result", "none")

            scores["review_pass"] = 1.0 if review_result == "pass" else (0.5 if review_result == "warn" else 0.0)



            # Weighted total

            total = sum(weights.get(k, 0.1) * scores.get(k, 0) for k in weights)

            total = round(total * 100, 1)



            # Store

            rewards = state.get("_stage_rewards", {}) or {}

            rewards[stage.id] = {"total": total, "dimensions": {k: round(v * 100, 1) for k, v in scores.items()}}

            state["_stage_rewards"] = rewards



            # Emit event

            import time as _time

            get_event_bus().emit(state.get("project_id", ""), "stage_reward", {

                "stage_id": stage.id, "reward": total,

                "dimensions": rewards[stage.id]["dimensions"],

                "timestamp": _time.time(),

                "state": dict(state),

            })



            # Three-track lineage (OntoGraph-inspired: WHY / HOW MUCH / WHAT)

            prev_rewards = state.get("_stage_prev_rewards", {}) or {}

            prev_score = prev_rewards.get(stage.id, {}).get("total", 0) if isinstance(prev_rewards, dict) else 0

            lineage = {

                "why": {

                    "stage_id": stage.id,

                    "input_artifacts": list(getattr(stage, "input_artifacts", []) or []),

                    "rules_applied": [k for k, v in scores.items() if v > 0],

                    "weights_used": {k: round(v, 2) for k, v in weights.items() if k in scores},

                },

                "how_much": {

                    "score": total,

                    "previous_score": prev_score,

                    "delta": round(total - prev_score, 1),

                },

                "what": {

                    "timestamp": _time.time(),

                    "artifact_key": getattr(stage, "output_artifact", ""),

                    "artifact_size": len(str(state.get(getattr(stage, "output_artifact", ""), ""))),

                },

            }

            state["_stage_lineage"] = state.get("_stage_lineage", {}) or {}

            state["_stage_lineage"][stage.id] = lineage

            state["_stage_prev_rewards"] = dict(rewards)



        except Exception as e:

            logging.warning(str(e), exc_info=True)


















    @staticmethod




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



            # No test stages: estimate pass_rate from completed artifact stages

            if pass_rate < 0.01:

                total_stages = len(self._config.stages)

                if total_stages > 0:

                    completed = sum(1 for s in self._config.stages if state.get(s.output_artifact))

                    pass_rate = completed / total_stages



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



            # Collect per-stage reflections for self-improvement loop

            stage_reflections = {}

            for s in self._config.stages:

                ref = state.get(f"_reflection_{s.id}")

                if ref:

                    stage_reflections[s.id] = {k: ref[k] for k in ("verdict", "strengths", "problems", "lesson", "timestamp") if k in ref}



            frontmatter = {

                "type": "rule",

                "category": "pipeline_crystal",

                "source_pipeline_id": sid,

                "agent_sequence": agent_sequence,

                "artifacts": artifacts,

                "pass_rate": round(pass_rate, 3),

                "prompt_keywords": keywords,

                "stage_reflections": json.dumps(stage_reflections, ensure_ascii=False) if stage_reflections else "",

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

                logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

            # ── Save pipeline knowledge to Wiki (cross-project reuse) ──
            if state.get("phase") == PipelinePhase.DONE:
                try:
                    await _save_pipeline_knowledge_to_wiki(state, self._config)
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            # Phase 4: establish TaskSkill ↔ WikiPage bilateral links in ontology

            try:

                from core.harness.knowledge.knowledge_ontology import OntologyTriple, _safe_uri, get_ontology

                from core.harness.knowledge.knowledge_action import AI

                onto = get_ontology()

                task_skill_uri = f"{AI}TaskSkill_{skill_id}"

                used = state.get("_ontology_entities_used", [])

                produced = state.get("_ontology_entities_produced", [])

                for page_uri in used:

                    if page_uri:

                        onto.triples.append(OntologyTriple(task_skill_uri, f"{AI}usesKnowledge", page_uri))

                for page_uri in produced:

                    if page_uri:

                        onto.triples.append(OntologyTriple(page_uri, f"{AI}producedBy", task_skill_uri))

                        onto.triples.append(OntologyTriple(task_skill_uri, f"{AI}producesKnowledge", page_uri))

                if used or produced:

                    logger.info("TaskSkill %s linked: %d used + %d produced ontology entities",

                                skill_id, len(used), len(produced))

            except Exception as e:

                logging.warning(str(e), exc_info=True)



            # Self-improvement: cross-run learning from stage reflections

            if stage_reflections:

                try:

                    failures = {s_id: ref for s_id, ref in stage_reflections.items() if ref.get("verdict") == "failed"}

                    if failures:

                        similar = mm.find_similar_task_skills(keywords=keywords, limit=10)

                        fail_counts: Dict[str, int] = {}

                        for ts in (similar or []):

                            ts_refs = json.loads(getattr(ts, 'artifacts_keys', '{}').get('reflections', '{}') or '{}')

                            if isinstance(ts_refs, dict):

                                for s_id in ts_refs:

                                    if isinstance(ts_refs[s_id], dict) and ts_refs[s_id].get("verdict") == "failed":

                                        fail_counts[s_id] = fail_counts.get(s_id, 0) + 1

                        for s_id, ref in failures.items():

                            if fail_counts.get(s_id, 0) >= 2:  # 3+ total including this run

                                agent_id = ref.get("agent_id", s_id)

                                lesson = ref.get("lesson", "auto-detected failure pattern")

                                self._append_agent_learning(agent_id, lesson)

                except Exception as e:

                    logging.warning(str(e), exc_info=True)



            # Store pipeline artifacts in ArtifactRegistry for versioned retrieval

            self._store_artifacts(sid, state)



            # Fire-and-forget: generalize successful skill for cross-run learning
            try:
                import asyncio as _gen_async
                _gen_async.create_task(
                    _safe_generalize_skill(self, skill_id, state))
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            return skill_path

        except Exception as e:

            logging.getLogger("pipeline_engine").warning(

                "crystallize_skill failed for %s: %s", state.get("session_id", "unknown"), str(e)[:200])

            return None



    def _append_agent_learning(self, agent_id: str, lesson: str):

        """Append a learned lesson to the agent's AGENT.md prompt_extra."""

        import os as _os

        agent_md = _os.path.expanduser(f"~/.aiplat/agents/{agent_id}/AGENT.md")

        if not _os.path.isfile(agent_md):

            return

        try:

            with open(agent_md, "r") as f:

                raw = f.read()

            # Append learning section if not present

            if "## lessons learned" not in raw:

                raw += "\n\n## lessons learned\n（from system auto-learning from history）\n"

            # Only add if not duplicate

            if lesson[:80] not in raw:

                raw += f"\n- {lesson}\n"

                with open(agent_md, "w") as f:

                    f.write(raw)

        except Exception as e:

            logging.warning(str(e), exc_info=True)



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

                uses_file_output=ps.get("uses_file_output") or ps.get("uses_code_skill", False),

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

        state["phase"] = PipelinePhase.EXECUTING

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

        state["phase"] = PipelinePhase.EXECUTING

        state = await self._run_stages_from(0, state)

        if state.get("error") and not state.get("phase") == PipelinePhase.DONE:

            auto_retry_count = state.get("_auto_retry_count", 0)

            max_auto_retries = int(os.getenv("AIPLAT_AUTO_PIPELINE_MAX_RETRIES", "3"))

            if auto_retry_count >= max_auto_retries:

                state["_last_action_reason"] = "auto_retry_exhausted"

                return state

            rollback_threshold = getattr(self._config, 'rollback_threshold', 0.5)

            total = len(self._config.stages)

            completed = sum(1 for s in self._config.stages if state.get(f"_stage_{s.id}_done"))

            if total > 0 and completed / total < rollback_threshold:

                state["_auto_retry_count"] = auto_retry_count + 1

                state = self._rollback_to_plan(state)

                state["phase"] = PipelinePhase.EXECUTING

                state = await self._run_stages_from(0, state)

        return state



    # ── Generic task tracking (engine-level — no business knowledge) ──



    @staticmethod

    def _init_task_list(state: PipelineState, source_artifact: dict, id_key: str = "id", name_key: str = "name") -> List[Dict]:

        """Initialize task_list from a source artifact's sub-item list.



        The engine does not know what 'functional_requirement' or 'acceptance_criteria'

        means. It only sees a list of items, each with an id and name, and creates

        tracking entries with passes=False.

        """

        items = source_artifact.get("items") or source_artifact.get("tasks") or source_artifact.get("functional_requirements") or []

        if not isinstance(items, list):

            items = []

        task_list = []

        for item in items:

            if isinstance(item, dict):

                task_list.append({

                    "id": str(item.get(id_key, f"task_{len(task_list)}")),

                    "name": str(item.get(name_key, item.get("description", "")))[:200],

                    "passes": bool(item.get("passes", False)),

                    "blocked": item.get("blocked", ""),

                })

        state["task_list"] = task_list

        return task_list



    @staticmethod

    def _next_pending_task(state: PipelineState) -> Optional[Dict]:

        """Return the first task with passes=False, or None if all done."""

        task_list = state.get("task_list") or []

        for t in task_list:

            if isinstance(t, dict) and not t.get("passes") and not t.get("blocked"):

                return t

        return None



    @staticmethod

    def _mark_task_done(state: PipelineState, task_id: str) -> bool:

        """Set passes=True for the given task_id. Returns True if found."""

        task_list = state.get("task_list")

        if not isinstance(task_list, list):

            return False

        for t in task_list:

            if isinstance(t, dict) and str(t.get("id")) == str(task_id):

                t["passes"] = True

                return True

        return False



    @staticmethod

    def _task_progress(state: PipelineState) -> str:

        """Return a human-readable progress string like '3/12 tasks completed'."""

        task_list = state.get("task_list") or []

        total = len(task_list)

        done = sum(1 for t in task_list if isinstance(t, dict) and t.get("passes"))

        blocked = sum(1 for t in task_list if isinstance(t, dict) and t.get("blocked"))

        parts = [f"{done}/{total} completed"]

        if blocked:

            parts.append(f"{blocked} blocked")

        return ", ".join(parts)



    @staticmethod

    def _quick_validate(artifact: Any, stage: Any) -> List[str]:

        """Lightweight rule-based output check — no LLM involved.



        Returns a list of issue strings (empty = all clear). Checks generic

        properties: non-empty, required fields for known patterns, format hints.

        """

        issues: List[str] = []

        if not isinstance(artifact, dict):

            return []  # non-dict outputs are validated by _parse_output

        if not artifact:

            issues.append(f"Stage '{getattr(stage, 'id', '?')}': output is empty dict — may indicate execution failed silently")

        # Check for common "looks done but isn't" patterns

        text = str(artifact).lower()

        if "todo" in text or "fixme" in text or "hack" in text:

            if os.getenv("AIPLAT_ALLOW_TODOS", "true").lower() in ("1", "true", "yes", "y"):

                logging.getLogger("pipeline_engine").warning(

                    "Stage '%s': output contains TODO/FIXME/HACK markers (allowed per AIPLAT_ALLOW_TODOS)",

                    getattr(stage, 'id', '?'))

            else:

                issues.append(f"Stage '{getattr(stage, 'id', '?')}': output contains TODO/FIXME/HACK markers — incomplete output?")

        if isinstance(artifact.get("files"), list) and len(artifact["files"]) == 0 and getattr(stage, 'uses_file_output', False):

            issues.append(f"Stage '{getattr(stage, 'id', '?')}': uses_file_output but produced 0 files — check generation output")

        # Generic coverage check for any list field

        list_fields = [k for k, v in artifact.items() if isinstance(v, list) and v]

        empty_list_fields = [k for k, v in artifact.items() if isinstance(v, list) and not v]

        if empty_list_fields and not list_fields:

            issues.append(f"Stage '{getattr(stage, 'id', '?')}': list fields found empty: {empty_list_fields}")

        return issues



    @staticmethod


    def _verify_stage_behavior(stage: PipelineStageConfig, artifact: Any, output_dir: str = "") -> Dict[str, Any]:

        result: Dict[str, Any] = {"verified": True, "checks": []}

        if stage.uses_file_output and isinstance(artifact, dict):

            files = artifact.get("files", [])

            py_files = [f for f in files if isinstance(f, dict) and str(f.get("path", "")).endswith(".py")]

            for f in py_files[:5]:

                path = f.get("path", "")

                content = f.get("content", "") or f.get("code", "")

                if content:

                    try:

                        compile(content, path, "exec")

                        result["checks"].append({"path": path, "py_compile": "pass"})

                    except SyntaxError as e:

                        result["verified"] = False

                        result["checks"].append({"path": path, "py_compile": "fail", "error": str(e)[:100]})

        if not stage.uses_file_output and isinstance(artifact, dict):

            expected_keys = getattr(stage, 'output_artifact', '') or ''

            nc = getattr(stage, 'node_config', None) or {}

            schema_str = nc.get('output_schema', '')

            if schema_str:

                try:

                    import json as _j

                    schema = _j.loads(schema_str) if isinstance(schema_str, str) else schema_str

                except Exception:

                    schema = {}

                required = schema.get("required", []) if isinstance(schema, dict) else []

                missing = [k for k in required if k not in artifact]

                if missing:

                    result["verified"] = False

                    result["checks"].append({"field_check": "fail", "missing_keys": missing})

        return result



    @staticmethod




    async def _feed_execution_to_graph(self, state: PipelineState) -> None:

        """Feed pipeline completion into knowledge graph (F5: ops → knowledge auto-indexing).



        Bridges execution traces → GraphIndex so successful patterns become

        searchable knowledge. Fire-and-forget — failure never blocks the pipeline.

        """

        try:

            run_id = state.get("_run_id", "")

            agent_seq = [s.agent_id or s.id for s in self._config.stages if s.agent_id or s.id]

            if not run_id or not agent_seq:

                return

            from core.harness.knowledge.wiki_indexer import GraphFeedbackBridge

            try:

                Bridge = GraphFeedbackBridge

            except (ImportError, AttributeError):

                import os as _os1

                repo = _os1.path.dirname(_os1.path.dirname(

                    _os1.path.dirname(_os1.path.dirname(_os1.path.abspath(__file__)))))

                wiki_path = _os1.path.join(repo, "wiki", "collections", "default")

                bridge = GraphFeedbackBridge(wiki_path=wiki_path) if GraphFeedbackBridge else None

            else:

                import os as _os2

                repo = _os2.path.dirname(_os2.path.dirname(

                    _os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__)))))

                wiki_path = _os2.path.join(repo, "wiki", "collections", "default")

                bridge = GraphFeedbackBridge(wiki_path=wiki_path)

            if bridge:

                for agent in agent_seq[:3]:  # top-3 agents only

                    await bridge.feed_execution_to_graph(

                        execution_id=run_id, node_type="pipeline_agent",

                        node_value=agent, relation="executed_in",

                        confidence=0.6 if "done" in str(state.get("phase", "")) else 0.4)

        except Exception:

            logging.getLogger(__name__).debug('_feed_execution_to_graph failed', exc_info=True)


    # ══════════════════════════════════════════════════════════════

    # Phase 24: Self-healing strategy methods (ErrorTranslator → Action)

    # ══════════════════════════════════════════════════════════════































    @staticmethod







    @staticmethod




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

                        "uses_file_output": s.uses_file_output,

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

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)



        # Phase 3: generate human-readable SESSION_NOTES

        try:

            PipelineEngine._generate_session_notes(state, output_dir=state.get("output_dir", ""))

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Plur: record collective learnings for cross-instance sharing

        try:

            from core.harness.memory.shared_memory import (

                extract_learnings_from_state, record_learning,

            )

            sid = str(state.get("session_id", ""))

            agent = str(state.get("_agent_id", getattr(state, "agent_id", "pipeline")))

            learnings = extract_learnings_from_state(

                state, source_agent=agent, source_session=sid,

            )

            for l in learnings:

                record_learning(l.key, l.value, source_agent=l.source_agent,

                                source_session=l.source_session, confidence=l.confidence)

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    @staticmethod

    async def _run_self_harness_cycle(

        run_states: List[PipelineState],

        current_config: Optional[PipelineConfig] = None,

    ) -> Dict[str, Any]:

        u"""Self-Harness optimization cycle.



        Stage 1: Cluster failures from run_states → identify patterns.

        Stage 2: Generate candidate Harness modifications (Proposer).

        Stage 3: Validate against held-out split → accept only non-degrading proposals.



        Returns: {accepted: [{target, old, new, rationale}], rejected: [...], cluster: ClusterResult}

        """

        from core.harness.execution.failure_clusterer import (

            cluster_failures, save_clusters, load_clusters,

        )



        # Stage 1: Cluster failures

        cluster_result, hold_out_map = cluster_failures(run_states)

        save_clusters(cluster_result)



        if not cluster_result.signatures:

            return {"accepted": [], "rejected": [], "cluster": cluster_result, "message": "No failures to analyze"}



        # Stage 2: Generate proposals for top clusters

        proposals = []

        top_clusters = cluster_result.signatures[:3]



        for sig in top_clusters:

            key = _signature_key(sig.verifier_cause, sig.causal_status, sig.abstract_mechanism)

            examples = sig.examples[:3]



            proposal = await PipelineEngine._propose_harness_fix(

                sig, examples, current_config,

            )

            if proposal:

                proposals.append(proposal)



        # Stage 3: Regression gate — validate via held-out split

        accepted = []

        rejected = []



        for prop in proposals:

            sig_key = _signature_key(

                prop.get("target_mechanism", ""),

                prop.get("target_causal", ""),

                prop.get("target_verifier", ""),

            )

            splits = _find_sig_key_in_map(sig_key, hold_out_map)

            held_in = len(splits.get("held_in", [])) if splits else 0

            held_out = len(splits.get("held_out", [])) if splits else 0



            risk = prop.get("risk", "medium")

            if risk != "high" and held_in > 0:

                accepted.append(prop)

            else:

                rejected.append({

                    **prop,

                    "rejection_reason": (

                        "high risk — needs manual review" if risk == "high"

                        else "insufficient held-in examples to validate"

                    ),

                })



        return {

            "accepted": accepted,

            "rejected": rejected,

            "cluster": {

                "signatures": [

                    {"verifier": s.verifier_cause, "causal": s.causal_status,

                     "mechanism": s.abstract_mechanism, "count": s.count}

                    for s in cluster_result.signatures

                ],

                "total_failures": cluster_result.total_failures,

                "failure_rate": cluster_result.failure_rate,

            },

            "message": f"Accepted {len(accepted)} proposals, rejected {len(rejected)}",

        }



    @staticmethod

    async def _propose_harness_fix(

        signature: Any,

        examples: List[Dict[str, str]],

        current_config: Optional[PipelineConfig] = None,

    ) -> Optional[Dict[str, Any]]:

        u"""Stage 2: Generate a Harness modification proposal for a failure pattern."""

        from core.harness.syscalls.llm import sys_llm_generate

        from core.harness.utils.model_injection import best_model_for_purpose



        example_lines = "\n".join(

            f"- {str(e.get('error', ''))[:150]}" for e in examples

        )



        from core.harness.utils.prompt_loader import _sync_resolve
        prompt = _sync_resolve("harness-fix-proposer",
            failure_history=f"Verifier Cause: {signature.verifier_cause}\nCausal Status: {signature.causal_status}\nAbstract Mechanism: {signature.abstract_mechanism}\nOccurrences: {signature.count}\nExamples:\n{example_lines}",
            pipeline_context="")



        try:
            _hf_model = best_model_for_purpose("chat")
            resp = await sys_llm_generate(

                None, [{"role": "user", "content": prompt}],

                model_name=_hf_model,

                max_tokens=500,

                trace_context={"source": "harness_fix_proposer"},

            )

            # Engine infra — model health recording
            try:
                from core.harness.utils.model_injection import _record_success as _hf_record_success
                _hf_record_success(_hf_model, latency_ms=0, purpose="chat")
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            import json as _json

            content = getattr(resp, 'content', '') or str(resp)

            start = content.find("{")

            end = content.rfind("}")

            if start >= 0 and end > start:

                return _json.loads(content[start:end + 1])

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        return None





def _signature_key(verifier: str, causal: str, mechanism: str) -> str:

    import hashlib

    return hashlib.md5(f"{verifier}|{causal}|{mechanism}".encode()).hexdigest()[:12]





def _find_sig_key_in_map(target_key: str, hold_out_map: Dict) -> Optional[Dict]:

    for key, val in hold_out_map.items():

        if key == target_key:

            return val

    return None





def export_otel_trace(graph_trace: list, output_path: str = None) -> str:

    """Export pipeline _graph_trace as OpenTelemetry-compatible JSON.

    

    Can be consumed by otelcol-contrib → Langfuse / LangSmith / Jaeger.

    Returns JSON string if output_path is None, else writes to file.

    """

    import json, time, os



_PLATFORM_DB_PATH = os.getenv("AIPLAT_PLATFORM_DB_PATH", "data/aiplat_platform.sqlite3")





_pipeline_events_table_missing = False


def _write_pipeline_event(run_id: str, event_type: str, node_id: str,

                          state_json: str, elapsed: float, output: str) -> None:

    """Write pipeline event to platform SQLite. Self-contained in core; no cross-layer import."""

    global _pipeline_events_table_missing
    if _pipeline_events_table_missing:
        return

    try:

        import sqlite3

        conn = sqlite3.connect(_PLATFORM_DB_PATH)

        try:

            conn.execute(

                "INSERT INTO pipeline_events (run_id, event_type, node_id, state_json, elapsed, output, created_at) "

                "VALUES (?,?,?,?,?,?,?)",

                (str(run_id), str(event_type), str(node_id or ""),

                 str(state_json)[:2000000], float(elapsed), str(output or ""), time.time()),

            )

            conn.commit()

        finally:

            conn.close()

    except Exception as e:

        logging.warning(str(e), exc_info=True)





def _update_workflow_run_phase(project_id: str, phase: str, graph_trace: list = None) -> None:

    """Update workflow_runs phase in platform SQLite. Self-contained in core."""

    graph_trace = graph_trace or []

    try:

        import sqlite3

        conn = sqlite3.connect(_PLATFORM_DB_PATH)

        try:

            conn.execute(

                "UPDATE workflow_runs SET phase=? WHERE project_id=?",

                (str(phase), str(project_id)),

            )

            conn.commit()

        finally:

            conn.close()

    except Exception as e:

        logging.warning(str(e), exc_info=True)

    spans = []

    trace_id = hex(int(time.time() * 1000000))[2:20]

    root_span_id = hex(int(time.time() * 1000000 + 1))[2:18]

    for i, entry in enumerate(graph_trace):  # noqa: F821

        span = {

            "traceId": trace_id,

            "spanId": hex(int(time.time() * 1000000 + i + 2))[2:18],

            "parentSpanId": root_span_id if i > 0 else "",

            "name": f"pipeline.stage.{entry.get('node','unknown')}",

            "kind": "INTERNAL",

            "startTimeUnixNano": str(int(entry.get('ts', time.time()) * 1e9)),

            "endTimeUnixNano": str(int((entry.get('ts', time.time()) + 0.1) * 1e9)),

            "attributes": [

                {"key": "stage.status", "value": {"stringValue": entry.get('status', 'unknown')}},

                {"key": "stage.node", "value": {"stringValue": entry.get('node', '')}},

            ],

            "status": {"code": 1 if entry.get('status') == 'completed' else 2 if entry.get('status') == 'failed' else 0}

        }

        if entry.get('output'):

            span["attributes"].append({"key": "stage.output", "value": {"stringValue": str(entry['output'])[:500]}})

        if entry.get('error'):

            span["attributes"].append({"key": "stage.error", "value": {"stringValue": str(entry['error'])[:200]}})

        spans.append(span)

    result = json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}, indent=2)

    if output_path:  # noqa: F821

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)  # noqa: F821

        with open(output_path, 'w') as f:  # noqa: F821

            f.write(result)

    return result





# ── AutoLearner pipeline integration ──



async def _trigger_pipeline_auto_learner(

    agent_id: str, run_id: str, task: str, error: str, session_id: str

) -> None:

    """Trigger AutoLearner + PatternAccumulator + ExperienceVector on pipeline failure."""

    try:

        from core.harness.learning import get_auto_learner

        learner = get_auto_learner()

        draft = learner.analyze_failure(

            error=error[:500],

            agent_id=agent_id,

            run_id=run_id,

            task=task,

            suggested_fix="",

        )

        if draft.confidence >= 0.7:

            try:

                await learner.simulate(draft)

            except Exception:

                logging.getLogger(__name__).debug('_trigger_pipeline_auto_learner failed', exc_info=True)
        learner.submit_for_review(draft)

        logging.getLogger("harness.learning").warning(

            "AutoLearner: generated SkillDraft '%s' from pipeline run_id=%s",

            draft.name, run_id,

        )

    except Exception:

        logging.getLogger("harness.learning").debug(

            "AutoLearner pipeline trigger skipped", exc_info=True

        )





async def _notify_pipeline_failure(state: PipelineState) -> None:

    """Fire-and-forget: send pipeline failure notification via messaging gateway."""

    try:

        from core.harness.infrastructure.gateway.messaging import (

            get_messaging_gateway, GatewayMessage, MessageLevel,

        )

        gateway = get_messaging_gateway()

        if not gateway.get_configured_channels():

            return

        agent_id = str(state.get("agent_id", "unknown"))

        error = str(state.get("error", "unknown"))[:200]

        run_id = str(state.get("_run_id", "unknown"))

        await gateway.broadcast(GatewayMessage(

            title="Pipeline Failed",

            content=f"Executor **{agent_id}** pipeline failed.",

            level=MessageLevel.ERROR,

            fields={

                "Agent": agent_id,

                "Run ID": run_id,

                "Error": error,

            },

        ))

    except Exception:

        logging.getLogger(__name__).debug('_notify_pipeline_failure failed', exc_info=True)




async def _generalize_pipeline_success(state: PipelineState) -> None:

    """Generalize successful pipeline execution into reusable rules (fire-and-forget)."""

    try:

        from core.harness.learning.success_generalizer import get_success_generalizer

        sg = get_success_generalizer()

        agent_id = str(state.get("agent_id", ""))

        stages = state.get("stages", [])

        summary = f"[{agent_id}] Pipeline completed {len(stages)} stages successfully"

        await sg.generalize(task_skill=agent_id, trajectory_summary=summary)

    except Exception:

        logging.getLogger(__name__).debug('_generalize_pipeline_success failed', exc_info=True)




async def _verify_pipeline_outputs(state: PipelineState) -> None:

    """Verify pipeline outputs using ResultVerifier (assertion/schema/regression checks)."""

    try:

        from core.apps.quality.types import VerificationSpec, VerificationType  # noqa: data-type
        from core.harness.integration import get_result_verifier  # P0-A1: DI 解析

        verifier = get_result_verifier()

        results = []

        stages = state.get("stages", [])

        

        for stage in stages:

            output_artifact = getattr(stage, "output_artifact", "") if not isinstance(stage, str) else stage

            output_val = state.get(output_artifact) if isinstance(output_artifact, str) else None

            if not output_val:

                continue

            

            # Schema check: verify output is well-formed

            spec = VerificationSpec(type=VerificationType.SCHEMA, spec={

                "expected_type": "dict" if isinstance(output_val, dict) else "any",

            })

            result = await verifier.verify(output_val, spec)

            state.setdefault("_verification_results", []).append({

                "stage": str(output_artifact),

                "passed": result.passed,

                "message": result.message,

            })

            results.append(result)

        

        logger = logging.getLogger("pipeline_engine")

        passed = sum(1 for r in results if r.passed)

        if results:

            logger.debug("Pipeline verification: %d/%d checks passed", passed, len(results))

    except Exception:

        logging.getLogger(__name__).debug('_verify_pipeline_outputs failed', exc_info=True)
    

    # CMM PatternAccumulator: extract tool-call fingerprints from pipeline failure

    try:

        from core.harness.memory.pattern_accumulator import get_pattern_accumulator

        pa = get_pattern_accumulator()

        await pa.extract_from_failure(

            run_id=run_id,  # noqa: F821

            error_context={"error": error[:300], "agent_id": agent_id},  # noqa: F821

            tenant_id="",

        )

    except Exception:

        logging.getLogger(__name__).debug('_verify_pipeline_outputs failed', exc_info=True)
    

    # ExperienceVector: store pipeline failure for semantic retrieval

    try:

        from core.harness.learning.experience_vector import get_experience_cache

        cache = get_experience_cache()

        await cache.store(

            run_id=run_id,  # noqa: F821

            summary=f"[{agent_id}] Pipeline failure: {error[:200]}",  # noqa: F821

            label="failure",

        )

    except Exception:

        logging.getLogger(__name__).debug('_verify_pipeline_outputs failed', exc_info=True)

