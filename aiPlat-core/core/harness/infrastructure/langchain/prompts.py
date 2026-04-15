"""
LangChain Integration - Prompts Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PromptTemplate:
    """Prompt template definition"""
    template: str
    input_variables: List[str] = field(default_factory=list)
    template_format: str = "f-string"  # f-string, jinja2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptConfig:
    """Prompt configuration"""
    template: str
    input_variables: List[str] = field(default_factory=list)
    template_format: str = "f-string"
    metadata: Dict[str, Any] = field(default_factory=dict)


class IPromptTemplate(ABC):
    """
    Prompt template interface - Contract for prompt templates
    """

    @abstractmethod
    def format(self, **kwargs) -> str:
        """Format prompt with variables"""
        pass

    @abstractmethod
    def get_input_variables(self) -> List[str]:
        """Get input variable names"""
        pass

    @abstractmethod
    def get_template(self) -> str:
        """Get template string"""
        pass


class LangChainPromptTemplate(IPromptTemplate):
    """
    LangChain-based prompt template wrapper
    """

    def __init__(self, template: str, input_variables: List[str], template_format: str = "f-string"):
        self._template = template
        self._input_variables = input_variables
        self._template_format = template_format
        
        try:
            from langchain.prompts import PromptTemplate as LCPromptTemplate
            
            self._lc_prompt = LCPromptTemplate(
                template=template,
                input_variables=input_variables,
                template_format=template_format,
            )
        except ImportError:
            self._lc_prompt = None

    def format(self, **kwargs) -> str:
        if self._lc_prompt:
            return self._lc_prompt.format(**kwargs)
        else:
            return self._template.format(**kwargs)

    def get_input_variables(self) -> List[str]:
        return self._input_variables.copy()

    def get_template(self) -> str:
        return self._template


class ChatPromptTemplate(IPromptTemplate):
    """
    Chat prompt template for multi-message conversations
    """

    def __init__(self, messages: List[Dict[str, str]]):
        self._messages = messages
        self._input_variables: List[str] = []
        
        for msg in messages:
            if "{variable}" in msg.get("template", ""):
                var = msg["template"].split("{")[1].split("}")[0]
                if var not in self._input_variables:
                    self._input_variables.append(var)
        
        try:
            from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
            
            lc_messages = []
            for msg in messages:
                if msg.get("role") == "system":
                    lc_messages.append(SystemMessagePromptTemplate.from_template(msg["template"]))
                elif msg.get("role") == "user":
                    lc_messages.append(HumanMessagePromptTemplate.from_template(msg["template"]))
            
            self._lc_prompt = ChatPromptTemplate.from_messages(lc_messages)
        except ImportError:
            self._lc_prompt = None

    def format(self, **kwargs) -> str:
        if self._lc_prompt:
            return self._lc_prompt.format(**kwargs)
        else:
            result = []
            for msg in self._messages:
                template = msg["template"]
                try:
                    formatted = template.format(**kwargs)
                    result.append(f"{msg.get('role', 'user')}: {formatted}")
                except KeyError:
                    result.append(f"{msg.get('role', 'user')}: {template}")
            return "\n".join(result)

    def get_input_variables(self) -> List[str]:
        return self._input_variables.copy()

    def get_template(self) -> str:
        return "\n".join([msg["template"] for msg in self._messages])


class FewShotPromptTemplate(IPromptTemplate):
    """
    Few-shot prompt template with examples
    """

    def __init__(
        self,
        template: str,
        input_variables: List[str],
        examples: List[Dict[str, str]],
        example_separator: str = "\n\n"
    ):
        self._template = template
        self._input_variables = input_variables
        self._examples = examples
        self._example_separator = example_separator
        
        try:
            from langchain.prompts import FewShotPromptTemplate, PromptTemplate
            
            example_prompt = PromptTemplate(
                template="{input} -> {output}",
                input_variables=["input", "output"]
            )
            
            self._lc_prompt = FewShotPromptTemplate(
                examples=examples,
                example_prompt=example_prompt,
                prefix=template.split("{examples}")[0] if "{examples}" in template else "",
                suffix=template.split("{examples}")[1] if "{examples}" in template else template,
                input_variables=input_variables,
            )
        except ImportError:
            self._lc_prompt = None

    def format(self, **kwargs) -> str:
        if self._lc_prompt:
            return self._lc_prompt.format(**kwargs)
        else:
            examples_str = self._example_separator.join([
                f"Input: {ex.get('input', '')}\nOutput: {ex.get('output', '')}"
                for ex in self._examples
            ])
            return self._template.format(examples=examples_str, **kwargs)

    def get_input_variables(self) -> List[str]:
        return self._input_variables.copy()

    def get_template(self) -> str:
        return self._template


def create_prompt_template(config: PromptConfig) -> IPromptTemplate:
    """
    Factory function to create prompt template
    
    Args:
        config: Prompt configuration
        
    Returns:
        IPromptTemplate: Prompt template instance
    """
    return LangChainPromptTemplate(
        template=config.template,
        input_variables=config.input_variables,
        template_format=config.template_format,
    )


def create_chat_prompt_template(messages: List[Dict[str, str]]) -> ChatPromptTemplate:
    """
    Factory function to create chat prompt template
    
    Args:
        messages: List of message templates
        
    Returns:
        ChatPromptTemplate: Chat prompt template instance
    """
    return ChatPromptTemplate(messages)


def create_few_shot_prompt_template(
    template: str,
    input_variables: List[str],
    examples: List[Dict[str, str]]
) -> FewShotPromptTemplate:
    """
    Factory function to create few-shot prompt template
    
    Args:
        template: Template string
        input_variables: Input variable names
        examples: Few-shot examples
        
    Returns:
        FewShotPromptTemplate: Few-shot prompt template instance
    """
    return FewShotPromptTemplate(
        template=template,
        input_variables=input_variables,
        examples=examples,
    )