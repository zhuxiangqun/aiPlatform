"""
Skill Base Module

Provides base Skill class implementing ISkill interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ...harness.interfaces import (
    ISkill,
    SkillConfig,
    SkillContext,
    SkillResult,
)


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

            response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}])
            
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
        """Execute code generation"""
        if not self._model:
            return SkillResult(
                success=False,
                error="No model configured"
            )
        
        requirements = params.get("requirements", "")
        language = params.get("language", "python")
        framework = params.get("framework", "")
        
        prompt = f"""Generate {language} code for the following requirements:

{requirements}

{f'Use {framework} framework.' if framework else ''}

Only output the code, no explanations.
"""
        
        try:
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}])
            
            return SkillResult(
                success=True,
                output={
                    "code": response.content,
                    "language": language
                },
                metadata={"framework": framework}
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e)
            )


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
        
        prompt = f"""Analyze the following data:

Data: {data}

Analysis type: {analysis_type}
Question: {question}

Provide insights and analysis.
"""
        
        try:
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}])
            
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


def create_skill(
    skill_type: str,
    **kwargs
) -> BaseSkill:
    """
    Factory function to create skill
    
    Args:
        skill_type: Type of skill ("text_generation", "code_generation", "data_analysis")
        
    Returns:
        BaseSkill: Skill instance
    """
    if skill_type == "text_generation":
        return TextGenerationSkill()
    elif skill_type == "code_generation":
        return CodeGenerationSkill()
    elif skill_type == "data_analysis":
        return DataAnalysisSkill()
    else:
        raise ValueError(f"Unknown skill type: {skill_type}")
