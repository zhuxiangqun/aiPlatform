from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Message:
    role: str = "user"
    content: str = ""
    name: Optional[str] = None


@dataclass
class ChatRequest:
    model: str = "gpt-4"
    messages: List[Message] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    stream: bool = False
    stop: Optional[List[str]] = None
    tools: Optional[List[dict]] = None


@dataclass
class ChatResponse:
    id: str = ""
    model: str = ""
    content: str = ""
    role: str = "assistant"
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    latency: float = 0.0
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class StreamChunk:
    content: str = ""
    finish_reason: Optional[str] = None
    delta: str = ""


@dataclass
class EmbeddingResult:
    embedding: List[float]
    model: str = ""


@dataclass
class LLMConfig:
    provider: str = "openai"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "gpt-4"
    timeout: int = 30
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: Optional[int] = None


@dataclass
class CostStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
