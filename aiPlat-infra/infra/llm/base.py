from abc import ABC, abstractmethod
from typing import List, AsyncIterator, Optional
from .schemas import ChatRequest, ChatResponse, StreamChunk, Message


class LLMClient(ABC):
    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        pass

    @abstractmethod
    async def achat(self, request: ChatRequest) -> ChatResponse:
        pass

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        pass

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        pass

    @abstractmethod
    def get_metrics(self) -> dict:
        pass

    def close(self) -> None:
        """Release underlying HTTP connections / resources.

        Default no-op. Subclasses with persistent connections should override.
        """
