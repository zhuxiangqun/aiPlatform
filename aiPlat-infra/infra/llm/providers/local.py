import time
import os
import threading
from typing import List, AsyncIterator, Optional, Dict, Any
from ..base import LLMClient
from ..schemas import ChatRequest, ChatResponse, StreamChunk, LLMConfig


class LocalLLMClient(LLMClient):
    _instance_lock = threading.Lock()
    _model_cache: Dict[str, Any] = {}
    _embedding_model_cache: Dict[str, Any] = {}

    def __init__(self, config: LLMConfig):
        self.config = config
        self._model = None
        self._embedding_model = None
        self._backend = None
        self._metrics = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_latency": 0.0,
            "avg_latency": 0.0,
            "tokens_per_second": 0.0,
            "peak_memory_mb": 0,
            "backend": None,
        }
        self._init_options = self._parse_model_options()

    def _parse_model_options(self) -> Dict[str, Any]:
        options = {
            "n_ctx": 4096,
            "n_gpu_layers": -1,
            "n_batch": 512,
            "verbose": False,
        }
        if hasattr(self.config, "options") and self.config.options:
            options.update(self.config.options)
        if "n_ctx" not in options:
            options["n_ctx"] = self.config.max_tokens * 2 if self.config.max_tokens else 4096
        return options

    def _get_backend_priority(self) -> List[str]:
        return ["llama_cpp", "transformers", "fallback"]

    def _try_import_backend(self, backend: str) -> bool:
        try:
            if backend == "llama_cpp":
                import llama_cpp

                return True
            elif backend == "transformers":
                import transformers

                return True
            return False
        except ImportError:
            return False

    def _load_model_llama_cpp(self, model_path: str) -> Any:
        try:
            from llama_cpp import Llama

            cache_key = f"llama_cpp:{model_path}"
            if cache_key in self._model_cache:
                return self._model_cache[cache_key]

            model = Llama(
                model_path=model_path,
                n_ctx=self._init_options.get("n_ctx", 4096),
                n_gpu_layers=self._init_options.get("n_gpu_layers", -1),
                n_batch=self._init_options.get("n_batch", 512),
                verbose=self._init_options.get("verbose", False),
            )
            self._model_cache[cache_key] = model
            return model
        except Exception as e:
            raise RuntimeError(f"Failed to load model with llama-cpp: {e}")

    def _load_model_transformers(self, model_name: str) -> Any:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            cache_key = f"transformers:{model_name}"
            if cache_key in self._model_cache:
                return self._model_cache[cache_key]

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
                low_cpu_mem_usage=True,
            )
            if not torch.cuda.is_available():
                model = model.to("cpu")

            self._model_cache[cache_key] = {"model": model, "tokenizer": tokenizer}
            return {"model": model, "tokenizer": tokenizer}
        except Exception as e:
            raise RuntimeError(f"Failed to load model with transformers: {e}")

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        model_path = self.config.model

        for backend in self._get_backend_priority():
            if backend == "fallback":
                raise RuntimeError(f"No backend available for model: {model_path}")

            if not self._try_import_backend(backend):
                continue

            try:
                if backend == "llama_cpp":
                    if os.path.exists(model_path):
                        self._model = self._load_model_llama_cpp(model_path)
                        self._backend = "llama_cpp"
                        self._metrics["backend"] = "llama_cpp"
                        return self._model
                    if not model_path.endswith((".gguf", ".ggml", ".bin")):
                        continue
                    possible_paths = [
                        model_path,
                        os.path.expanduser(f"~/.cache/huggingface/{model_path}"),
                        f"/models/{model_path}",
                    ]
                    for path in possible_paths:
                        if os.path.exists(path):
                            self._model = self._load_model_llama_cpp(path)
                            self._backend = "llama_cpp"
                            self._metrics["backend"] = "llama_cpp"
                            return self._model

                elif backend == "transformers":
                    self._model = self._load_model_transformers(model_path)
                    self._backend = "transformers"
                    self._metrics["backend"] = "transformers"
                    return self._model

            except Exception:
                continue

        raise RuntimeError(f"Failed to load model: {model_path}")

    def _get_embedding_model(self) -> Any:
        if self._embedding_model is not None:
            return self._embedding_model

        try:
            from sentence_transformers import SentenceTransformer

            embedding_model_name = self._init_options.get(
                "embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
            )
            cache_key = f"embedding:{embedding_model_name}"

            if cache_key in self._embedding_model_cache:
                self._embedding_model = self._embedding_model_cache[cache_key]
                return self._embedding_model

            self._embedding_model = SentenceTransformer(embedding_model_name)
            self._embedding_model_cache[cache_key] = self._embedding_model
            return self._embedding_model
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. Install with: pip install sentence-transformers"
            )

    def _generate_llama_cpp(self, request: ChatRequest) -> ChatResponse:
        model = self._get_model()
        start = time.time()

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        params = {
            "messages": messages,
            "temperature": request.temperature if request.temperature else self.config.temperature,
            "top_p": request.top_p,
        }
        if request.max_tokens:
            params["max_tokens"] = request.max_tokens
        if request.stop:
            params["stop"] = request.stop

        response = model.create_chat_completion(**params)

        latency = time.time() - start
        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})

        self._update_metrics(usage, latency)

        return ChatResponse(
            id=response.get("id", "local"),
            model=self.config.model,
            content=content,
            role="assistant",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=response["choices"][0].get("finish_reason", "stop"),
            latency=latency,
        )

    def _generate_transformers(self, request: ChatRequest) -> ChatResponse:
        model_data = self._get_model()
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]
        start = time.time()

        prompt = self._messages_to_prompt(request.messages, tokenizer)

        inputs = tokenizer(prompt, return_tensors="pt")
        import torch

        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.max_tokens or 512,
                temperature=request.temperature
                if request.temperature
                else self.config.temperature,
                top_p=request.top_p,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response_text = generated_text[len(prompt) :].strip()

        latency = time.time() - start
        prompt_tokens = len(inputs["input_ids"][0])
        completion_tokens = len(outputs[0]) - prompt_tokens

        self._update_metrics(
            {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            latency,
        )

        return ChatResponse(
            id="local",
            model=self.config.model,
            content=response_text,
            role="assistant",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            finish_reason="stop",
            latency=latency,
        )

    def _messages_to_prompt(self, messages: List, tokenizer) -> str:
        try:
            if hasattr(tokenizer, "apply_chat_template"):
                return tokenizer.apply_chat_template(messages, tokenize=False)
        except Exception:
            pass

        prompt_parts = []
        for msg in messages:
            role = msg.role
            content = msg.content
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        prompt_parts.append("Assistant:")
        return "\n".join(prompt_parts)

    def _update_metrics(self, usage: Dict, latency: float):
        self._metrics["total_requests"] += 1
        self._metrics["total_tokens"] += usage.get("total_tokens", 0)
        self._metrics["total_latency"] += latency
        self._metrics["avg_latency"] = (
            self._metrics["total_latency"] / self._metrics["total_requests"]
        )
        if latency > 0 and usage.get("completion_tokens", 0) > 0:
            self._metrics["tokens_per_second"] = usage.get("completion_tokens", 0) / latency

        try:
            import psutil

            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024
            if mem_mb > self._metrics["peak_memory_mb"]:
                self._metrics["peak_memory_mb"] = mem_mb
        except ImportError:
            pass

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError("Use achat for async")

    async def achat(self, request: ChatRequest) -> ChatResponse:
        self._get_model()

        if self._backend == "llama_cpp":
            return self._generate_llama_cpp(request)
        elif self._backend == "transformers":
            return self._generate_transformers(request)
        else:
            raise RuntimeError(f"Unknown backend: {self._backend}")

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        self._get_model()

        if self._backend == "llama_cpp":
            async for chunk in self._stream_llama_cpp(request):
                yield chunk
        elif self._backend == "transformers":
            async for chunk in self._stream_transformers(request):
                yield chunk
        else:
            yield StreamChunk(content="Error: Unknown backend", finish_reason="error")

    async def _stream_llama_cpp(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        import asyncio

        model = self._get_model()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        params = {
            "messages": messages,
            "temperature": request.temperature if request.temperature else self.config.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        if request.max_tokens:
            params["max_tokens"] = request.max_tokens

        loop = asyncio.get_event_loop()

        def generate_stream():
            return model.create_chat_completion(**params)

        stream = await loop.run_in_executor(None, generate_stream)

        full_content = ""
        for chunk in stream:
            if "choices" in chunk and chunk["choices"]:
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    full_content += content
                    yield StreamChunk(content=content, delta=content)
                finish_reason = chunk["choices"][0].get("finish_reason")
                if finish_reason:
                    yield StreamChunk(content="", finish_reason=finish_reason)

    async def _stream_transformers(
        self, request: ChatRequest
    ) -> AsyncIterator[StreamChunk]:
        import asyncio
        import torch

        model_data = self._get_model()
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]

        prompt = self._messages_to_prompt(request.messages, tokenizer)
        inputs = tokenizer(prompt, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        input_ids = inputs["input_ids"]
        max_new_tokens = request.max_tokens or 512

        current_ids = input_ids.clone()
        generated_tokens = 0

        with torch.no_grad():
            while generated_tokens < max_new_tokens:
                outputs = model(current_ids)
                next_token_logits = outputs.logits[:, -1, :]
                next_token = torch.argmax(next_token_logits, dim=-1, keepdim=True)
                current_ids = torch.cat([current_ids, next_token], dim=-1)

                new_token_text = tokenizer.decode(next_token[0], skip_special_tokens=True)
                generated_tokens += 1

                if new_token_text and new_token_text.strip():
                    yield StreamChunk(content=new_token_text, delta=new_token_text)
                    await asyncio.sleep(0.01)

                if next_token[0].item() == tokenizer.eos_token_id:
                    yield StreamChunk(content="", finish_reason="stop")
                    break

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            model = self._get_embedding_model()
            embeddings = model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {e}")

    def count_tokens(self, text: str) -> int:
        try:
            if self._backend == "llama_cpp" and self._model:
                return len(self._model.tokenize(text.encode("utf-8")))
            elif self._backend == "transformers" and self._model:
                tokenizer = self._model["tokenizer"]
                return len(tokenizer.encode(text))
        except Exception:
            pass
        return len(text) // 4

    def get_metrics(self) -> dict:
        metrics = self._metrics.copy()
        try:
            import psutil

            process = psutil.Process()
            metrics["current_memory_mb"] = process.memory_info().rss / 1024 / 1024
        except ImportError:
            pass
        if self._model:
            metrics["model_loaded"] = True
            metrics["backend"] = self._backend
        else:
            metrics["model_loaded"] = False
        return metrics

    def unload_model(self):
        if self._backend == "llama_cpp":
            cache_key = f"llama_cpp:{self.config.model}"
            if cache_key in self._model_cache:
                del self._model_cache[cache_key]
        elif self._backend == "transformers":
            cache_key = f"transformers:{self.config.model}"
            if cache_key in self._model_cache:
                del self._model_cache[cache_key]

        self._model = None
        self._backend = None

        import gc

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    @classmethod
    def clear_cache(cls):
        cls._model_cache.clear()
        cls._embedding_model_cache.clear()
        gc.collect()