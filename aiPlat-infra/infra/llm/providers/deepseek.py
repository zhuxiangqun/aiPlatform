import time
from typing import List, AsyncIterator
from ..base import LLMClient
from ..schemas import ChatRequest, ChatResponse, StreamChunk, LLMConfig


class DeepSeekClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            self._client = openai
            self._client.api_key = self.config.api_key
            self._client.base_url = (
                self.config.base_url or "https://api.deepseek.com/v1"
            )
        return self._client

    def chat(self, request: ChatRequest) -> ChatResponse:
        client = self._get_client()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        response = client.ChatCompletion.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return ChatResponse(
            id=response.id,
            model=response.model,
            content=response.choices[0].message.content,
        )

    async def achat(self, request: ChatRequest) -> ChatResponse:
        return self.chat(request)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        response = client.ChatCompletion.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta:
                yield StreamChunk(
                    content=chunk.choices[0].delta.content,
                    delta=chunk.choices[0].delta.content,
                )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = client.Embedding.create(model="deepseek-embedding", input=texts)
        return [d.embedding for d in response.data]

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_metrics(self) -> dict:
        return {}
