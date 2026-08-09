"""
OpenAI-compatible LLM client — supports any provider using the OpenAI API protocol.

Supported providers (via base_url config):
- OpenAI (default: https://api.openai.com/v1)
- DeepSeek (base_url: https://api.deepseek.com)
- Qwen / DashScope (base_url: https://dashscope.aliyuncs.com/compatible-mode/v1)
- LM Studio / oMLX / vLLM / llama.cpp server (base_url: http://localhost:xxxx/v1)
"""

import time
from typing import List, AsyncIterator
from ..base import LLMClient
from ..schemas import ChatRequest, ChatResponse, StreamChunk, LLMConfig


class OpenAICompatibleClient(LLMClient):
    """Generic client for any OpenAI-compatible API.

    Credential rotation (transparent): when the provider has multiple API keys
    configured via ``{PROVIDER}_KEYS=k1,k2,k3``, this client rotates keys on
    429 / 403 / timeout via infra ``CredentialPool``. Single-key setups keep the
    exact previous behavior (``config.api_key``), so this change is backward
    compatible and invisible to callers.
    """
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._cost_stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        # ── Credential pool wiring (only active for multi-key providers) ──
        self._pool = None
        self._current_key = None

    def _get_keep_alive(self) -> str | None:
        """Dynamic keep_alive based on model deployment state (v3).

        Returns None for API models, '-1' for hot-loaded local models,
        '30' for cold-loaded local models (prevents thrashing).
        """
        try:
            from infra.management.model.manager import _derive_model_state
            # Construct a lightweight model info object
            class _M: pass
            m = _M()
            m.provider = getattr(self.config, 'provider', '') or ''
            m.name = getattr(self.config, 'model', '') or ''
            m.size = 0
            ds = _derive_model_state(m)
            if ds == "local_hot":
                return "-1"
            elif ds == "local_cold":
                return "30"
        except Exception:
            pass
        return None

    def _get_extra_body(self) -> dict:
        """Return extra_body dict with keep_alive, or empty dict for API models."""
        _ka = self._get_keep_alive()
        return {"keep_alive": _ka} if _ka else {}

    # ── Credential pool wiring (only active for multi-key providers) ──
        try:
            provider = (config.provider or "").lower()
            if provider:
                from infra.management.model.credential_pool import get_credential_pool
                pool = get_credential_pool(provider)
                if pool.key_count > 1:
                    self._pool = pool
        except Exception:
            # No {PROVIDER}_KEYS / no env keys → single-key mode (unchanged)
            self._pool = None

    def _resolve_api_key(self) -> str:
        """Return the active API key — pool key when rotating, else static config key."""
        if self._pool is not None:
            if self._current_key is None:
                self._current_key = self._pool.next()
            return self._current_key
        return self.config.api_key

    @staticmethod
    def _is_rotatable_error(e: Exception) -> bool:
        """True for errors that warrant switching to another API key (429/403/401/timeout)."""
        try:
            import openai
            if isinstance(e, (openai.RateLimitError, openai.AuthenticationError,
                              openai.PermissionDeniedError, openai.APITimeoutError)):
                return True
        except Exception:  # noqa: optional-error-detection
            pass
            return True
        if isinstance(e, TimeoutError):
            return True
        msg = str(e).lower()
        return any(k in msg for k in ("rate limit", "429", "403", "401",
                                      "timeout", "timed out"))

    @staticmethod
    def _extract_retry_after(e: Exception) -> float:
        """Best-effort parse of Retry-After header (seconds); 0 if absent."""
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                ra = resp.headers.get("retry-after")
                if ra:
                    return float(ra)
            except Exception:  # noqa: optional-header-parse
                pass

    def _rotate_key(self, e: Exception) -> None:
        """Cool down the current key and switch to the next available one."""
        if self._pool is None:
            return
        self._pool.mark_rate_limited(self._current_key, self._extract_retry_after(e))
        self._current_key = self._pool.next()
        self._client = None  # force rebuild with the new key

    def _get_client(self):
        if self._client is None:
            import openai
            import httpx
            base_url = self.config.base_url or None
            # Normalize: Ollama/LM Studio/oMLX may lack /v1 suffix
            if base_url and not base_url.rstrip("/").endswith("/v1"):
                provider = (self.config.provider or "").lower()
                if provider in ("ollama", "lmstudio", "omlx", "vllm"):
                    base_url = base_url.rstrip("/") + "/v1"
            timeout_sec = self.config.timeout or 30
            self._client = openai.OpenAI(
                api_key=self._resolve_api_key(),
                base_url=base_url,
                timeout=httpx.Timeout(timeout=timeout_sec, connect=5.0),
            )
        return self._client

    def _execute_chat(self, client, request: ChatRequest) -> ChatResponse:
        """Core chat call — factored out so the retry loop can swap auth after failures."""
        start = time.time()

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        create_kwargs: dict = dict(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            stop=request.stop,
            stream=False,
        )
        if request.timeout:
            import httpx
            create_kwargs["timeout"] = httpx.Timeout(timeout=request.timeout, connect=5.0)
        # Dynamic keep_alive based on model deployment state (v3)
        _ka = self._get_keep_alive()
        if _ka:
            create_kwargs["extra_body"] = {"keep_alive": _ka}
        response = client.chat.completions.create(**create_kwargs)

        latency = time.time() - start
        resp = response.choices[0].message
        usage = response.usage

        # usage may be a CompletionUsage object (openai) or a dict (DeepSeek)
        prompt_tokens = getattr(usage, 'prompt_tokens', usage.get('prompt_tokens', 0) if hasattr(usage, 'get') else 0)
        completion_tokens = getattr(usage, 'completion_tokens', usage.get('completion_tokens', 0) if hasattr(usage, 'get') else 0)
        total_tokens = getattr(usage, 'total_tokens', usage.get('total_tokens', 0) if hasattr(usage, 'get') else 0)

        self._cost_stats["prompt_tokens"] += prompt_tokens
        self._cost_stats["completion_tokens"] += completion_tokens
        self._cost_stats["total_tokens"] += total_tokens

        # ── Liveness signal for credential pool ──
        if self._pool is not None and self._current_key is not None:
            self._pool.mark_success(self._current_key)

        return ChatResponse(
            id=response.id,
            model=response.model,
            content=resp.content or "",
            role=resp.role,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            finish_reason=response.choices[0].finish_reason,
            latency=latency,
        )

    def chat(self, request: ChatRequest) -> ChatResponse:
        max_attempts = self._pool.key_count if self._pool else 1
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                client = self._get_client()
                return self._execute_chat(client, request)
            except Exception as e:
                # Preserve the first seen exception for non-rotatable cases
                if last_exc is None:
                    last_exc = e
                if attempt < max_attempts - 1 and self._is_rotatable_error(e):
                    self._rotate_key(e)
                    continue
                raise RuntimeError(f"OpenAI API error: {e}")

        raise RuntimeError(f"OpenAI API error: {last_exc}")

    async def achat(self, request: ChatRequest) -> ChatResponse:
        import asyncio
        return await asyncio.to_thread(self.chat, request)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        max_attempts = self._pool.key_count if self._pool else 1
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            yielded_any = False
            try:
                client = self._get_client()
                response = client.chat.completions.create(
                    model=request.model,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                    stop=request.stop,
                     stream=True,
                     **self._get_extra_body(),
                 )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        yielded_any = True
                        yield StreamChunk(
                            content=delta.content or "",
                            finish_reason=chunk.choices[0].finish_reason,
                            delta=delta.content or "",
                        )
                if self._pool is not None and self._current_key is not None:
                    self._pool.mark_success(self._current_key)
                return
            except Exception as e:
                last_exc = e
                # Only rotate/retry if nothing was streamed yet — retrying after
                # partial output would duplicate content.
                if (not yielded_any) and attempt < max_attempts - 1 and self._is_rotatable_error(e):
                    self._rotate_key(e)
                    continue
                raise RuntimeError(f"OpenAI API error: {e}")

        if last_exc is not None:
            raise RuntimeError(f"OpenAI API error: {last_exc}")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        create_kwargs: dict = dict(model="text-embedding-3-small", input=texts)
        _ka = self._get_keep_alive()
        if _ka:
            create_kwargs["extra_body"] = {"keep_alive": _ka}
        response = client.embeddings.create(**create_kwargs)
        return [d.embedding for d in response.data]

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    def close(self) -> None:
        """Release httpx connection pool and client resources."""
        if self._client is not None:
            # Unload Ollama model before closing connection
            if (self.config.provider or "").lower() == "ollama":
                try:
                    import httpx
                    ollama_url = (self.config.base_url or "http://localhost:11434").rstrip("/").replace("/v1", "")
                    httpx.post(
                        f"{ollama_url}/api/generate",
                        json={"model": self.config.model, "keep_alive": 0},
                        timeout=5.0,
                    )
                except Exception:  # noqa: best-effort-unload
                    pass
            self._client = None

    @staticmethod
    def unload_ollama_models(ollama_base_url: str = "http://localhost:11434", timeout: float = 10.0) -> dict:
        """Unload all loaded Ollama models to free GPU/RAM. Returns status dict."""
        result = {"unloaded": [], "errors": []}
        try:
            import httpx
            r = httpx.get(f"{ollama_base_url.rstrip('/')}/api/ps", timeout=5.0)
            r.raise_for_status()
            models = r.json().get("models", [])
            for m in models:
                model_name = m.get("name", m.get("model", ""))
                if not model_name:
                    continue
                try:
                    ur = httpx.post(
                        f"{ollama_base_url.rstrip('/')}/api/generate",
                        json={"model": model_name, "keep_alive": 0},
                        timeout=timeout,
                    )
                    if ur.status_code < 400:
                        result["unloaded"].append(model_name)
                    else:
                        result["errors"].append(f"{model_name}: HTTP {ur.status_code}")
                except Exception as exc:
                    result["errors"].append(f"{model_name}: {exc}")
        except Exception as exc:
            result["errors"].append(f"list models failed: {exc}")
        return result

    def get_metrics(self) -> dict:
        metrics = dict(self._cost_stats)
        # Observability: surface credential-pool health when rotation is active.
        if self._pool is not None:
            try:
                metrics["credential_pool"] = self._pool.status()
            except Exception:  # noqa: metrics-non-critical
                pass


# Backward-compat aliases
OpenAIClient = OpenAICompatibleClient
DeepSeekClient = OpenAICompatibleClient
