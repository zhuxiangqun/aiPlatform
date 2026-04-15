import time
from typing import List, AsyncIterator
from ..base import LLMClient
from ..schemas import ChatRequest, ChatResponse, StreamChunk, LLMConfig


class OpenAIClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._cost_stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def _get_client(self):
        if self._client is None:
            import openai

            openai.api_key = self.config.api_key
            if self.config.base_url:
                openai.base_url = self.config.base_url
            self._client = openai
        return self._client

    def chat(self, request: ChatRequest) -> ChatResponse:
        client = self._get_client()
        start = time.time()

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        try:
            response = client.ChatCompletion.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                stream=False,
            )

            latency = time.time() - start
            resp = response.choices[0].message
            usage = response.usage

            self._cost_stats["prompt_tokens"] += usage.prompt_tokens
            self._cost_stats["completion_tokens"] += usage.completion_tokens
            self._cost_stats["total_tokens"] += usage.total_tokens

            return ChatResponse(
                id=response.id,
                model=response.model,
                content=resp.content or "",
                role=resp.role,
                usage={
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                latency=latency,
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

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
            top_p=request.top_p,
            stop=request.stop,
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                yield StreamChunk(
                    content=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                    delta=delta.content or "",
                )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = client.Embedding.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_metrics(self) -> dict:
        return self._cost_stats
