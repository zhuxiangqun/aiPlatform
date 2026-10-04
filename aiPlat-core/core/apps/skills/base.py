import logging
"""
Skill Base Module

Provides base Skill class implementing ISkill interface.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ...harness.interfaces import (
    ISkill,
    SkillConfig,
    SkillContext,
    SkillResult,
)
from core.harness.utils.model_injection import best_model_for_purpose


@dataclass
class SkillMetadata:
    """Skill metadata with rich fields for Agent Skill mode"""
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    # Extended fields for Agent Skill mode
    display_name: str = ""
    capabilities: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[Dict[str, str]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name


class BaseSkill(ISkill):
    """
    Base Skill Implementation
    
    Provides common functionality for all skill implementations.
    """

    def __init__(self, config: SkillConfig):
        self._config = config

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """Execute skill - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement execute")

    async def validate(self, params: Dict[str, Any]) -> bool:
        """Validate parameters - to be implemented by subclass"""
        return True

    def get_config(self) -> SkillConfig:
        """Get skill configuration"""
        return self._config

    def get_input_schema(self) -> Dict[str, Any]:
        """Get input schema"""
        return self._config.input_schema

    def get_output_schema(self) -> Dict[str, Any]:
        """Get output schema"""
        return self._config.output_schema

    def to_dict(self) -> Dict[str, Any]:
        """Export skill configuration as dict for Playbook serialization."""
        cfg = self._config
        return {
            "name": cfg.name,
            "version": cfg.version or "1.0.0",
            "description": getattr(cfg, "description", ""),
            "category": getattr(cfg, "category", "general"),
            "input_schema": getattr(cfg, "input_schema", {}),
            "output_schema": getattr(cfg, "output_schema", {}),
            "tags": getattr(cfg, "tags", []),
            "metadata": getattr(cfg, "metadata", {}),
        }


class TextGenerationSkill(BaseSkill):
    """
    Text Generation Skill
    
    Generates text based on prompt.
    """

    def __init__(self):
        config = SkillConfig(
            name="text_generation",
            description="Generate text based on prompt",
            input_schema={
                "prompt": {"type": "string", "description": "Input prompt"},
                "max_tokens": {"type": "integer", "description": "Max tokens to generate", "default": 500},
                "temperature": {"type": "number", "description": "Temperature", "default": 0.7}
            },
            output_schema={
                "text": {"type": "string", "description": "Generated text"},
                "usage": {"type": "object", "description": "Token usage"}
            }
        )
        super().__init__(config)
        self._model = None

    def set_model(self, model: Any) -> None:
        """Set model for skill"""
        self._model = model

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """Execute text generation"""
        if not self._model:
            return SkillResult(
                success=False,
                error="No model configured"
            )
        
        prompt = params.get("prompt", "")
        
        try:
            from ...harness.syscalls.llm import sys_llm_generate

            from core.harness.utils.execute_session import skill_nested_llm_trace_context

            response = await sys_llm_generate(
                self._model,
                [{"role": "user", "content": prompt}],
                trace_context=skill_nested_llm_trace_context(
                    context, params, source="skill_base"
                ),
            )
            
            return SkillResult(
                success=True,
                output={
                    "text": response.content,
                    "usage": response.usage
                },
                metadata={"model": response.model}
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e)
            )


class CodeGenerationSkill(BaseSkill):
    """
    Code Generation Skill
    
    Generates code based on requirements.
    """

    def __init__(self):
        config = SkillConfig(
            name="code_generation",
            description="Generate code based on requirements",
            # Nested LLM asks for up to 420s; outer skill wait must keep headroom
            # (was SKILL.md timeout — keep here so engine SKILL.md stays untouched).
            timeout=540,
            input_schema={
                "requirements": {"type": "string", "description": "Code requirements"},
                "language": {"type": "string", "description": "Programming language"},
                "framework": {"type": "string", "description": "Framework (optional)"}
            },
            output_schema={
                "code": {"type": "string", "description": "Generated code"},
                "language": {"type": "string", "description": "Language"}
            },
            metadata={"timeout": 540},
        )
        super().__init__(config)
        self._model = None

    def set_model(self, model: Any) -> None:
        """Set model for skill"""
        self._model = model

    @staticmethod
    def _strip_done_prefix(text: str) -> str:
        """Normalize DONE / DONE: / DONEn (mangled newline) prefixes from weak models."""
        import re

        s = str(text or "").strip()
        s = re.sub(r"^(?:DONE\s*:?\s*|DONEn)", "", s, count=1, flags=re.I).strip()
        return s

    @staticmethod
    def _has_code_substance(text: str) -> bool:
        """True when body has real implementation — not clarify prose mentioning 'class'."""
        try:
            from core.management.execution_quality_review import _code_body_has_substance

            return bool(_code_body_has_substance(text))
        except Exception:
            import re

            s = CodeGenerationSkill._strip_done_prefix(text)
            body = re.sub(r"(?m)^##\s*FILE:\s*\S+\s*$", "", s)
            body = re.sub(r"(?m)^```\w*\s*$", "", body).strip()
            if len(body) < 40:
                return False
            # Fallback: require code-shaped tokens (def name(, class Name:)
            return bool(
                re.search(
                    r"(?:"
                    r"\b(?:async\s+)?def\s+\w+\s*\(|"
                    r"\bclass\s+\w+\s*[\(:]|"
                    r"\bfunction\s+\w+\s*\(|"
                    r"\bconst\s+\w+\s*=|"
                    r"@router\.|APIRouter|BaseModel|FastAPI|"
                    r"\bcurl\s+|"
                    r"app\.(?:get|post|put|delete|patch)\("
                    r")",
                    body,
                    re.I,
                )
            )

    @staticmethod
    def _resolve_requirements(params: Dict[str, Any]) -> str:
        """ReAct/sys_skill often passes the user task as ``input``, not ``requirements``."""
        if not isinstance(params, dict):
            return ""
        for key in (
            "requirements",
            "requirement",
            "message",
            "input",
            "query",
            "task",
            "user_task",
            "prompt",
            "text",
        ):
            v = params.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                nested = CodeGenerationSkill._resolve_requirements(v)
                if nested:
                    return nested
        return ""

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """Execute code generation using best-available LLM via model_injection."""
        language = params.get("language", "python") if isinstance(params, dict) else "python"
        _lang_locked = bool(
            (params if isinstance(params, dict) else {}).get("_language_locked")
        )
        requirements = self._resolve_requirements(params if isinstance(params, dict) else {})
        if not requirements:
            return SkillResult(
                success=False,
                error=(
                    "code_generation missing requirements/input — "
                    "pass the user task (ReAct usually sets params.input)."
                ),
            )

        # Prefer language demanded by the user task over schema default ``python``
        # (run-2e2d49539faf: TS client generated but envelope stayed language=python → false thin).
        # When loop injected preferred_language with ``_language_locked``, do not
        # re-infer here — inject already applied task > preferred > model.
        if not _lang_locked:
            try:
                from core.management.execution_quality_review import (
                    _detect_requested_code_language,
                )

                req_lang = _detect_requested_code_language(requirements)
                if req_lang:
                    language = req_lang
            except Exception:
                logging.getLogger(__name__).debug(
                    "code_generation language infer skipped", exc_info=True
                )

        # Auto-select model: via model_injection (canonical path), fall back to env config
        model = self._model
        if model is None:
            model = await self._resolve_code_gen_model()
        if model is None:
            return SkillResult(success=False, error="No model configured for code generation")

        from core.harness.utils.prompt_loader import _sync_resolve
        _user_tail = (
            "Start each file with ## FILE: path. Put complete runnable code under each header. "
            "Do not ask clarifying questions. Do not output only a FILE header. "
            "Do not wrap the whole answer in DONE. If details are missing, state assumptions "
            "and still deliver a minimal runnable slice. "
            "Do not import relative modules (./utils) that you did not also deliver as ## FILE."
        )
        try:
            from core.management.execution_quality_review import _input_requires_auth_todo

            if _input_requires_auth_todo(requirements):
                # Gate (_output_has_auth_todo) only accepts a code-line comment
                # like `// TODO: auth` — prose / bare `TODO: auth/鉴权` fails
                # (run-91896f56fcd9: substantive apiClient still missing_auth_todo).
                _user_tail += (
                    " Auth details are not given — inside the apiClient/fetch helper "
                    "add an exact line comment `// TODO: auth` (TypeScript) or "
                    "`# TODO: auth` (Python); never claim DingTalk/SSO is integrated."
                )
        except Exception:
            logging.getLogger(__name__).debug(
                "code_generation auth-todo hint skipped", exc_info=True
            )
        msgs = [
            {"role": "system", "content": _sync_resolve("codegen-expert", language=language)},
            {
                "role": "user",
                "content": (
                    f"Generate {language} code for:\n{str(requirements)[:4000]}\n"
                    + _user_tail
                ),
            },
        ]

        try:
            from ...harness.syscalls.llm import sys_llm_generate
            import time as _time

            # Nested LLM under skill timeout (540) but above local default 300
            # (run-8fd66c1b21fa: operation timed out after 300.0s).
            from core.harness.utils.execute_session import skill_nested_llm_trace_context

            _llm_tc = skill_nested_llm_trace_context(
                context,
                params,
                source="code_generation",
                extra={"timeout_seconds": 420},
            )
            _t0 = _time.monotonic()
            response = await sys_llm_generate(
                model,
                msgs,
                trace_context=_llm_tc,
                max_tokens=8192,
            )
            # Empty content must NOT fall through to str(LLMResponse(...)) —
            # that greenwashed finish_reason=length empties as a fake "code" blob
            # (run-69d8218f39e8 deepseek-v4-pro max_tokens cut-off).
            _raw = getattr(response, "content", None)
            if not isinstance(_raw, str) or not _raw.strip():
                _raw = ""
            code = self._strip_done_prefix(_raw)
            _elapsed = _time.monotonic() - _t0

            # Retry only when thin AND first call left wall budget (avoid 2×420 > skill 540).
            if (not self._has_code_substance(code)) and _elapsed < 200.0:
                _retry_tail = (
                    f"Write complete {language} code for: {str(requirements)[:2000]}. "
                    "Use ## FILE: path headers and include full function/class bodies "
                    "(not just empty file headers). Do not ask questions — assume TODOs."
                )
                try:
                    from core.management.execution_quality_review import (
                        _input_requires_auth_todo as _req_auth,
                    )

                    if _req_auth(requirements):
                        _retry_tail += (
                            " Must include a code-line comment exactly "
                            "`// TODO: auth` or `# TODO: auth` where auth would go."
                        )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "code_gen_retry auth-todo hint skipped", exc_info=True
                    )
                short_msgs = [
                    {
                        "role": "user",
                        "content": _retry_tail,
                    }
                ]
                _retry_budget = max(60.0, min(180.0, 500.0 - _elapsed))
                res = await sys_llm_generate(
                    model,
                    short_msgs,
                    trace_context={
                        **_llm_tc,
                        "source": "code_gen_retry",
                        "timeout_seconds": _retry_budget,
                    },
                    max_tokens=8192,
                )
                _raw2 = getattr(res, "content", None)
                if not isinstance(_raw2, str) or not _raw2.strip():
                    _raw2 = ""
                code = self._strip_done_prefix(_raw2)

            # Align envelope language with body fences when they disagree —
            # unless language was locked by task/preferred_language inject
            # (FE preferred=typescript must not silently adopt a Python body).
            try:
                from core.management.execution_quality_review import (
                    _detect_output_code_language,
                    _language_families_compatible,
                )

                body_lang = _detect_output_code_language(code, {"text": code, "code": code})
                locked = bool(
                    (params if isinstance(params, dict) else {}).get("_language_locked")
                )
                if body_lang and not _language_families_compatible(str(language), body_lang):
                    if locked:
                        logging.getLogger(__name__).info(
                            "code_generation language lock kept=%s body=%s",
                            language,
                            body_lang,
                        )
                    else:
                        language = body_lang
            except Exception:
                logging.getLogger(__name__).debug(
                    "code_generation language reconcile skipped", exc_info=True
                )

            # Dual gate: shape check + clarify/thin detector (skill_delivery must not greenwash)
            thin = not self._has_code_substance(code)
            contract_hit: List[str] = []
            _lang_locked = bool(
                (params if isinstance(params, dict) else {}).get("_language_locked")
            )
            _out_env: Dict[str, Any] = {
                "code": code,
                "language": language,
                "text": code,
            }
            if _lang_locked:
                _out_env["_language_locked"] = True
            if not thin:
                try:
                    from core.management.execution_quality_review import (
                        _coding_contract_fail_codes,
                        is_non_deliverable_coding_output,
                    )

                    thin = is_non_deliverable_coding_output(
                        input_text=requirements,
                        output_text=code,
                        raw_out=_out_env,
                        scope="skill",
                    )
                    if thin:
                        contract_hit = [
                            c
                            for c in _coding_contract_fail_codes(
                                requirements,
                                code,
                                _out_env,
                            )
                            if c
                            in (
                                "language_mismatch",
                                "missing_auth_todo",
                                "dangling_local_import",
                                "fake_integration_claim",
                            )
                        ]
                        # Deterministic line-comment inject when only auth-TODO is
                        # missing (run-91896f56: prose ``### TODO: auth`` + Bearer
                        # example, no ``// TODO: auth`` in apiClient). Avoids a
                        # nested LLM fix and ReAct step_2 hang (0 children / 962s).
                        if contract_hit == ["missing_auth_todo"]:
                            try:
                                from core.management.execution_quality_review import (
                                    _ensure_auth_todo_comment,
                                )

                                _patched = _ensure_auth_todo_comment(
                                    code, language=str(language or "")
                                )
                                if _patched.strip() and _patched != code:
                                    code = _patched
                                    _out_env["code"] = code
                                    _out_env["text"] = code
                                    thin = is_non_deliverable_coding_output(
                                        input_text=requirements,
                                        output_text=code,
                                        raw_out=_out_env,
                                        scope="skill",
                                    )
                                    if thin:
                                        contract_hit = [
                                            c
                                            for c in _coding_contract_fail_codes(
                                                requirements,
                                                code,
                                                _out_env,
                                            )
                                            if c
                                            in (
                                                "language_mismatch",
                                                "missing_auth_todo",
                                                "dangling_local_import",
                                                "fake_integration_claim",
                                            )
                                        ]
                                    else:
                                        contract_hit = []
                            except Exception:
                                logging.getLogger(__name__).debug(
                                    "code_gen auth-todo deterministic patch skipped",
                                    exc_info=True,
                                )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "code_generation non-deliverable gate skipped", exc_info=True
                    )

            if thin:
                hint = (
                    f" contract={','.join(contract_hit)}"
                    if contract_hit
                    else ""
                )
                return SkillResult(
                    success=False,
                    error=(
                        "code_generation returned a thin stub or clarification "
                        f"(no runnable body){hint}. Retry with fuller output: "
                        "inline helpers (no ./utils), and mark // TODO: auth when asked."
                    ),
                    output={k: v for k, v in _out_env.items() if k != "text"},
                    metadata={"contract_fail_codes": contract_hit} if contract_hit else {},
                )

            return SkillResult(
                success=True,
                output={k: v for k, v in _out_env.items() if k != "text"},
            )

        except Exception as e:
            return SkillResult(success=False, error=str(e))

    @staticmethod
    async def _resolve_code_gen_model() -> Any:
        import os
        # Primary: central resolution via infra ModelManager
        try:
            from core.harness.utils.model_injection import create_selected_adapter, get_default_model
            return create_selected_adapter(model_name=get_default_model(purpose="code_gen") or best_model_for_purpose("chat"))
        except Exception as e:
            logging.warning("Code-gen model resolution failed: %s", e, exc_info=True)
            return None


class DataAnalysisSkill(BaseSkill):
    """
    Data Analysis Skill
    
    Analyzes data and provides insights.
    """

    def __init__(self):
        config = SkillConfig(
            name="data_analysis",
            description="Analyze data and provide insights",
            input_schema={
                "data": {"type": "string", "description": "Data to analyze"},
                "analysis_type": {"type": "string", "description": "Type of analysis"},
                "question": {"type": "string", "description": "Specific question about data"}
            },
            output_schema={
                "insights": {"type": "string", "description": "Analysis insights"},
                "visualization": {"type": "string", "description": "Visualization suggestions"}
            }
        )
        super().__init__(config)
        self._model = None

    def set_model(self, model: Any) -> None:
        """Set model for skill"""
        self._model = model

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """Execute data analysis"""
        if not self._model:
            return SkillResult(
                success=False,
                error="No model configured"
            )
        
        data = params.get("data", "")
        analysis_type = params.get("analysis_type", "general")
        question = params.get("question", "")
        
        from core.harness.utils.prompt_loader import _sync_resolve
        prompt = _sync_resolve("data-analysis",
            data=str(data)[:3000], analysis_type=str(analysis_type), question=str(question),
        )
        
        try:
            from ...harness.syscalls.llm import sys_llm_generate

            from core.harness.utils.execute_session import skill_nested_llm_trace_context

            response = await sys_llm_generate(
                self._model,
                [{"role": "user", "content": prompt}],
                trace_context=skill_nested_llm_trace_context(
                    context, params, source="skill_base"
                ),
            )
            
            return SkillResult(
                success=True,
                output={
                    "insights": response.content,
                    "visualization": "Suggested visualizations: bar chart, line graph"
                },
                metadata={"analysis_type": analysis_type}
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e)
            )


_skill_factory_registry: Dict[str, type] = {}


def register_skill_factory(skill_type: str, factory_class: type) -> None:
    """Register a skill factory class for a given skill type name.

    Called during seed_data() so create_skill() can resolve types
    without hardcoded if/elif chains.
    """
    _skill_factory_registry[skill_type] = factory_class


def create_skill(
    skill_type: str,
    **kwargs
) -> BaseSkill:
    """Factory function to create skill. Uses registry lookup, not hardcoded if/elif."""
    factory = _skill_factory_registry.get(skill_type)
    if factory:
        return factory()
    raise ValueError(f"Unknown skill type: {skill_type}")
