"""llm/base：LLM 客户端抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, AsyncIterator, Optional
from .schemas import ChatRequest, ChatResponse, StreamChunk, Message


class LLMClient(ABC):
    """大模型客户端抽象接口。"""

    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        """同步聊天补全。

        Args:
            request: 请求对象。
        """
        pass

    @abstractmethod
    async def achat(self, request: ChatRequest) -> ChatResponse:
        """异步聊天补全。

        Args:
            request: 请求对象。
        """
        pass

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """流式聊天补全。

        Args:
            request: 请求对象。
        """
        pass

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """文本嵌入。

        Args:
            texts: 文本列表。
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """估算 token 数。

        Args:
            text: 文本。
        """
        pass

    @abstractmethod
    def get_metrics(self) -> dict:
        """获取客户端运行指标。"""
        pass

    def close(self) -> None:
        """Release underlying HTTP connections / resources.

        Default no-op. Subclasses with persistent connections should override.
        """
