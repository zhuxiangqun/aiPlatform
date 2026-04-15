import time
from typing import List, AsyncIterator
from ..base import LLMClient
from ..schemas import ChatRequest, ChatResponse, StreamChunk, LLMConfig


class AnthropicClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._cost_stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError("Use achat for async")

    async def achat(self, request: ChatRequest) -> ChatResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.api_key)

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        response = client.messages.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens or 1024,
        )

        return ChatResponse(
            id=response.id,
            model=response.model,
            content=response.content[0].text if response.content else "",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.api_key)

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        with client.messages.stream(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens or 1024,
        ) as stream:
            for chunk in stream.text_stream:
                yield StreamChunk(content=chunk, delta=chunk)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Anthropic doesn't support embeddings API")

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_metrics(self) -> dict:
        return self._cost_stats
