"""Best-effort recovery + single-flight for local LLM generates.

``asyncio.wait_for`` cannot kill the sync OpenAI client thread; an in-flight
HTTP call keeps llama-server / Ollama busy. After TimeoutError we unload, and
while a local generate is in flight we serialize new local calls so nested
episodic/scoring generates cannot wedge the primary ReAct path.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

_log = logging.getLogger("aiplat.local_llm")

# Cross-event-loop safe (FastAPI loop + stream daemon ``asyncio.run``).
_slots = max(1, int(os.getenv("AIPLAT_LOCAL_LLM_MAX_INFLIGHT", "1") or "1"))
_local_llm_sem = threading.BoundedSemaphore(_slots)


def unload_local_llm_best_effort() -> None:
    """Drop loaded Ollama models (keep_alive=0) so a zombie generate cannot block the queue.

    asyncio.wait_for cannot kill the sync OpenAI client thread; the in-flight HTTP
    call keeps llama-server busy until we force unload.
    """
    try:
        import json
        import urllib.request

        base = (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
        with urllib.request.urlopen(f"{base}/api/ps", timeout=2) as resp:
            models = (json.loads(resp.read()) or {}).get("models") or []
        for m in models:
            name = (m or {}).get("name") or (m or {}).get("model")
            if not name:
                continue
            req = urllib.request.Request(
                f"{base}/api/generate",
                data=json.dumps({"model": str(name), "keep_alive": 0}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=5).read()
            except Exception:
                logging.debug("ollama unload failed for %s", name, exc_info=True)
    except Exception:
        logging.debug("ollama unload probe failed", exc_info=True)


def looks_like_local_llm(
    *,
    model_name: str = "",
    model: Any = None,
    provider: str = "",
    base_url: str = "",
) -> bool:
    """Heuristic: local Ollama / LM Studio / oMLX / loopback OpenAI-compatible."""
    prov = (provider or "").strip().lower()
    if not prov and model is not None:
        cfg = getattr(model, "_config", None) or getattr(model, "config", None)
        prov = str(getattr(cfg, "provider", "") or getattr(model, "_provider", "") or "").lower()
        if not base_url:
            base_url = str(
                getattr(cfg, "base_url", "")
                or getattr(model, "_base_url", "")
                or getattr(model, "base_url", "")
                or ""
            )
    if prov in ("ollama", "lmstudio", "omlx", "vllm", "llamacpp", "local"):
        return True
    url = (base_url or "").strip().lower()
    if any(h in url for h in ("127.0.0.1", "localhost", "0.0.0.0", "::1")):
        return True
    name = (model_name or "").strip().lower()
    # Common local tags without a remote provider prefix
    if name and ":" in name and "/" not in name.split(":")[0]:
        # e.g. qwen2.5-coder:7b — usually Ollama
        if any(
            name.startswith(p)
            for p in ("qwen", "llama", "mistral", "deepseek-r1", "phi", "gemma", "yi")
        ):
            return True
    return False


def _acquire_timeout_seconds() -> float:
    try:
        return float(
            os.getenv("AIPLAT_LOCAL_LLM_ACQUIRE_SECONDS")
            or os.getenv("AIPLAT_LLM_TIMEOUT_SECONDS")
            or "180"
        )
    except Exception:
        return 180.0


@asynccontextmanager
async def local_llm_inflight(
    *,
    model_name: str = "",
    model: Any = None,
    provider: str = "",
    base_url: str = "",
    acquire_timeout: Optional[float] = None,
) -> AsyncIterator[None]:
    """Serialize local LLM generates across event loops; no-op for remote APIs.

    Acquire MUST NOT block a thread-pool worker (``sem.acquire(blocking=True)`` in
    ``asyncio.to_thread``). Status polling uses ``anyio.to_thread`` for SQLite; a
    180s blocked acquire starves that pool → status API hangs while Agent is in
    pre_llm / generate (run-c604da8f129e + wiki_curation auto_atomize contention).
    """
    if not looks_like_local_llm(
        model_name=model_name, model=model, provider=provider, base_url=base_url
    ):
        yield
        return

    timeout = float(acquire_timeout) if acquire_timeout is not None else _acquire_timeout_seconds()
    timeout = max(0.5, timeout)
    deadline = asyncio.get_running_loop().time() + timeout
    acquired = False
    while True:
        if _local_llm_sem.acquire(blocking=False):
            acquired = True
            break
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"local_llm_inflight: acquire timed out after {timeout}s "
                f"(max_inflight={_slots}; another local generate still holds the slot)"
            )
        await asyncio.sleep(min(0.05, remaining))
    try:
        yield
    finally:
        if acquired:
            try:
                _local_llm_sem.release()
            except ValueError:
                _log.debug("local_llm_inflight release ignored (already free)", exc_info=True)


def local_llm_slot_available() -> bool:
    """True if a local LLM generate could start without waiting (peek; race-ok)."""
    got = _local_llm_sem.acquire(blocking=False)
    if not got:
        return False
    try:
        _local_llm_sem.release()
    except ValueError:
        pass  # noqa: cleanup-best-effort
    return True
