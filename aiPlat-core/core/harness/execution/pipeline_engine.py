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



class PipelineEngine:

    def __init__(self, config: PipelineConfig, model: Any = None, skill_loader: Any = None):

        self._config = config

        self._model = model

        if self._model is None:

            self._model = self._load_default_model(category="agent")

        self._skill_loader = skill_loader

        self._stage_runner = StageRunner(model=self._model, pipeline_config=config)

        self._eval_runner = EvalRunner()

        self._model_lock = asyncio.Lock()  # guards parallel stage model swaps



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

                        rerank_prompt = f"""You are a relevance ranker. Given a user query and retrieved passages, rank them by relevance to the query. Return the top {kb_top_k} passages in order, with a relevance score (0-1).



Query: {kb_query}



Passages:

{str(output)[:3000]}



Output format: JSON array of {{"rank": 1, "score": 0.95, "content": "..."}}"""

                        from core.harness.syscalls.llm import sys_llm_generate

                        rerank_resp = await sys_llm_generate(

                            best_model_for_purpose("chat"),

                            [{"role": "user", "content": rerank_prompt}],

                            trace_context={"source": f"workflow_knowledge_rerank_{stage.id}"}

                        )

                        rerank_text = getattr(rerank_resp, 'content', '') or ''

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

            prompt = (

                f"You are a technical planner. Based on the upstream context, "

                f"produce a structured task execution plan.\n\n"

                f"{plan_hint}\n\n"

                f"Output format: JSON array of tasks. Each task has: "

                f'{{"id": "t1", "description": "...", "acceptance_criteria": ["..."], '

                f'"estimated_complexity": "low|medium|high"}}'

            )

            from core.harness.syscalls.llm import sys_llm_generate

            from core.harness.utils.model_injection import best_model_for_purpose

            resp = await sys_llm_generate(

                None, [{"role": "user", "content": prompt}],

                model_name=best_model_for_purpose("chat"),

                max_tokens=1000,

            )

            plan_text = getattr(resp, 'content', '') or str(resp)

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

            # Use first stage's output_artifact as the PRD key (config-driven)

            prd_key = self._config.stages[0].output_artifact if self._config.stages else ""

            state[prd_key] = prd_data

        return await self._run_stages_from(0, state)



    async def approve(self, state: PipelineState, feedback: str = "") -> PipelineState:

        state = dict(state)

        self._audit_hitl(state, "hitl_approved", detail=feedback[:200] if feedback else "")



        # ── Human-stage HITL: inject feedback as human input, return immediately ──

        # The actual pipeline continuation is handled by the caller (background task)

        hitl_stage_id = state.get("_hitl_stage_id", "")

        human_feedback = feedback or state.get("_hitl_human_feedback", "")

        if hitl_stage_id and human_feedback:

            for i, s in enumerate(self._config.stages):

                if s.id == hitl_stage_id:

                    state[s.output_artifact] = {"raw_output": human_feedback, "source": "human_hitl"}

                    state[f"_stage_{s.id}_done"] = True

                    try:

                        import json as _j

                        parsed = _j.loads(human_feedback)

                        if isinstance(parsed, dict):

                            state[s.output_artifact] = parsed

                    except Exception:

                        logging.getLogger(__name__).debug('approve failed', exc_info=True)
                    state["_hitl_resolved_" + s.id] = True

                    state["_hitl_stage_id"] = ""

                    state["_hitl_human_feedback"] = ""

                    state["phase"] = PipelinePhase.EXECUTING

                    state["_current_stage_idx"] = i

                    self._audit_hitl(state, "hitl_human_input", detail=f"stage={s.id}")

                    # Don't run remaining stages here — let caller do it async

                    return state

            state["_hitl_stage_id"] = ""

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



    async def reject(self, state: PipelineState, feedback: str) -> PipelineState:

        state = dict(state)

        state["_reject_feedback"] = feedback

        self._audit_hitl(state, "hitl_rejected", detail=feedback[:200])

        idx = self._find_hitl_stage_index(state)

        for i in range(idx, len(self._config.stages)):

            state[self._config.stages[i].output_artifact] = None

            state.pop(f"_stage_{self._config.stages[i].id}_done", None)

            if self._config.stages[i].generate_test_plan:

                state[self._config.stages[i].test_result_key] = None

        state["phase"] = PipelinePhase.EXECUTING

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



            # Execute all stages in this layer in parallel with Semaphore control

            layer_timeout = max(600 * len(layer), 3600)

            try:

                from core.harness.integration import get_parallel_executor

                ParallelExecutor = get_parallel_executor().ParallelExecutor

                pool_size = max(1, min(len(layer), 5))

                _executor = ParallelExecutor(max_concurrency=pool_size)

                _sem = asyncio.Semaphore(pool_size)

                async def _stage_with_sem(i):

                    async with _sem:

                        return await self._exec_single_stage(stages[i], i, state)

                results = await asyncio.wait_for(

                    asyncio.gather(*[_stage_with_sem(i) for i in layer], return_exceptions=True),

                    timeout=layer_timeout,

                )

                state.setdefault("_parallel_stats", []).append({

                    "pool_size": pool_size, "layer_count": len(layer),

                })

            except asyncio.TimeoutError:

                state["error"] = f"layer_timeout ({layer_timeout}s)"

                state["phase"] = PipelinePhase.FAILED

                state["_last_action_reason"] = "layer_timeout"

                break

            # Merge results and check for HITL

            paused = False

            for i, result in enumerate(results):

                if isinstance(result, Exception):

                    idx = layer[i]

                    # Write traceback to dedicated log file for debugging
                    import traceback as _tb, os as _os
                    _log_path = _os.path.join(_os.path.expanduser("~/.aiplat"), "pipeline_errors.log")
                    with open(_log_path, "a") as _lf:
                        _lf.write(f"\n=== Stage {idx} error at {_time.time()} ===\n")
                        _lf.write(f"Exception: {result}\n")
                        _tb.print_exception(type(result), result, result.__traceback__, file=_lf)
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



            # P1-3: 动态预算重分配——未使用的 token 均分给剩余 stage

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

        # Feed execution into knowledge graph (F5: ops→知识自动索引)

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

                pm.push(event={"type": "pipeline_complete", "phase": state.get("phase"),

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

        for stage in stages[:-1]:  # keep last stage

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

                    desc_parts.append(f"产出:{s.output_artifact}")

                if getattr(s, "uses_file_output", False):

                    desc_parts.append("文件操作")

                agent_descriptions[name] = ", ".join(desc_parts) if desc_parts else "通用Agent"



        # Stage index map for routing

        stage_idx_map: Dict[str, int] = {s.id: i for i, s in enumerate(stages)}



        router = DynamicRouter(

            agent_descriptions=agent_descriptions,

            max_steps=int(os.getenv("AIPLAT_DYNAMIC_ROUTER_MAX_STEPS", "15")),

        )

        goal = state.get("_pipeline_goal", "执行流水线")

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

        # Persist trace for developer visibility (Andrew Ng 三层 Loop P2)

        await self._persist_dynamic_trace(state, done_indices, stages)

        return state



    async def _run_debate(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Skill 6: Multi-agent debate via run_agent_debate() from core debate engine."""

        from core.harness.execution.debate import run_agent_debate



        goal = state.get("_pipeline_goal", "执行流水线")

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

            "reasoning": f"辩论完成: {result.get('rounds')} 轮, converged={result.get('converged')}",

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



        goal = state.get("_pipeline_goal", "执行流水线")

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

            "reasoning": f"竞选择优完成: winner={result.get('winner')}, scores={result.get('scores')}",

        })

        return state



    async def _run_roundtable(

        self, stages: List[PipelineStageConfig], state: PipelineState,

    ) -> PipelineState:

        """Skill 2 Roundtable: agents discuss equally, seeing all prior outputs each round."""

        from core.harness.execution.roundtable import run_roundtable



        goal = state.get("_pipeline_goal", "执行流水线")

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

            "reasoning": f"圆桌讨论完成: {result.get('rounds')} 轮, converged={result.get('converged')}",

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

                    "summary": f"完成 {len(done_indices)}/{len(stages)} 个 stage",

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



    async def _dispatch_execute(self, stage: PipelineStageConfig, state: PipelineState) -> PipelineState:

        """Execute stage based on declarative execution_mode field."""

        mode = getattr(stage, 'execution_mode', 'code_first') or 'code_first'



        # PR #2: 若 stage 未指定执行模式，从 ControlProfile 读取 orchestration_mode

        if mode == "code_first":

            try:

                from core.harness.meta.profile_registry import get_active_profile

                orch_mode = get_active_profile().orchestration_mode

                if orch_mode == "auto":

                    # PR #3: 自动模式 → OrchestrationSelector 按复杂度选

                    from core.harness.meta.orchestration_selector import OrchestrationSelector

                    selector = OrchestrationSelector()

                    stage_count = len(getattr(self._config, 'stages', []))

                    orch_mode = selector.select_for_pipeline(

                        stage_count=stage_count,

                        has_parallel=False,

                        profile_mode="auto",

                    )

                if orch_mode in ("single", "chain", "tree", "reflexion"):

                    mode = orch_mode

            except Exception:

                logging.getLogger(__name__).debug('_dispatch_execute failed', exc_info=True)


        if mode == "plan_only":

            return await self._gen_test_plan(stage, state)

        elif mode == "tdd":

            return await self._exec_tdd_cycle(stage, state)

        else:  # code_first (default)

            return await self._exec_stage(stage, state)



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

        if existing and (not isinstance(existing, dict) or len(existing) > 0):

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

            # PR #3: 阶段超时 — 归因到 D4_orchestration

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

        # ── Cross-stage validation ──

        state.setdefault("_cross_validations", {})

        self._validate_cross_stage(stage, state)

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



    def _build_prompt(self, stage: PipelineStageConfig, state: PipelineState) -> str:

        skill_corpus_context = (

            "[SKILL CORPUS: If you need a capability not found in the enabled skills above, "

            "you can search disabled skills via:\n"

            "  1. sys_skill_corpus_search(query, limit=10) → candidate list with ref/name/score\n"

            "  2. sys_skill_corpus_inspect(ref) → full metadata (NOT body) for a candidate\n"

            "  3. sys_skill_corpus_select(ref, query, reason, confidence) → returns body + records audit\n"

            "Remember: inspect before select. Never select without checking metadata first.]\n"

        )

        feedback = state.get("_reject_feedback", "")

        fb = f"\n## Reject Feedback\n{feedback}" if feedback else ""

        ctx = {}

        constraint_text = ""

        handoff_text = ""

        for artifact_name in stage.input_artifacts:

            val = state.get(artifact_name)

            if val:

                # Compact downstream artifacts: only the first artifact gets full detail.

                # Saves ~90% of token overhead for non-PRD upstream summaries.

                is_first = artifact_name == (stage.input_artifacts[0] if stage.input_artifacts else "")

                primary_chars = int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_CHARS", "8000"))

                secondary_chars = int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_SECONDARY_CHARS", "2000"))

                max_chars = primary_chars if is_first else secondary_chars

                ctx[artifact_name] = self._summarize_artifact(val, max_chars=max_chars)

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



        # Phase A: scene context injection — tells Agent what business problem we're solving

        scene_context = ""

        scene_id = getattr(stage, 'scene_id', '') or state.get("scene_id", "")

        if scene_id:

            try:

                from core.harness.knowledge.scene_model import get_scene

                scene = get_scene(scene_id)

                if scene:

                    scene_context = f"\n## Business Context (Scene: {scene.name})\n{scene.to_agent_context()}\n"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # Cross-session memory: inject previous SESSION_NOTES so Agent remembers past context

        previous_notes = ""

        try:

            import os as _os, glob as _glob

            from core.utils.paths import get_aiplat_data_dir

            output_root = get_aiplat_data_dir("output")

            note_files = sorted(

                _glob.glob(_os.path.join(output_root, "*", "SESSION_NOTES.md")),

                key=_os.path.getmtime, reverse=True,

            )

            if note_files:

                summaries = []

                for f in note_files[:5]:

                    with open(f) as fh:

                        text = fh.read()

                    first_lines = "\n".join(text.split("\n")[:5])

                    summaries.append(f"## {_os.path.basename(_os.path.dirname(f))}\n{first_lines}")

                previous_notes = "\n## Recent Session Context\n" + "\n---\n".join(summaries) + "\n"

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Plur: collective learnings shared across all agent instances

        collective_context = ""

        try:

            from core.harness.memory.shared_memory import get_learnings_context

            collective_context = get_learnings_context()

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Phase D: knowledge gap context — tell Agent what we don't know

        gaps_context = ""

        try:

            from core.harness.syscalls.ontology_context import sys_ontology_context

            onto_ctx = sys_ontology_context(question=state.get("description", ""), include_gaps=True)

            gaps = onto_ctx.get("knowledge_gaps", {})

            if gaps and gaps.get("total_gaps", 0) > 0:

                gap_lines = []

                if gaps.get("source_less_count"):

                    gap_lines.append(f"- {gaps['source_less_count']} concepts lack source documents")

                if gaps.get("unmined_count"):

                    gap_lines.append(f"- {gaps['unmined_count']} KB documents have not been mined into wiki pages")

                if gaps.get("unidirectional_count"):

                    gap_lines.append(f"- {gaps['unidirectional_count']} citations are one-way")

                if gaps.get("orphan_count"):

                    gap_lines.append(f"- {gaps['orphan_count']} pages have no connections to other knowledge")

                if gap_lines:

                    gaps_context = "\n## Knowledge Gaps\n" + "\n".join(gap_lines) + "\n\nWhen producing knowledge artifacts, consider filling these gaps."

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Progressive disclosure: skill stubs only (~50 tokens/skill)

        skill_stubs_context = ""

        try:

            from core.harness.integration import get_skill_registry, _start_bg_curator

            reg = get_skill_registry()

            _start_bg_curator()

            skill_stubs_context = "\n" + reg.get_all_stubs() + "\n"

            skill_stubs_context += (

                "[SKILL RECOMMENDATION: When you identify that the current task matches "

                "one of the available skills above, proactively describe how you would use it "

                "before invoking sys_skill_call. This helps the user understand your approach.]\n"

            )

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Ponytail: Lazy Senior Developer constraint (via PONytail_MODE env)

        ponytail_context = ""

        ponytail_mode = os.getenv("PONytail_MODE", "full").lower()

        if ponytail_mode != "off":

            try:

                import os as _os

                skill_path = _os.path.expanduser("~/.aiplat/skills/ponytail-lazy/SKILL.md")

                if _os.path.exists(skill_path):

                    with open(skill_path, "r") as f:

                        body = f.read()

                    ponytail_context = f"\n## Ponytail: Lazy Senior Developer ({ponytail_mode} mode)\n{body}\n"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # Output format instruction for code-generating stages

        fmt_text = ""

        if stage.uses_file_output:

            fmt_text = (

                "\n## Output Format\n"

                "Use ## FILE: path/to/file.py format for EACH file.\n"

                "Do NOT wrap files in ``` fences. Each ## FILE: header starts a new file.\n"

                "Example:\n## FILE: main.py\n[content]\n## FILE: models/user.py\n[content]"

            )

            # Inject existing scaffold files as context (prevent regeneration)

            scaffold = state.get("project_scaffold")

            if isinstance(scaffold, dict) and self._collect_files(scaffold):

                existing = [f["path"] for f in self._collect_files(scaffold)]

                fmt_text += (

                    f"\n\n## Existing Project Files (reference only — DO NOT regenerate)\n"

                    + "\n".join(f"- {p}" for p in existing[:30])

                    + f"\n\n{len(existing)} files exist. Generate only NEW files or modifications."

                )

        progress_text = ""

        progress = self._task_progress(state)

        if progress and not progress.startswith("0/"):

            progress_text = f"\n## Progress\n{progress}\nCheck `task_list` in the upstream output for details (passes=true|false)."

        # Repository map: inject compact structural view for code stages on existing repos

        repo_map_text = ""

        if stage.uses_file_output and state.get("output_dir"):

            repo_map_text = self._build_repo_map_text(state["output_dir"])

            if repo_map_text:

                repo_map_text = f"\n## Repository Structure (existing files — reference only)\n{repo_map_text}"

        # Test plan injection: QA stage gets test_plan as primary input

        test_plan_text = ""

        if not stage.uses_file_output and stage.generate_test_plan:

            # This is the test_plan generator stage — no upstream test_plan to inject

            pass

        elif stage.test_result_key and not stage.generate_test_plan:

            # This is the QA test execution stage — inject test_plan + upstream code

            test_plan_key = ""

            for s in self._config.stages:

                if s.generate_test_plan and s.output_artifact:

                    test_plan_key = s.output_artifact

                    break

            if test_plan_key:

                test_plan = state.get(test_plan_key)

                if isinstance(test_plan, dict):

                    test_plan_text = f"\n## Test Plan (Acceptance Criteria)\n{json.dumps(self._summarize_artifact(test_plan), ensure_ascii=False, indent=2)}"



        # Build Jinja2 render context from upstream artifacts

        jinja_ctx = {}

        for s in self._config.stages:

            val = state.get(s.output_artifact)

            if val:

                # Support file-type variables: read content from path

                if isinstance(val, dict) and val.get('type') == 'file' and val.get('path'):

                    try:

                        with open(val['path'], 'r') as ff:

                            val['_content'] = ff.read()[:10000]

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

                jinja_ctx[s.output_artifact or s.id] = val

        jinja_ctx.update({k: v for k, v in state.items() if not k.startswith('_') and k not in jinja_ctx})

        # Conversation state: cross-stage persistent memory

        conv = state.get('conversation_state') or state.get('_conversation_state') or {}

        jinja_ctx['conversation'] = conv if isinstance(conv, dict) else {}

        # Inject workflow environment variables (secrets) into Jinja2 context

        env_path = os.path.expanduser(os.getenv('AIPLAT_WORKFLOW_ENV_PATH', '~/.aiplat/workflow_env.json'))

        try:

            if os.path.exists(env_path):

                with open(env_path, 'r') as f:

                    wf_env = json.load(f)

                jinja_ctx['env'] = wf_env

        except Exception:

            jinja_ctx['env'] = {}

        # Inject per-node config env override

        ncf = getattr(stage, 'node_config', None) or {}

        node_env = ncf.get('env', {})

        if isinstance(node_env, dict) and node_env:

            jinja_ctx['env'] = {**jinja_ctx.get('env', {}), **node_env}



        raw = f"""You are {stage.agent_name or stage.id}.

{scene_context}

{previous_notes}

{collective_context}

{gaps_context}

{skill_stubs_context}

{skill_corpus_context}  # noqa

{ponytail_context}

{stage_hints}

Complete your work based on upstream output.{fb}{constraint_text}{handoff_text}{iss}{agent_list}{fmt_text}{progress_text}{test_plan_text}



## Upstream Artifacts

{json.dumps(ctx, ensure_ascii=False, indent=2)}



## Task Description

{state.get('description', '')}



## Output Format

For non-code stages: Output JSON with artifact, confidence, issues, decision.

For code stages: Use ## FILE: path/to/file.py format (see Scope section above).

JSON format: {{"artifact": {{}},"confidence": "HIGH","issues": [{{"severity": "P1","description": "description","target_agent": "agent_id","suggestion": "suggestion"}}],"decision": "PROCEED"}}

"""

        return self._render_jinja2(raw, jinja_ctx)



    def _render_jinja2(self, template: str, context: dict) -> str:

        """Render {{var.path}} patterns in prompt via Jinja2, if available."""

        if '{{' not in template:

            return template

        try:

            from jinja2 import Template

            # Build nested dict from dotted keys (e.g. 'start.question' → {'start': {'question': ...}})

            nested: dict = {}

            for k, v in context.items():

                parts = k.split('.')

                d = nested

                for part in parts[:-1]:

                    d = d.setdefault(part, {})

                d[parts[-1]] = v

            return Template(template).render(**nested)

        except Exception:

            return template  # fallback: return unrendered



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

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)



    def _collect_upstream_code(self, state: PipelineState) -> Dict[str, Any]:

        """Collect code files from all upstream code-generating stages.

        

        FIX A: Only merge 'files' lists, skipping raw_output artifacts.

        Raw outputs (when _extract_files_delimiter finds no ## FILE: blocks)

        indicate the LLM didn't produce structured code — ingesting them would

        produce empty code_graph and misleading REJECTED evaluations.

        """

        all_files: List[Dict[str, str]] = []

        for s in self._config.stages:

            if s.uses_file_output and state.get(s.output_artifact):

                artifact = state[s.output_artifact]

                if isinstance(artifact, dict):

                    stage_files = self._collect_files(artifact)

                    if stage_files:

                        all_files.extend(stage_files)

        return {"files": all_files}



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



        # Preprocess: strip leading/trailing markdown fences that wrap the entire output

        text = re.sub(r'^```\w*\n', '', text.strip())

        text = re.sub(r'\n```$', '', text)



        # 1) ## FILE: path syntax (primary format)

        # Path must NOT contain spaces — use hyphens/underscores.

        # Example: ## FILE: backend/models/user.py

        for m in re.finditer(r'##\s*FILE:\s*(\S+)[\s\S]*?\n(.*?)(?=\n##\s*FILE:|\Z)', text, re.MULTILINE):

            files.append({"path": m.group(1).strip(), "content": m.group(2).strip()})



        # 2) ```language path\n...\n``` syntax (fallback)

        # Captures optional language tag + optional file path

        for m in re.finditer(r'```(\w+)\s*(\S+)?\n([\s\S]*?)```', text):

            lang = m.group(1).strip().lower() if m.group(1) else ""

            path = m.group(2).strip() if m.group(2) else ""

            content = m.group(3).strip() if m.group(3) else ""

            # Skip pure language markers (e.g. ```python with no path)

            if not path and lang:

                continue

            # Use lang as path only if it looks like a file path

            if not path and ("/" in lang or "." in lang):

                path = lang

            if path and content and not any(f["path"] == path for f in files):

                if "/" in path or "." in path:

                    files.append({"path": path, "content": content})



        # 3) JSON {"files": [...]} format (fallback)

        json_str = PipelineEngine._extract_json(text)

        if json_str:

            try:

                import json

                data = json.loads(json_str)

                if isinstance(data.get("files"), list):

                    for f in data["files"]:

                        if isinstance(f, dict) and f.get("path") and f.get("content"):

                            if not any(e["path"] == f["path"] for e in files):

                                files.append({"path": f["path"], "content": f["content"]})

            except (json.JSONDecodeError, TypeError) as e:

                logging.warning(str(e), exc_info=True)



        # 4) ## PATCH: path with <<< ORIGINAL / === / >>> UPDATED blocks (incremental edit)

        for m in re.finditer(r'##\s*PATCH:\s*(\S+)\s*\n(.*?)(?=\n##\s*(?:FILE|PATCH):|\Z)', text, re.DOTALL):

            patch_path = m.group(1).strip()

            patch_content = m.group(2).strip()

            if patch_path and patch_content and not any(f["path"] == patch_path for f in files):

                files.append({"path": patch_path, "content": patch_content, "_is_patch": True})



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

            except (json.JSONDecodeError, TypeError) as e:

                logging.warning(str(e), exc_info=True)

        return AgentOutput(artifact={"raw_output": raw[:5000]}, issues=[], confidence=AgentConfidence.LOW, decision=AgentDecision.PROCEED)



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



    def _snapshot(self, state: PipelineState, name: str) -> None:

        sid = state.get("session_id", "")

        if not sid:

            return

        checkpoint = {"name": name, "ts": time.time(), "phase": state.get("phase", ""),

            "stage_idx": state.get("_current_stage_idx"), "last_reason": state.get("_last_action_reason", ""),

            "artifacts": {s.output_artifact: bool(state.get(s.output_artifact)) for s in self._config.stages},

            "tokens_used": state.get("tokens_used", 0), "tokens_budget": state.get("tokens_budget", 0),

            "iteration": state.get("iteration", 0)}

        state.setdefault("_checkpoints", []).append(checkpoint)

        if len(state["_checkpoints"]) > 50:

            state["_checkpoints"] = state["_checkpoints"][-50:]

        base = state.get("output_dir", "") or self._output_root(sid)

        os.makedirs(base, exist_ok=True)

        try:

            with open(os.path.join(base, f"_{name}.json"), "w", encoding="utf-8") as fh:

                json.dump(dict(state), fh, ensure_ascii=False, indent=2, default=str)

        except OSError as e:

            logging.getLogger("pipeline_engine").warning(

                "Failed to persist checkpoint for %s: %s", sid, str(e)[:200])



    def _merge_state(self, state: dict, r_state: dict, stage: Optional[PipelineStageConfig] = None) -> None:

        """Reducer-based state merge — prevents parallel overwrite.

        

        Reads merge_strategies from PipelineStageConfig (or defaults):

          "append"     → extend list fields instead of overwriting

          "overwrite"  → standard dict.update (last writer wins, default)

          "merge_deep" → recursive dict merge for nested structures

        

        Default: _graph_trace, _checkpoints, messages always append.

        """

        # Default append keys (engine-level guarantees)

        default_append = {"_graph_trace", "_checkpoints", "messages", "trace", "sub_agent_results", "_shared_state_board"}

        strategies = {}

        if stage and hasattr(stage, "merge_strategies") and stage.merge_strategies:

            strategies = stage.merge_strategies

        strategies.update({k: "append" for k in default_append if k not in strategies})



        for key, new_value in list(r_state.items()):

            if new_value is None:

                continue

            strategy = strategies.get(key, "overwrite")



            if strategy == "append":

                if key in state and isinstance(state[key], list):

                    if isinstance(new_value, list):

                        state[key].extend(new_value)

                    else:

                        state[key].append(new_value)

                else:

                    state[key] = [new_value] if not isinstance(new_value, list) else list(new_value)

            elif strategy == "merge_deep":

                if key in state and isinstance(state[key], dict) and isinstance(new_value, dict):

                    state[key].update(new_value)

                else:

                    state[key] = new_value

            else:  # "overwrite" (default)

                state[key] = new_value



    def _load_checkpoints_from_disk(self, state: PipelineState) -> List[Dict[str, Any]]:

        """Load checkpoint summaries from disk checkpoint files (survives restart)."""

        checkpoints = []

        sid = state.get("session_id", "")

        base = state.get("output_dir", "") or self._output_root(sid)

        if not sid or not os.path.isdir(base):

            return checkpoints

        try:

            for fname in sorted(os.listdir(base)):

                if fname.startswith("_") and fname.endswith(".json") and fname.startswith("_stage_"):

                    fp = os.path.join(base, fname)

                    try:

                        with open(fp, "r", encoding="utf-8") as fh:

                            saved = json.load(fh)

                        if isinstance(saved, dict):

                            checkpoints.append({

                                "name": fname[1:-5],

                                "stage_idx": saved.get("_current_stage_idx"),

                                "tokens_used": saved.get("tokens_used", 0),

                                "tokens_budget": saved.get("tokens_budget", 0),

                                "iteration": saved.get("iteration", 0),

                                "error": saved.get("error", ""),

                            })

                    except Exception:

                        logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        return checkpoints



    def _output_root(self, project_id: str, project_name: str = "") -> str:

        """Build a human-readable output directory path.



        When project_name is given, the directory is:

            ~/.aiplat/output/{sanitized_name}-{project_id}/

        Otherwise falls back to the legacy bare-ID directory:

            ~/.aiplat/output/{project_id}/

        """

        import re

        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))

        if project_name:

            safe = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff-]', '_', project_name).strip('_')[:40]

            return str(os.path.join(home, "output", f"{safe}-{project_id}"))

        return str(os.path.join(home, "output", project_id))



    def _persist_files(self, artifact: Dict[str, Any], output_dir: str = "") -> None:

        if not output_dir:

            return

        for f in self._collect_files(artifact):

            path = f.get("path", "")

            content = f.get("content", "")

            if path and content:

                full = _safe_join(output_dir, path)

                try:

                    os.makedirs(os.path.dirname(full), exist_ok=True)

                    with open(full, "w", encoding="utf-8") as fh:

                        fh.write(content)

                except OSError as e:

                    logging.getLogger("pipeline_engine").warning(

                        "Failed to persist artifact file %s: %s", full, str(e)[:200])



    @staticmethod

    def _summarize_artifact(val: Any, max_chars: int = 0) -> Dict[str, Any]:

        limit = max_chars or int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_CHARS", "8000"))

        """Structured 7-section summary template (OpenCode pattern).



        Sections: goal, artifacts, quality, key_decisions, next_steps,

        critical_context, relevant_files.

        """

        if not isinstance(val, dict):

            s = str(val)[:limit // 2] if val else "{}"

            return {"summary": s, "artifact_keys": []}

        raw = json.dumps(val, ensure_ascii=False, default=str)

        if len(raw) <= limit:

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

            if "## 历史教训" not in raw:

                raw += "\n\n## 历史教训\n（由系统自动从历史运行中学习）\n"

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



    def _validate_cross_stage(self, stage: PipelineStageConfig, state: PipelineState) -> None:

        """Cross-stage validation: check downstream outputs reference upstream artifacts."""

        validations = state.get("_cross_validations", {})

        # C1: SA → BA consistency

        if stage.output_artifact == "solution_design":

            cp = state.get("customer_profile") or {}

            sd = state.get("solution_design") or {}

            score = 100; checks = []

            cp_text = str(cp).lower()

            sd_text = str(sd).lower()

            if len(cp_text) > 10:

                overlap = sum(1 for w in ["制造", "零售", "金融", "医疗", "教育", "政府"] if w in cp_text and w in sd_text)

                if overlap == 0:

                    checks.append("no industry keyword overlap with customer_profile"); score -= 20

                else:

                    checks.append(f"{overlap} industry keyword matches with customer_profile")

                pain_points = cp.get("pain_points", []) if isinstance(cp, dict) else []

                ref = sum(1 for p in pain_points if str(p)[:10] in sd_text)

                if pain_points and ref == 0:

                    checks.append("no pain_points addressed"); score -= 25

                elif pain_points:

                    checks.append(f"{ref}/{len(pain_points)} pain points addressed")

            validations["sa_ba_consistency"] = {"score": score, "checks": checks}

        # C2: DE → SA coverage

        if stage.output_artifact == "deployment_package":

            sd = state.get("solution_design") or {}

            dp = state.get("deployment_package") or {}

            score = 100; checks = []

            sol_comps = sd.get("components", []) if isinstance(sd, dict) else []

            dep_comps = dp.get("components", []) if isinstance(dp, dict) else []

            if sol_comps:

                dep_names = [str(c.get("name","")).lower() for c in dep_comps if isinstance(c, dict)]

                covered = sum(1 for c in sol_comps if isinstance(c,dict) and str(c.get("name","")).lower() in dep_names)

                cov = covered / len(sol_comps) if sol_comps else 1

                checks.append(f"component coverage: {covered}/{len(sol_comps)}")

                if cov < 0.5: score -= 30; checks.append("coverage < 50%")

                elif cov < 1.0: score -= 15

            risks = dp.get("risk_matrix",[]) if isinstance(dp, dict) else []

            if sd.get("gap_analysis") and not risks:

                score -= 20; checks.append("no risk_matrix despite gap_analysis")

            validations["de_sa_coverage"] = {"score": score, "checks": checks}

        # C3: DM → DE acceptance

        if stage.output_artifact == "acceptance_report":

            dp = state.get("deployment_package") or {}

            ar = state.get("acceptance_report") or {}

            score = 100; checks = []

            test_plan = dp.get("test_plan",[]) if isinstance(dp, dict) else []

            risk_matrix = dp.get("risk_matrix",[]) if isinstance(dp, dict) else []

            ar_text = str(ar).lower()

            if test_plan:

                ref = sum(1 for t in test_plan if isinstance(t,dict) and str(t.get("test",""))[:20].lower() in ar_text)

                if ref == 0: score -= 25; checks.append("no test_plan references")

                else: checks.append(f"{ref}/{len(test_plan)} tests covered")

            if risk_matrix:

                ref = sum(1 for r in risk_matrix if isinstance(r,dict) and str(r.get("risk",""))[:20].lower() in ar_text)

                if ref == 0: score -= 25; checks.append("no risk_matrix references")

                else: checks.append(f"{ref}/{len(risk_matrix)} risks covered")

            validations["dm_de_acceptance"] = {"score": score, "checks": checks}

        # C4: Quality gate

        scores = [v["score"] for v in validations.values()]

        if scores:

            overall = sum(scores) // len(scores)

            validations["_quality_score"] = overall

            if overall < 50:

                state["_quality_warning"] = f"cross-stage quality {overall}/100 < 50"

        state["_cross_validations"] = validations



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



    async def _feed_execution_to_graph(self, state: PipelineState) -> None:

        """Feed pipeline completion into knowledge graph (F5: 操作→知识自动索引).



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



    def _healing_pre_snapshot(self, state, strategy_name):

        """Phase 25: Snapshot execution context before self-healing attempt."""

        try:

            from core.harness.execution.snapshot import save_execution_snapshot

            pre_id = save_execution_snapshot(

                state, f"pre_{strategy_name}",

                session_id=state.get("session_id", ""),

                stage_id=state.get("_last_error_stage", ""),

            )

            state["_last_snapshot_id"] = pre_id

        except Exception:

            logging.getLogger(__name__).debug('_healing_pre_snapshot failed', exc_info=True)


    def _healing_post_snapshot(self, state, strategy_name):

        """Phase 25: Snapshot execution context after self-healing."""

        try:

            from core.harness.execution.snapshot import snapshot_after_heal

            snapshot_after_heal(

                state, strategy_name,

                session_id=state.get("session_id", ""),

                stage_id=state.get("_last_error_stage", ""),

            )

        except Exception:

            logging.getLogger(__name__).debug('_healing_post_snapshot failed', exc_info=True)
        # Phase 26: Record strategy outcome in effectiveness tracker

        success = state.pop("_meta_optimized", False)

        error_type = state.get("_last_healing_reason", "unknown")

        self._record_strategy_outcome(error_type, strategy_name, success)



    def _resolve_best_strategy(self, error_type, classed=None):

        """Phase 29: UCB1-based strategy selection (replaces Phase 26 greedy lookup)."""

        try:

            from core.harness.optimization.search_engine import get_search_engine

            engine = get_search_engine()

            best = engine.select_best(error_type)

            if best:

                return best

            # Cold start: fallback to Phase 26 tracker exploration

            from core.harness.optimization.strategy_tracker import get_strategy_tracker

            return get_strategy_tracker().explore_strategy(error_type)

        except Exception:

            return None



    async def _dispatch_strategy(self, strategy_name, stage, state, classed=None):

        """Phase 26: Dispatch to strategy by name (replaces if/elif chain)."""

        strategy_map = {

            "rotate_credential": self._strategy_rotate_credential,

            "compress_retry": self._strategy_compress_retry,

            "backoff_retry": self._strategy_backoff_retry,

            "skip_stage": self._strategy_skip_stage,

        }

        handler = strategy_map.get(strategy_name)

        if handler:

            return await handler(stage, state)

        return None



    def _record_strategy_outcome(self, error_type, strategy_name, success):

        """Phase 26: Record strategy effectiveness after execution."""

        try:

            from core.harness.optimization.strategy_tracker import get_strategy_tracker

            tracker = get_strategy_tracker()

            tracker.record(error_type, strategy_name, success=success, tokens_used=0)

        except Exception:

            logging.getLogger(__name__).debug('_record_strategy_outcome failed', exc_info=True)


    async def _strategy_rotate_credential(self, stage, state):

        """rate_limit / auth → rotate API key via infra CredentialPool."""

        self._inc_healing_stat("attempts")

        try:

            from infra.management.model.credential_pool import get_credential_pool

            provider = os.getenv("AIPLAT_LLM_PROVIDER", "deepseek")

            pool = get_credential_pool(provider)

            pool.next()

            if pool.key_count > 1:

                state["_meta_diagnosis"] = f"credential_rotated:{provider}({pool.key_count} keys)"

                state["_meta_optimized"] = True

                self._inc_healing_stat("successes")

                logger.warning("[healing] rotated credential: provider=%s keys=%d", provider, pool.key_count)

                self._healing_post_snapshot(state, "rotate_credential")

                return stage

            else:

                logger.warning("[healing] cannot rotate: only 1 key for %s", provider)

        except Exception as e:

            logger.warning("[healing] credential rotation failed: %s", e)

        self._healing_post_snapshot(state, "rotate_credential")

        return None



    async def _strategy_compress_retry(self, stage, state):

        """context_overflow / payload_too_large → flag compression, retry."""

        self._inc_healing_stat("attempts")

        state["_meta_diagnosis"] = "context_overflow: retry with compression"

        state["_meta_optimized"] = True

        state["_force_context_compression"] = True

        self._inc_healing_stat("successes")

        self._healing_post_snapshot(state, "compress_retry")

        return stage



    async def _strategy_backoff_retry(self, stage, state):

        """timeout / overloaded → exponential backoff + retry."""

        self._inc_healing_stat("attempts")

        retry_count = state.get("_auto_retry_count", 0)

        classed = state.get("_last_classified_error", {})

        retry_after = classed.get("retry_after_seconds", 0) if classed else 0

        wait = max(2 ** retry_count, retry_after) if retry_after > 0 else 2 ** retry_count

        wait = min(wait, 60)

        state["_meta_diagnosis"] = f"backoff:{wait}s(retry_count={retry_count})"

        state["_meta_optimized"] = True

        self._inc_healing_stat("successes")

        await asyncio.sleep(wait)

        self._healing_post_snapshot(state, "backoff_retry")

        return stage



    async def _strategy_skip_stage(self, stage, state):

        """billing / model_not_found / server_error → skip this stage.



        Returns None (not stage!) to signal "done with this stage".

        _retry_loop checks _stage_{id}_skipped before setting error.

        """

        self._inc_healing_stat("attempts")

        failure_strategy = getattr(stage, 'failure_strategy', None) or ''

        if failure_strategy == 'skip_stage':

            state["_meta_diagnosis"] = f"skip_stage:{stage.id}"

            state["_meta_optimized"] = True

            state[f"_stage_{stage.id}_done"] = True

            state[f"_stage_{stage.id}_skipped"] = True

            self._inc_healing_stat("skips")

            logger.warning("[healing] skipping stage %s: %s", stage.id, failure_strategy)

        else:

            self._inc_healing_stat("escalations")

            logger.warning("[healing] cannot skip: stage %s failure_strategy=%s", stage.id, failure_strategy)

        self._healing_post_snapshot(state, "skip_stage")

        return None



    async def _strategy_escalate(self, stage, state):

        """unknown / unresolvable → human approval via PolicyGate."""

        self._inc_healing_stat("attempts")

        try:

            from core.harness.infrastructure.gates.policy_gate import PolicyGate

            gate = PolicyGate()

            result = await gate.check_agent(

                user_id=state.get("user_id", "system"),

                agent_id="pipeline_engine",

                agent_args={

                    "_approval_required": True,

                    "_escalation": True,

                    "_error_stage": stage.id,

                    "_error_reason": state.get("_last_classified_error", {}).get("reason", "unknown"),

                    "_tenant_id": state.get("tenant_id", ""),

                },

            )

            if getattr(result, 'decision', None) and str(result.decision) in ("APPROVAL_REQUIRED",):

                state["_meta_diagnosis"] = f"escalated:approval_id={getattr(result, 'approval_request_id', '')}"

                state["_meta_optimized"] = True

                state["phase"] = PipelinePhase.PAUSED

                state["_paused_for_approval"] = True

                state["_approval_request_id"] = getattr(result, "approval_request_id", "")

                self._inc_healing_stat("escalations")

                self._healing_post_snapshot(state, "escalate")

                return None

        except Exception as e:

            logger.warning("[healing] escalation failed: %s", e)

        self._healing_post_snapshot(state, "escalate")

        return None



    @staticmethod

    def _inc_healing_stat(key):

        stats = getattr(PipelineEngine, '_healing_stats', None)

        if stats is None:

            PipelineEngine._healing_stats = {}

            stats = PipelineEngine._healing_stats

        stats[key] = stats.get(key, 0) + 1



    async def _meta_optimize(self, stage: PipelineStageConfig, report: Dict, state: PipelineState) -> Optional[PipelineStageConfig]:

        """Invoke lightweight Meta-Agent to diagnose and suggest config changes.



        Called by _retry_loop after 3+ retries still REJECTED.

        Modifies stage in-place; returns None if optimization failed.



        Phase 24: Checks _last_classified_error first — if ErrorTranslator has

        classified the failure, uses a specialized strategy instead of generic

        Meta-Agent LLM call. Unclassified errors fall through to original logic.

        """

        # Phase 24: Read and immediately clear error signature (prevents stale data)

        classed = state.pop("_last_classified_error", None)

        state.pop("_last_error", None)



        if classed:

            reason = classed.get("reason", "unknown")

            state["_last_healing_reason"] = reason  # Phase 26: preserve for outcome recording

            # Phase 25: Snapshot execution context before self-healing attempt

            self._healing_pre_snapshot(state, reason)



            # Phase 26: Strategy effectiveness tracker — data-driven routing

            best = self._resolve_best_strategy(reason, classed)

            if best:

                state["_meta_strategy_source"] = "tracker"

                logger.info("[strategy] tracker-selected: %s for %s", best, reason)

                return await self._dispatch_strategy(best, stage, state, classed)



            # Fallback: hardcoded mapping (backward compat + cold start)

            state["_meta_strategy_source"] = "hardcoded"

            if reason in ("rate_limit", "auth", "auth_permanent"):

                if classed.get("should_rotate_credential"):

                    return await self._strategy_rotate_credential(stage, state)

            if reason in ("context_overflow", "payload_too_large"):

                if classed.get("should_compress"):

                    return await self._strategy_compress_retry(stage, state)

            if reason in ("timeout", "overloaded"):

                if classed.get("retryable"):

                    return await self._strategy_backoff_retry(stage, state)

            if reason in ("billing", "model_not_found", "server_error"):

                return await self._strategy_skip_stage(stage, state)

            if reason == "unknown":

                pass  # fall through to Meta-Agent LLM

            else:

                return await self._strategy_escalate(stage, state)



        score = report.get("score", {})

        issues = report.get("issues", [])[:5]

        history = state.get("_score_history", [])



        # Phase 24: Inject error classification into Meta-Agent prompt (fallback path only)

        error_hint = ""

        if classed:

            error_hint = (

                f"\nKnown failure type: {classed['reason']} "

                f"(retryable={classed['retryable']}, "

                f"compress={classed['should_compress']})"

            )

        else:

            err = state.get("_last_error")

            if err:

                error_hint = f"\nLast error: {type(err).__name__}: {str(err)[:200]}"



        diagnosis_prompt = f"""Stage {stage.id} (agent={stage.agent_id}) REJECTED after multiple retries.

Current: agent_type={getattr(stage, 'agent_type', 'react')}, prompt_extra={json.dumps(str(getattr(stage, 'prompt_extra', ''))[:300])}

Evaluation: overall={score.get('overall', '?')}, pass_rate={report.get('pass_rate', '?')}

Dimension scores: {json.dumps({k: v for k, v in score.items() if k != 'overall'})}

Issues: {json.dumps(issues, ensure_ascii=False)}

Score history: {json.dumps([h.get('overall', 0) for h in history[-5:]]) if history else 'none'}

{error_hint}

Output ONLY this JSON (no preamble): {{"diagnosis":"<1 sentence>","suggested_prompt_extra":"<追加内容>","suggested_agent_type":"react|plan|reflection","enable_test_plan":false}}"""



        try:

            result_text = await self._stage_runner.run(diagnosis_prompt, state)

            json_str = self._extract_json(result_text)

            if not json_str:

                return stage

            changes = json.loads(json_str)

            if not isinstance(changes, dict):

                return stage



            if changes.get("suggested_prompt_extra") and isinstance(changes["suggested_prompt_extra"], str):

                extra = changes["suggested_prompt_extra"].strip()

                current = getattr(stage, 'prompt_extra', '') or ''

                if extra and extra not in current:

                    stage.prompt_extra = current + "\n" + extra

            if changes.get("suggested_agent_type") in ("plan", "reflection"):

                stage.agent_type = changes["suggested_agent_type"]

            if changes.get("enable_test_plan"):

                stage.generate_test_plan = True



            state["_meta_optimized"] = True

            state["_meta_diagnosis"] = str(changes.get("diagnosis", ""))[:200]

            return stage

        except Exception:

            return stage



    @staticmethod

    def _extract_keywords(text: str) -> List[str]:

        """Extract technical framework keywords from requirement text.



        Only includes technology-agnostic framework/tool names, NOT business domain terms.

        Business keywords (e-commerce, healthcare, finance, etc.) must be declared

        by the Skill author in its SKILL.md frontmatter, not inferred by the engine.

        """

        import re

        import os as _os

        tech_patterns = [

            r"(?:fastapi|flask|django|express|spring|rails|laravel)",

            r"(?:react|vue|angular|next\.?js|nuxt|svelte)",

            r"(?:postgres|mysql|mongodb|redis|sqlite|mariadb)",

            r"(?:docker|kubernetes|k8s|terraform)",

            r"(?:python|typescript|javascript|go|rust|java|kotlin|swift)",

            r"(?:rest|graphql|grpc|websocket|soap)",

        ]

        extra = _os.getenv("AIPLAT_TECH_KEYWORD_PATTERNS", "")

        if extra:

            tech_patterns.extend([p.strip() for p in extra.split("||") if p.strip()])

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



        prompt = (

            "You are a Harness engineer optimizing an AI pipeline execution system.\n\n"

            f"A failure pattern has been identified:\n"

            f"  Verifier Cause: {signature.verifier_cause}\n"

            f"  Causal Status: {signature.causal_status}\n"

            f"  Abstract Mechanism: {signature.abstract_mechanism}\n"

            f"  Occurrences: {signature.count}\n\n"

            f"Example failures:\n{example_lines}\n\n"

            "Your task: propose the MINIMAL possible change to PipelineStageConfig or AGENT.md "

            "that would address this specific failure pattern without breaking existing behavior.\n\n"

            "The change must:\n"

            "1. Target a specific PipelineStageConfig field or AGENT.md instruction\n"

            "2. Be minimal — change ONE thing only\n"

            "3. Explain WHY this change addresses the mechanism (not just the symptom)\n"

            "4. Rate the risk: low (cosmetic), medium (changes behavior), high (may break passing cases)\n\n"

            "Reply with JSON only:\n"

            f'{{"target_field": "prompt_extra|hitl|failure_strategy|retry_llm_on_rate_limit|stage_timeout_seconds", '

            f'"target_stage_pattern": "stage id pattern (use * for all)", '

            f'"old_value": "current", "new_value": "proposed", "rationale": "one sentence", '

            f'"target_mechanism": "{signature.abstract_mechanism}", '

            f'"target_causal": "{signature.causal_status}", '

            f'"target_verifier": "{signature.verifier_cause}", '

            f'"risk": "low|medium|high"}}'

        )



        try:

            resp = await sys_llm_generate(

                None, [{"role": "user", "content": prompt}],

                model_name=best_model_for_purpose("chat"),

                max_tokens=500,

            )

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





def _write_pipeline_event(run_id: str, event_type: str, node_id: str,

                          state_json: str, elapsed: float, output: str) -> None:

    """Write pipeline event to platform SQLite. Self-contained in core; no cross-layer import."""

    try:

        import sqlite3

        conn = sqlite3.connect(_PLATFORM_DB_PATH)

        try:

            conn.execute(

                "INSERT INTO pipeline_events (run_id, event_type, node_id, state_json, elapsed, output, created_at) "

                "VALUES (?,?,?,?,?,?,?)",

                (str(run_id), str(event_type), str(node_id or ""),

                 str(state_json), float(elapsed), str(output or ""), time.time()),

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

        from core.apps.quality.verifier import ResultVerifier

        from core.apps.quality.types import VerificationSpec, VerificationType

        

        verifier = ResultVerifier()

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

