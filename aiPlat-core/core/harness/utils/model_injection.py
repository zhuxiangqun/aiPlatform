"""

Model injection helpers.



统一处理 "给 agent/skill 注入 LLM adapter" 的逻辑，避免：

- agent._model 被更新，但 agent._loop._model 仍旧为空（导致偶发失败）

- skill 注入仍强制 openai 且无 key（导致执行链路不稳定）

"""

# === capability_dependencies (Phase 43: auto-verified) ===

# depends_on:

#   - model-infrastructure:

#       symbols: [best_model_for_purpose, create_selected_adapter, ModelTierRouter]

#   - moa-multi-model-reasoning:

#       symbols: [is_moa_session, get_moa_preset]

#   - runtime-intervention:

#       symbols: [_model_overrides]

# === end ===



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

_adapter_models_injected: bool = False





def _get_cached_model_manager() -> Any:

    """Get or create the infra ModelManager singleton. Cached to avoid Ollama re-scan.

    After creation, the instance is registered with the infra management

    API's DI container so that the management UI and the model selection

    engine share the same _models dict.  Scanning / enabling / disabling

    models via the management UI takes effect immediately.

    """

    global _model_manager_cache

    if _model_manager_cache is not None:

        return _model_manager_cache

    from infra.management.model.manager import ModelManager

    _model_manager_cache = ModelManager()
    # 回注到 infra 管理 API 的 DI 容器，替换其临时占位实例
    try:
        from infra.management.api.main import get_infra_manager
        get_infra_manager().register("model", _model_manager_cache)
    except Exception:
            logging.getLogger(__name__).debug('管理 API 未加载时忽略（兼容 CLI / 测试场景）', exc_info=True)

    return _model_manager_cache





def _ensure_adapter_models_injected(mgr: Any) -> None:

    """Lazily inject adapter-based models (called before model selection, not at init)."""

    global _adapter_models_injected

    if _adapter_models_injected:

        return

    try:

        logging.info("Injecting adapter models into ModelManager...")

        count = _do_inject_adapter_models(mgr)

        if count > 0:

            logging.info("Adapter injection complete: %d models injected", count)

            _adapter_models_injected = True  # succeeded, no need to retry

    except Exception as e:

        logging.info("Adapter injection attempt failed: %s", e)





def _do_inject_adapter_models(mgr: Any) -> int:

    """Inject models from ExecutionStore adapters table into infra ModelManager.

    Returns the number of models injected."""

    injected = 0

    try:

        import json as _json



        # Resolve execution DB path from multiple sources

        db_path = None

        # Priority 1: kernel runtime (most reliable in server process)

        try:

            from core.harness.kernel.runtime import get_kernel_runtime

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            db_path = getattr(getattr(store, "_config", None), "db_path", None)

        except Exception:

            logging.getLogger(__name__).debug('_do_inject_adapter_models failed', exc_info=True)
        # Priority 2: env var

        if not db_path or not os.path.isfile(db_path):

            db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH") or ""

            if db_path and not os.path.isfile(db_path):

                db_path = ""

        # Priority 3: known paths

        if not db_path:

            for candidate in [

                os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),

                            "data", "aiplat_executions.sqlite3"),

            ]:

                if os.path.isfile(candidate):

                    db_path = candidate

                    break



        if not db_path or not os.path.isfile(db_path):

            logging.info("Adapter injection: no DB path found, skipping")

            return 0



        logging.info("Adapter injection: using DB %s", db_path)

        from infra.management.schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig



        conn = sqlite3.connect(str(db_path), timeout=5.0)

        conn.row_factory = sqlite3.Row

        try:

            rows = conn.execute(

                "SELECT adapter_id, name, provider, api_base_url, models_json "

                "FROM adapters WHERE status='active' "

                "AND ((api_key IS NOT NULL AND api_key != '') OR (api_key_enc IS NOT NULL AND api_key_enc != '')) "

                "ORDER BY updated_at DESC"

            ).fetchall()

            for row in rows:

                d = dict(row)

                provider = (d.get("provider") or "").strip().lower()

                base_url = (d.get("api_base_url") or "").strip()

                adapter_id = d.get("adapter_id") or ""

                models_json = d.get("models_json") or "[]"



                if not provider or not adapter_id:

                    continue



                try:

                    models = _json.loads(models_json) if isinstance(models_json, str) else models_json

                except Exception:

                    models = []



                model_name = ""

                if isinstance(models, list) and models:

                    first = models[0]

                    if isinstance(first, dict):

                        model_name = str(first.get("name") or first.get("model") or "")

                    elif isinstance(first, str):

                        model_name = first

                if not model_name:

                    model_name = f"{provider}-chat"



                if model_name in seen_names:

                    continue

                seen_names.add(model_name)



                provider_caps = {"chat"}

                if provider in ("deepseek", "openai"):

                    provider_caps = {"chat", "reasoning"}



                mi = ModelInfo(

                    id=f"adapter:{adapter_id}:{model_name}",

                    name=model_name,

                    type=ModelType.CHAT,

                    provider=provider,

                    source=ModelSource.EXTERNAL,

                    enabled=True,

                    status=ModelStatus.AVAILABLE,

                    config=ModelConfig(

                        adapter_id=adapter_id,

                        base_url=base_url or None,

                    ),

                    capabilities=list(provider_caps),

                )

                mgr._models[model_name] = mi

                injected += 1

                logging.info(

                    "Injected adapter model: %s (provider=%s, adapter=%s)",

                    model_name, provider, adapter_id,

                )

        finally:

            conn.close()

    except Exception as e:

        logging.info("Adapter model injection failed: %s", e)

    return injected





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

            with open(log_path) as f:

                samples = _log_json.loads(f.read())

        record = {"ts": _log_time.time(), "purpose": purpose,

                  "selected": selected, "entry": entry}

        if candidates:

            record["candidates"] = [{"name": n, "score": s} for s, n in candidates[:5]]

        if extra:

            record["extra"] = str(extra)[:200]

        samples.append(record)

        _log_os.makedirs(_log_os.path.dirname(log_path), exist_ok=True)

        with open(log_path, "w") as lf:

            _log_json.dump(samples[-1000:], lf)

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

        conn = sqlite3.connect(str(db_path), timeout=5.0)

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

            db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH")

        if not db_path or not os.path.isfile(str(db_path or "")):

            return None

        conn = sqlite3.connect(str(db_path), timeout=5.0)

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



        # Adapter-based API key resolution (management UI → adapters table)

        if needs_api_key and not api_key and model_info and model_info.config:

            adapter_id = getattr(model_info.config, "adapter_id", None)

            if adapter_id:

                ad = _load_adapter_from_store(str(adapter_id))

                if ad:

                    api_key = str(ad.get("api_key") or "")

                    if not base_url:

                        base_url = str(ad.get("api_base_url") or "")



    # Env var overrides (fallback only — adapter-based key takes priority)

    provider_env = os.getenv("AIPLAT_LLM_PROVIDER", "").strip()

    base_url_env = os.getenv("AIPLAT_LLM_BASE_URL", "").strip()

    api_key_env = (os.getenv("AIPLAT_LLM_API_KEY") or "").strip()



    if provider_env and not provider:

        provider = _norm_provider(provider_env)

    if base_url_env and needs_api_key and not base_url:

        base_url = base_url_env

    if api_key_env and needs_api_key and not api_key:

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

                    from core.harness.syscalls.llm import sys_llm_generate

                    resp = await _asyncio.wait_for(

                        sys_llm_generate(adapter, messages,

                                         model_name=model_name,

                                         gate_mode="minimal"),

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





import asyncio as _asyncio



def _adapter_key_exists(adapter_id: str) -> bool:

    """Check if adapter has a valid key in the adapters table."""

    try:

        from core.harness.kernel.runtime import get_kernel_runtime

        from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

        runtime = get_kernel_runtime()

        store = getattr(runtime, "execution_store", None) if runtime else None

        db_path = getattr(getattr(store, "_config", None), "db_path", None)

        if not db_path:

            db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH")

        if not db_path or not os.path.isfile(str(db_path)):

            return None

        conn = sqlite3.connect(str(db_path), timeout=5.0)

        try:

            row = conn.execute(

                "SELECT api_key, api_key_enc FROM adapters WHERE adapter_id=? LIMIT 1",

                (adapter_id,)

            ).fetchone()

            if not row:

                return False

            if row[1] and is_configured():

                return bool(decrypt_str(row[1]).strip())

            return bool((row[0] or "").strip())

        finally:

            conn.close()

    except Exception:

        return False





def _is_local_model(model_name: str, mgr) -> bool:

    """Check if a model has a local variant (Ollama, etc.) — check ALL models with this name."""

    for v in mgr._models.values():

        if v.name == model_name:

            source = getattr(v, 'source', None)

            if source and hasattr(source, 'value') and source.value == 'local':

                return True

    return False





def _model_is_usable(model_name: str, mgr, _local_names: set = None) -> bool:

    """Check if a model is usable.

    

    For models with adapter_id → checks adapters table for valid key.

    For local models → always usable.

    For external without credentials → not usable.

    _local_names: pre-computed set of model names that have local variants.

    """

    from infra.management.model.manager import ModelSource

    

    mi = mgr._models.get(model_name)

    if mi is None:

        for v in mgr._models.values():

            if v.name == model_name:

                mi = v

                break

    if mi is None:

        return True



    source = getattr(mi, 'source', None)

    is_local = source and hasattr(source, 'value') and source.value == "local"

    if is_local:

        return True



    cfg = getattr(mi, 'config', None)

    if cfg:

        adapter_id = getattr(cfg, 'adapter_id', None)

        if adapter_id and _adapter_key_exists(adapter_id):

            return True

        env_name = getattr(cfg, 'api_key_env', None)

        if env_name and os.getenv(env_name, "").strip():

            return True

    

    # Check local variant

    if _local_names and model_name in _local_names:

        return True

    if _local_names is None:

        for v in mgr._models.values():

            if v.name == model_name:

                vs = getattr(v, 'source', None)

                if vs and hasattr(vs, 'value') and vs.value == "local":

                    return True

    

    return False




def _load_llm_profile() -> dict:
    """加载 llm_profile.yaml 配置。系统配置为基础，工作区配置层叠覆盖。"""
    try:
        import yaml
        from pathlib import Path
    except ImportError:
        return {}

    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    sys_config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
        str(project_root / "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
    ws_config_path = str(project_root / "config" / "infra" / "llm_profile.yaml")

    # 系统默认为基础
    base = {}
    if os.path.isfile(sys_config_path):
        with open(sys_config_path) as f:
            base = yaml.safe_load(f) or {}

    # 工作区配置层叠覆盖（深度合并）
    if os.path.isfile(ws_config_path):
        with open(ws_config_path) as f:
            ws = yaml.safe_load(f) or {}
        for key, val in ws.items():
            if isinstance(val, dict) and isinstance(base.get(key), dict):
                base[key].update(val)
            else:
                base[key] = val

    return base


def _build_preferences(purpose: str) -> dict:
    """收集偏好参数（env var 和 model_overrides），不再硬覆盖。
    env var 指定的模型如果硬过滤通不过（RAM/VRAM 不足），记录 Warning 并忽略该偏好。
    size=None 的本地模型拒绝授予偏好（防止 OOM 风险）。
    """
    prefs = {}
    purpose_env = f"AIPLAT_{purpose.upper()}_MODEL"
    env_val = os.getenv(purpose_env, "").strip()
    if env_val:
        first = env_val.split(",")[0].strip()
        try:
            import psutil
            mgr = _get_cached_model_manager()
            model = mgr._find_model_by_name(first)
            if model is None:
                logging.getLogger(__name__).warning("Env var model '%s' not found in registry", first)
            elif model.size is None:
                # size=None 的本地模型：拒绝偏好（防止 OOM）
                if model.provider in ("openai", "deepseek", "anthropic", "openrouter"):
                    prefs["env_var_model"] = first  # API 模型安全
                else:
                    logging.getLogger(__name__).warning(
                        "Env var %s=%s has UNKNOWN size (Ollama not scanned?). "
                        "Refusing +500 preference to avoid OOM risk.",
                        purpose_env, first)
            elif model.size == 0:
                prefs["env_var_model"] = first  # API 模型显式 size=0
            elif model.size > 0:
                ram = psutil.virtual_memory().available
                if model.size > ram:
                    logging.getLogger(__name__).warning(
                        "Env var %s=%s requires %.1fGB > available %.1fGB — ignoring",
                        purpose_env, first, model.size / 1e9, ram / 1e9)
                else:
                    prefs["env_var_model"] = first
        except Exception:
            logging.getLogger(__name__).debug('_build_preferences failed', exc_info=True)

    # model_overrides（兼容保留）
    profile = _load_llm_profile()
    override = profile.get("model_overrides", {}).get(purpose)
    if override:
        prefs["override_model"] = override

    return prefs


def best_model_for_purpose(purpose: str, messages: list = None) -> str:
    """选择最优 LLM 模型。所有路径收敛到 unified_pipeline 统一评分。

    Resolution chain:
      0. Session-level override (/model command)
      0.5 Non-LLM capability shortcuts (tts, stt, ocr)
      1. unified_pipeline: hard filter → soft filter → score → safe model
    """
    # Step 0: Session-level model override (/model command)
    override = _get_session_model_override()
    if override:
        _log_model_selection(purpose, override, entry="best_model_for_purpose",
                             source="session_override")
        return override

    # Step 0.5: Non-LLM capability shortcuts
    if purpose == "tts":
        profile = _load_llm_profile()
        tts_config = profile.get("tts", {})
        model = tts_config.get("default", "piper_zh_CN")
        _log_model_selection(purpose, model, entry="best_model_for_purpose", source="tts_shortcut")
        return model

    # Step 1: 构建偏好参数（env var 和 model_overrides 不再硬覆盖）
    preferences = _build_preferences(purpose)

    # Step 2: 加载配置
    profile_data = _load_llm_profile()

    # Step 3: 统一评分管道
    try:
        mgr = _get_cached_model_manager()
        _ensure_adapter_models_injected(mgr)
        result = mgr.unified_pipeline(purpose, messages, preferences, profile_data)
        _log_model_selection(purpose, result, entry="best_model_for_purpose",
                             source="unified_pipeline")
        return result
    except RuntimeError:
        raise
    except Exception as e:
        logging.getLogger(__name__).critical("Model selection failed: %s", e, exc_info=True)
        # 终极保底
        fallback = profile_data.get("fallback", {}).get("safe_model", "qwen2.5:3b")
        _log_model_selection(purpose, fallback, entry="best_model_for_purpose",
                             source="exception_fallback")
        return fallback





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

            pass  # noqa: cleanup-best-effort



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





# ── Phase 13: Session-level model override (/model command) ──

_model_overrides: Dict[str, str] = {}





def _get_session_model_override() -> Optional[str]:

    """Check for session-level model override set by /model command.

    Skips MoA markers (moa:preset) — those are handled separately."""

    val = _model_overrides.get("_global", None)

    if val and str(val).startswith("moa:"):

        return None  # MoA handled by moa_executor, not best_model_for_purpose

    return val





def set_model_override(model_name: str, session_id: str = "_global") -> None:

    """Set a session-level model override."""

    _model_overrides[session_id] = model_name

    logging.getLogger("aiplat.model").info("Model override: %s (session=%s)", model_name, session_id)





def clear_model_override(session_id: str = "_global") -> None:

    """Clear session-level model override."""

    _model_overrides.pop(session_id, None)





# ── Phase 42: MoA session mode ──





def is_moa_session() -> bool:

    """Check if the current session is in MoA mode."""

    return str(_model_overrides.get("_global", "")).startswith("moa:")





def get_moa_preset() -> str:

    """Get the MoA preset for the current session."""

    val = str(_model_overrides.get("_global", ""))

    if val.startswith("moa:"):

        return val.split(":", 1)[1] or "general"

    return "general"


