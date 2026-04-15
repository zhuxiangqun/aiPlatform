"""
LangChain Integration Module

Provides integration with LangChain for models, tools, and prompts.
Memory is now in harness/memory/ module.
"""

from .models import (
    IModel,
    ModelConfig,
    ModelProvider,
    Message,
    ModelResponse,
    LangChainModelWrapper,
    create_model,
)

from .tools import (
    IToolWrapper,
    ToolDefinition,
    FunctionToolWrapper,
    StructuredToolWrapper,
    create_tool_from_function,
    create_tool_from_class,
)

from .prompts import (
    IPromptTemplate,
    PromptTemplate,
    PromptConfig,
    ChatPromptTemplate,
    FewShotPromptTemplate,
    create_prompt_template,
    create_chat_prompt_template,
    create_few_shot_prompt_template,
)

from ...memory.langchain_adapter import (
    IMemory,
    MemoryConfig,
    MemoryMessage,
    BufferMemory,
    ConversationBufferMemory,
    create_memory,
)

__all__ = [
    "IModel",
    "ModelConfig",
    "ModelProvider",
    "Message",
    "ModelResponse",
    "LangChainModelWrapper",
    "create_model",
    "IToolWrapper",
    "ToolDefinition",
    "FunctionToolWrapper",
    "StructuredToolWrapper",
    "create_tool_from_function",
    "create_tool_from_class",
    "IPromptTemplate",
    "PromptTemplate",
    "PromptConfig",
    "ChatPromptTemplate",
    "FewShotPromptTemplate",
    "create_prompt_template",
    "create_chat_prompt_template",
    "create_few_shot_prompt_template",
    "IMemory",
    "MemoryConfig",
    "MemoryMessage",
    "BufferMemory",
    "ConversationBufferMemory",
    "create_memory",
]