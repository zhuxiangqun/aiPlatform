"""
Model injection helpers.

统一处理 "给 agent/skill 注入 LLM adapter" 的逻辑，避免：
- agent._model 被更新，但 agent._loop._model 仍旧为空（导致偶发失败）
- skill 注入仍强制 openai 且无 key（导致执行链路不稳定）
"""

from __future__ import annotations
import logging

import os
from typing import Any, Optional
import json
import sqlite3
from collections import defaultdict


# ── v3.0 Route Metrics (in-memory) ────────────────────────────────
# Updated atomically by _record_quality_and_metrics_async.
_route_metrics = {
    "total_calls": 0,
    "fallback_count": 0,
    "total_attempts": 0,
    "local_calls": 0,
    "external_calls": 0,
    "complexity_dist": defaultdict(int),  # {simple: N, medium: N, complex: N}
    "recent_logs": [],  # last 20 entries: [{time, purpose, model, success, latency_ms, quality_delta}]
}

def get_route_metrics() -> dict:
    """Return a snapshot of current route metrics (thread-safe for reading)."""
    m = dict(_route_metrics)
    m["complexity_dist"] = dict(m["complexity_dist"])
    m["recent_logs"] = list(m["recent_logs"][-20:])
    return m

from core.adapters.llm.base import create_adapter

# ── Cached ModelManager singleton (avoids 8s Ollama re-scan per call) ──
_model_manager_cache: Any = None


def _get_cached_model_manager() -> Any:
    """Get or create the infra ModelManager singleton. Cached to avoid Ollama re-scan."""
    global _model_manager_cache
    if _model_manager_cache is not None:
        return _model_manager_cache
    from infra.management.model.manager import ModelManager
    _model_manager_cache = ModelManager()
    return _model_manager_cache


def _log_model_selection(purpose: str, selected: str, entry: str = "best_model_for_purpose",
                         candidates: list = None, **extra):
    """Append model selection to shared audit log for observability tab."""
    try:
        import os as _log_os, json as _log_json, time as _log_time
        log_path = _log_os.path.join(
            _log_os.path.expanduser(_log_os.getenv("AIPLAT_HOME", "~/.aiplat")),
            "wiki", "model_selection_log.json")
        samples = []
        if _log_os.path.exists(log_path):
            samples = _log_json.loads(open(log_path).read())
        record = {"ts": _log_time.time(), "purpose": purpose,
                  "selected": selected, "entry": entry}
        if candidates:
            record["candidates"] = [{"name": n, "score": s} for s, n in candidates[:5]]
        if extra:
            record["extra"] = str(extra)[:200]
        samples.append(record)
        _log_os.makedirs(_log_os.path.dirname(log_path), exist_ok=True)
        _log_json.dump(samples[-1000:], open(log_path, "w"))
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def get_default_model(purpose: str = "default") -> str:
    """Centralized default model selection — pure delegation to infra ModelManager."""
    try:
        mgr = _get_cached_model_manager()
        result = mgr.get_default_model(purpose)
        if result:
            _log_model_selection(purpose, result, entry="get_default_model", source="infra_ModelManager")
            return result
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return ""


def _norm_provider(p: str) -> str:
    p = (p or "").strip().lower()
    if p in {"openai", "openai-compatible", "openai_compatible"}:
        return "openai"
    if p in {"anthropic", "claude"}:
        return "anthropic"
    if p in {"deepseek"}:
        return "deepseek"
    if p in {"mock"}:
        return "mock"
    if p in {"scripted"}:
        return "scripted"
    return p or "openai"


def _load_default_llm_from_store() -> Optional[dict]:
    """
    Sync read from ExecutionStore to avoid making model injection async.
    Returns: {adapter_id, model} or None.
    """
    try:
        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        db_path = getattr(getattr(store, "_config", None), "db_path", None)
        if not db_path:
            return None
        conn = sqlite3.connect(str(db_path, timeout=5.0))
        try:
            row = conn.execute("SELECT value_json FROM global_settings WHERE key='default_llm' LIMIT 1;").fetchone()
            if not row or not row[0]:
                return None
            v = json.loads(row[0]) if isinstance(row[0], str) else {}
            if isinstance(v, dict) and v.get("adapter_id") and v.get("model"):
                return v
        finally:
            conn.close()
    except Exception:
        return None
    return None


def _load_adapter_from_store(adapter_id: str) -> Optional[dict]:
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        db_path = getattr(getattr(store, "_config", None), "db_path", None)
        if not db_path:
            return None
        conn = sqlite3.connect(str(db_path, timeout=5.0))
        conn.row_factory = sqlite3.Row
        try:
            r = conn.execute("SELECT * FROM adapters WHERE adapter_id=? LIMIT 1;", (str(adapter_id),)).fetchone()
            if not r:
                return None
            d = dict(r)
            api_key = d.get("api_key")
            try:
                if d.get("api_key_enc") and is_configured():
                    api_key = decrypt_str(d.get("api_key_enc"))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            d["api_key"] = api_key
            try:
                d["models"] = json.loads(d.get("models_json") or "[]") if d.get("models_json") else []
            except Exception:
                d["models"] = []
            return d
        finally:
            conn.close()
    except Exception:
        return None


def create_selected_adapter(*, model_name: str) -> Any:
    """Create adapter for a model. Delegates to infra ModelManager for model info."""
    from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url

    selected_model = model_name
    if not selected_model:
        model_env = os.getenv("AIPLAT_LLM_MODEL", "").strip()
        default_llm = _load_default_llm_from_store() if not os.getenv("AIPLAT_LLM_PROVIDER", "") else None
        selected_model = model_env or (default_llm.get("model") if default_llm else "") or get_default_model()

    _log_model_selection("create_adapter", selected_model, entry="create_selected_adapter",
                         input_name=model_name)

    # ── Unified model resolution: infra ModelManager is the single source of truth ──
    provider = "openai"
    base_url = ""
    api_key = ""
    needs_api_key = True

    from infra.management.model.manager import ModelManager
    mgr = _get_cached_model_manager()
    model_info = mgr.select(model_name=selected_model)
    if model_info:
        provider = model_info.provider or "openai"
        if model_info.config and model_info.config.base_url:
            base_url = model_info.config.base_url
        if model_info.source.value == "local":
            # Local model (Ollama, LM Studio, etc.) — no API key needed
            api_key = "local"
            needs_api_key = False
            if not base_url:
                base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            # Normalize Ollama URL: add /v1 suffix
            if base_url and not base_url.rstrip("/").endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

    # Env var overrides (highest priority, but local model base_url wins)
    provider_env = os.getenv("AIPLAT_LLM_PROVIDER", "").strip()
    base_url_env = os.getenv("AIPLAT_LLM_BASE_URL", "").strip()
    api_key_env = (os.getenv("AIPLAT_LLM_API_KEY") or "").strip()

    if provider_env:
        provider = _norm_provider(provider_env)
    if base_url_env and needs_api_key:
        base_url = base_url_env
    if api_key_env and needs_api_key:
        api_key = api_key_env

    # If model not found in registry, fall back to env var resolution
    if not model_info:
        if not api_key:
            api_key = api_key_env or get_llm_api_key("deepseek") or ""
        if not base_url:
            base_url = base_url_env or get_llm_base_url("deepseek") or ""

    # Provider normalization for OpenAI-compatible adapters
    adapter_provider = provider
    if provider in {"deepseek", "ollama", "lmstudio", "omlx", "vllm", "openai_compatible"}:
        adapter_provider = "openai"
    elif provider == "anthropic":
        adapter_provider = "anthropic"

    if needs_api_key and not api_key:
        default_llm = _load_default_llm_from_store()
        if default_llm and default_llm.get("adapter_id"):
            ad = _load_adapter_from_store(str(default_llm.get("adapter_id")))
            if ad:
                api_key = str(ad.get("api_key") or "")
        if not api_key:
            raise RuntimeError(
                f"No API key configured for remote model '{selected_model}'. "
                "Set AIPLAT_LLM_API_KEY or DEEPSEEK_API_KEY environment variable."
            )

    _register_adapter(provider=adapter_provider, model_name=selected_model, base_url=base_url)
    return create_adapter(provider=adapter_provider, api_key=api_key or None, model=selected_model, base_url=base_url or None)


def _bind_model(obj: Any, adapter: Any) -> None:
    """Bind adapter into an object and its internal loop if present."""
    # 1) bind to obj itself
    if hasattr(obj, "set_model"):
        try:
            obj.set_model(adapter)  # type: ignore[attr-defined]
        except Exception:
            # fall back to attribute write
            try:
                setattr(obj, "_model", adapter)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
    else:
        try:
            setattr(obj, "_model", adapter)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # 2) bind to internal loop (common pattern)
    try:
        loop = getattr(obj, "_loop", None)
        if loop is not None:
            if hasattr(loop, "set_model"):
                try:
                    loop.set_model(adapter)  # type: ignore[attr-defined]
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
            elif hasattr(loop, "_model"):
                try:
                    setattr(loop, "_model", adapter)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def ensure_agent_model(agent: Any, *, model_name: str, force: bool = False) -> Any:
    """
    Ensure agent has a usable model. If openai has no api key, will use mock.

    force=True: regardless of current model, override to selected adapter.
    """
    adapter = create_selected_adapter(model_name=model_name)
    if force:
        _bind_model(agent, adapter)
        return adapter

    cur = getattr(agent, "_model", None)
    if cur is None:
        _bind_model(agent, adapter)
        return adapter

    # Still ensure loop model matches agent model (root cause of flakiness)
    try:
        loop = getattr(agent, "_loop", None)
        loop_model = getattr(loop, "_model", None) if loop is not None else None
        if loop is not None and loop_model is None:
            _bind_model(agent, cur)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    return cur


def ensure_skill_model(skill: Any, *, model_name: str, force: bool = False) -> Any:
    adapter = create_selected_adapter(model_name=model_name)
    cur = getattr(skill, "_model", None)
    if force or cur is None:
        _bind_model(skill, adapter)
        return adapter
    return cur


async def create_adapter_with_fallback(purpose: str, timeout: int = 60) -> Any:
    """Try models in order, fallback on timeout. Returns (adapter, model_name).

    Usage:
        adapter, model_name = await create_adapter_with_fallback("wiki_curation", timeout=60)
    """
    import asyncio, logging as _logging
    _fb_log = _logging.getLogger("aiplat.model_fallback")

    try:
        mgr = _get_cached_model_manager()
        candidates = mgr.select_by_purpose_list(purpose)
    except Exception:
        candidates = []

    # Purpose-specific env var override (comma-separated for fallback list)
    if not candidates or len(candidates) == 1:
        env_val = os.getenv(f"AIPLAT_{purpose.upper()}_MODEL", "").strip()
        if env_val:
            env_models = [m.strip() for m in env_val.split(",") if m.strip()]
            candidates = env_models

    if not candidates:
        candidate = best_model_for_purpose(purpose)
        candidates = [candidate] if candidate else []

    last_error = None
    for i, model_name in enumerate(candidates):
        try:
            adapter = create_selected_adapter(model_name=model_name)
            _fb_log.info(f"Model '{model_name}' ({i+1}/{len(candidates)}) selected for '{purpose}'")
            return adapter, model_name
        except asyncio.TimeoutError:
            _fb_log.warning(f"Model '{model_name}' ({i+1}/{len(candidates)}) timed out for '{purpose}'")
            last_error = f"timeout after {timeout}s"
            continue
        except Exception as e:
            _fb_log.warning(f"Model '{model_name}' ({i+1}/{len(candidates)}) failed for '{purpose}': {e}")
            last_error = str(e)
            continue

    raise RuntimeError(f"All {len(candidates)} models failed for '{purpose}': {last_error}")


async def generate_with_fallback(purpose: str,
                                   messages: list,
                                   timeout: int = 60,
                                   config=None) -> tuple:
    """Generate with automatic model fallback on timeout.

    Returns (LLMResponse, model_name). Tries each candidate model; on timeout
    or error, moves to the next automatically. The caller gets the response
    from the first model that succeeds within timeout.

    Usage:
        resp, model = await generate_with_fallback(
            "wiki_curation",
            messages=[{"role": "user", "content": "hello"}],
            timeout=60
        )
    """
    import asyncio as _asyncio, logging as _logging
    _fb_log = _logging.getLogger("aiplat.model_fallback")

    candidates = []

    # Env var override (comma-separated list for fallback order)
    env_val = os.getenv(f"AIPLAT_{purpose.upper()}_MODEL", "").strip()
    if env_val:
        candidates = [m.strip() for m in env_val.split(",") if m.strip()]

    # Fallback to infra auto-selection
    if not candidates:
        try:
            candidates = _get_cached_model_manager().select_by_purpose_list(purpose)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    if not candidates:
        candidates = [best_model_for_purpose(purpose)]

    per_model_timeout = min(timeout, 15)  # per-model cap
    # P2: global timeout aligned with caller budget, minimum guarantee
    calculated = len(candidates) * per_model_timeout + 5
    caller_budget = max(timeout * 0.8, per_model_timeout)  # 80% for inference, 20% for network
    global_timeout = min(calculated, caller_budget)
    global_timeout = max(global_timeout, per_model_timeout)  # at least one full attempt

    failed_models = set()
    last_error = None
    errors = []

    try:
        async with _asyncio.timeout(global_timeout):
            for i, model_name in enumerate(candidates):
                if model_name in failed_models:
                    continue
                try:
                    adapter = create_selected_adapter(model_name=model_name)
                    resp = await _asyncio.wait_for(
                        adapter.generate(messages, config=config),
                        timeout=per_model_timeout
                    )
                    _fb_log.info(f"'{purpose}' completed with '{model_name}' "
                                 f"({i+1}/{len(candidates)}, {per_model_timeout}s)")
                    if failed_models:
                        _fb_log.warning(
                            f"fallback_triggered purpose={purpose} "
                            f"failed={list(failed_models)} final={model_name} "
                            f"attempt={len(failed_models)+1}/{len(candidates)}"
                        )
                    # v3.0: async fire-and-forget quality + metrics recording
                    import asyncio as _as
                    _as.create_task(_record_quality_and_metrics_async(
                        purpose, model_name, resp,
                        attempts=len(failed_models) + 1
                    ))
                    return resp, model_name
                except _asyncio.TimeoutError:
                    msg = f"timeout after {per_model_timeout}s"
                    _fb_log.warning(f"'{model_name}' timed out ({i+1}/{len(candidates)}, {per_model_timeout}s)")
                    failed_models.add(model_name)
                    errors.append({"model": model_name, "error": msg, "transient": True})
                    last_error = msg
                    continue
                except Exception as e:
                    err_str = str(e)
                    permanent_keywords = ("API key", "401", "403", "404", "api_key", "unauthorized",
                                          "invalid api key", "not found", "model not found")
                    is_permanent = any(kw in err_str.lower() for kw in permanent_keywords)
                    _fb_log.warning(f"'{model_name}' failed ({i+1}/{len(candidates)}): {e}")
                    if is_permanent:
                        _fb_log.error(f"Permanent error on '{model_name}': {err_str}. Stopping fallback.")
                        raise RuntimeError(
                            f"Model '{model_name}' failed with permanent error: {err_str}. "
                            f"Tried {len(failed_models)+1}/{len(candidates)} candidates. Errors: {errors}"
                        ) from e
                    failed_models.add(model_name)
                    errors.append({"model": model_name, "error": err_str, "transient": True})
                    last_error = err_str
                    continue
    except _asyncio.TimeoutError:
        _fb_log.error(f"Global fallback timeout ({global_timeout}s) for '{purpose}'. "
                      f"Tried {len(failed_models)}/{len(candidates)} models.")
        raise RuntimeError(f"All models timed out for '{purpose}' within {global_timeout}s. "
                           f"Failed: {failed_models}")

    raise RuntimeError(f"All {len(candidates)} models failed for '{purpose}'. "
                       f"Errors: {errors}")


async def _record_quality_and_metrics_async(purpose: str, model_name: str, resp, attempts: int = 1):
    """Fire-and-forget: record quality score + latency + route metrics atomically."""
    import time as _time, logging as _logging
    _ql = _logging.getLogger("aiplat.quality")
    log_entry = {"time": _time.strftime("%H:%M:%S"), "purpose": purpose, "model": model_name, "success": True}

    try:
        # 1. Quality validation
        text = resp.content if hasattr(resp, 'content') else str(resp)
        from infra.management.model.quality_validator import QualityValidator, get_quality_tracker
        result = QualityValidator.validate(purpose, text)
        get_quality_tracker().update(model_name, purpose, result.score_delta)
        _ql.info(f"quality_recorded purpose={purpose} model={model_name} "
                 f"delta={result.score_delta:.3f} details={result.details}")
        log_entry["quality_delta"] = round(result.score_delta, 3)
    except Exception as e:
        _ql.warning(f"quality_record_failed purpose={purpose} model={model_name}: {e}")

    try:
        # 2. Latency tracking
        from infra.management.model.latency_tracker import get_latency_tracker
        if hasattr(resp, 'usage') and resp.usage:
            tokens = resp.usage.get('completion_tokens', 50)
            latency_ms = max(tokens * 20, 500)
            get_latency_tracker().record_latency(model_name, latency_ms)
            log_entry["latency_ms"] = latency_ms
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # 3. Route metrics (atomic update)
    is_local = any(k in model_name for k in ["qwen", "gemma", "minicpm", "mxbai", "all-MiniLM"])
    _route_metrics["total_calls"] += 1
    _route_metrics["total_attempts"] += attempts
    if attempts > 1:
        _route_metrics["fallback_count"] += 1
    if is_local:
        _route_metrics["local_calls"] += 1
    else:
        _route_metrics["external_calls"] += 1
    log_entry["fallback"] = attempts > 1
    log_entry["source"] = "local" if is_local else "external"

    # Complexity distribution (heuristic from response length)
    text_len = len(str(resp.content)) if hasattr(resp, 'content') else 0
    if text_len < 200:
        _route_metrics["complexity_dist"]["simple"] += 1
    elif text_len < 800:
        _route_metrics["complexity_dist"]["medium"] += 1
    else:
        _route_metrics["complexity_dist"]["complex"] += 1

    # Recent log
    _route_metrics["recent_logs"].append(log_entry)
    if len(_route_metrics["recent_logs"]) > 50:
        _route_metrics["recent_logs"] = _route_metrics["recent_logs"][-50:]


def best_model_for_purpose(purpose: str) -> str:
    """Select the best LLM model for a given task purpose.

    Resolution chain:
      0. Explicit purpose-specific env var (AIPLAT_{PURPOSE}_MODEL)
         If env var contains commas, only the first model name is returned.
      1. Capability-based auto-selection (infra ModelManager.select_by_purpose)
      2. Env var resolution (infra ModelManager.get_default_model)
      3. Ultimate fallback (llm_profile.yaml fallback.ultimate_model)
    """
    import os as _os
    purpose_env = f"AIPLAT_{purpose.upper()}_MODEL"
    env_val = _os.getenv(purpose_env, "").strip()
    if env_val:
        # If comma-separated list, take the first (fallback handled by generate_with_fallback)
        first_model = env_val.split(",")[0].strip()
        _log_model_selection(purpose, first_model, entry="best_model_for_purpose",
                             source="env_" + purpose_env)
        return first_model

    # 1. Capability-based auto-selection (infra)
    try:
        from infra.management.model.manager import ModelManager
        mgr = _get_cached_model_manager()
        selected = mgr.select_by_purpose(purpose)
        if selected:
            _log_model_selection(purpose, selected, entry="best_model_for_purpose",
                                 source="infra_select_by_purpose")
            return selected
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # 2. Env var fallback via infra
    model_name = get_default_model(purpose=purpose) or "deepseek-chat"
    _log_model_selection(purpose, model_name, entry="best_model_for_purpose", source="fallback")
    return model_name


def best_model_for_agent_type(agent_type: str) -> str:
    """Resolve best model for a given agent type (e.g. 'rag', 'react', 'conversational').

    Maps agent types to purposes for centralized model resolution.
    """
    _AMT = {
        "rag": "chat",
        "react": "agent_creation",
        "conversational": "chat",
        "wiki_curator": "chat",
        "materials_chat": "chat",
        "plan_execute": "agent_creation",
    }
    purpose = _AMT.get(agent_type, "chat")
    return best_model_for_purpose(purpose)


def _register_adapter(provider: str, model_name: str, base_url: str = "", api_key: str = "") -> None:
    """Best-effort register adapter for Doctor/management visibility (DB + in-memory)."""
    try:
        from core.services.execution_store import get_execution_store
        from core.harness.kernel.runtime import get_kernel_runtime
        import asyncio

        store = get_execution_store()
        record = {
            "name": f"llm-{provider}",
            "provider": provider,
            "description": f"Auto-registered LLM adapter for {provider} ({model_name})",
            "api_base_url": base_url,
            "api_key": api_key,
            "models": [{"name": model_name}],
            "status": "active",
        }
        # 1) Persist to DB
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(store.upsert_adapter(record))
        except RuntimeError:
            pass

        # 2) Register in-memory (so list_adapters() returns it immediately)
        runtime = get_kernel_runtime()
        am = getattr(runtime, "adapter_manager", None) if runtime else None
        if am and hasattr(am, "_adapters"):
            from core.management.adapter_manager import AdapterInfo
            import uuid
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            adapter_id = f"adapter-{uuid.uuid4().hex[:8]}"
            info = AdapterInfo(
                id=adapter_id, name=record["name"], provider=provider,
                description=record["description"], status="active", api_key=api_key,
                api_base_url=base_url, models=[{"name": model_name}],
                created_at=now, updated_at=now,
            )
            am._adapters[adapter_id] = info
    except Exception as e:
        logging.warning(str(e), exc_info=True)
