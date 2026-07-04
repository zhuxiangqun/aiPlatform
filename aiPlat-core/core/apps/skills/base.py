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

            response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}], trace_context={"source": "skill_base"})
            
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
            input_schema={
                "requirements": {"type": "string", "description": "Code requirements"},
                "language": {"type": "string", "description": "Programming language"},
                "framework": {"type": "string", "description": "Framework (optional)"}
            },
            output_schema={
                "code": {"type": "string", "description": "Generated code"},
                "language": {"type": "string", "description": "Language"}
            }
        )
        super().__init__(config)
        self._model = None

    def set_model(self, model: Any) -> None:
        """Set model for skill"""
        self._model = model

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """Execute code generation using best-available LLM via model_injection."""
        language = params.get("language", "python")
        requirements = params.get("requirements", "")

        # Auto-select model: via model_injection (canonical path), fall back to env config
        model = self._model
        if model is None:
            model = await self._resolve_code_gen_model()
        if model is None:
            return SkillResult(success=False, error="No model configured for code generation")

        from core.harness.utils.prompt_loader import _sync_resolve
        msgs = [
            {"role": "system", "content": _sync_resolve("codegen-expert", language=language)},
            {"role": "user", "content": f"Generate {language} code for:\n{str(requirements)[:4000]}\nOutput ONLY code with ## FILE: path headers. Output DONE: prefix before code."},
        ]

        try:
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(model, msgs)
            code = getattr(response, "content", "") or str(response)

            # If DONE: prefix found, extract code after it
            if "DONE:" in str(code):
                code = str(code).split("DONE:", 1)[-1].strip()
            if not code or len(code.strip()) < 10:
                short_msgs = [{"role": "user", "content": f"Write {language} code for: {str(requirements)[:2000]}. Output with DONE: prefix."}]
                res = await sys_llm_generate(model, short_msgs, trace_context={"source": "code_gen_retry"})
                code = getattr(res, "content", "") or str(res)
                if "DONE:" in str(code):
                    code = str(code).split("DONE:", 1)[-1].strip()

            return SkillResult(success=True, output={"code": code, "language": language})

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

            response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}], trace_context={"source": "skill_base"})
            
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
