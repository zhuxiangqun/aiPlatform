"""
Model injection helpers.

统一处理 "给 agent/skill 注入 LLM adapter" 的逻辑，避免：
- agent._model 被更新，但 agent._loop._model 仍旧为空（导致偶发失败）
- skill 注入仍强制 openai 且无 key（导致执行链路不稳定）
"""

from __future__ import annotations

import os
from typing import Any, Optional
import json
import sqlite3

from core.adapters.llm.base import create_adapter


def get_default_model(purpose: str = "default") -> str:
    """Centralized default model selection — delegates to infra ModelManager.

    Resolution chain: infra ModelManager.get_default_model() → env vars → fallback.
    All modules MUST use this function instead of reading AIPLAT_*_MODEL env vars directly.
    """
    # Primary: infra ModelManager (unique source of truth)
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        result = mgr.get_default_model(purpose)
        if result:
            return result
    except Exception:
        pass

    # Fallback: direct env var reading (backward compat)
    if purpose in ("agent", "reasoning"):
        return os.getenv("AIPLAT_AGENT_MODEL") or os.getenv("AIPLAT_DEFAULT_AGENT_MODEL") or os.getenv("AIPLAT_DEFAULT_MODEL", "")
    if purpose == "document":
        return os.getenv("AIPLAT_DOC_LLM_MODEL") or os.getenv("AIPLAT_LLM_MODEL") or os.getenv("AIPLAT_DEFAULT_CHAT_MODEL") or os.getenv("AIPLAT_DEFAULT_MODEL", "")
    if purpose == "code_gen":
        return os.getenv("AIPLAT_CODE_GEN_MODEL") or os.getenv("AIPLAT_LLM_MODEL") or os.getenv("AIPLAT_DEFAULT_MODEL", "")
    if purpose == "query_translation":
        return os.getenv("AIPLAT_QUERY_MODEL") or os.getenv("AIPLAT_DEFAULT_CHAT_MODEL") or os.getenv("AIPLAT_LLM_MODEL") or os.getenv("AIPLAT_DEFAULT_MODEL", "")
    return os.getenv("AIPLAT_DEFAULT_CHAT_MODEL") or os.getenv("AIPLAT_LLM_MODEL") or os.getenv("AIPLAT_DEFAULT_MODEL", "")


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
        conn = sqlite3.connect(str(db_path))
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
        conn = sqlite3.connect(str(db_path))
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
            except Exception:
                pass
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
    """Create adapter based on env vars, with dev-friendly fallback to mock."""
    from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url

    # Highest priority: explicit env overrides
    provider_env = os.getenv("AIPLAT_LLM_PROVIDER", "").strip()
    model_env = os.getenv("AIPLAT_LLM_MODEL", "").strip()
    base_url_env = os.getenv("AIPLAT_LLM_BASE_URL", "").strip()
    api_key_env = (os.getenv("AIPLAT_LLM_API_KEY") or "").strip()

    # Next priority: global default routing stored in ExecutionStore (set by Onboarding)
    default_llm = None if provider_env else _load_default_llm_from_store()
    # model_name (explicit parameter) > model_env (global) > store default
    selected_model = model_name or model_env or (default_llm.get("model") if default_llm else "") or get_default_model()

    # Provider resolution
    provider = _norm_provider(provider_env or os.getenv("AIPLAT_DEFAULT_PROVIDER", ""))

    # Provider-specific defaults (OpenAI-compatible).
    if provider == "deepseek":
        # DeepSeek官方文档：可用 base_url=https://api.deepseek.com 或 https://api.deepseek.com/v1
        # 为兼容 OpenAI SDK 的默认 /v1 路径，这里默认使用 /v1。
        base_url = (
            os.getenv("AIPLAT_LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        api_key = os.getenv("AIPLAT_LLM_API_KEY") or ""
        # If user kept default model_name (gpt-4), map to deepseek-chat by default.
        if selected_model in ("gpt-4", "gpt-4o", "gpt-3.5-turbo"):
            selected_model = get_default_model()
        # DeepSeek API is OpenAI-compatible — use openai adapter with DeepSeek base_url.
        return create_adapter(provider="openai", api_key=api_key or None, model=selected_model, base_url=base_url)

    # Generic providers
    # If no explicit env provider set, try default_llm adapter config.
    if default_llm and default_llm.get("adapter_id"):
        ad = _load_adapter_from_store(str(default_llm.get("adapter_id")))
        if ad:
            provider = _norm_provider(str(ad.get("provider") or provider))
            base_url = str(ad.get("api_base_url") or base_url_env or get_llm_base_url("deepseek") or "")
            api_key = str(ad.get("api_key") or api_key_env or get_llm_api_key("deepseek") or "")
            if provider in {"openai", "deepseek"}:
                provider = "openai"
            return create_adapter(provider=provider, api_key=api_key or None, model=selected_model, base_url=base_url or None)

    base_url = base_url_env or get_llm_base_url("deepseek")
    api_key = (get_llm_api_key("deepseek") or api_key_env or "")
    if not api_key:
        raise RuntimeError(
            "No API key configured for LLM. "
            "Set AIPLAT_LLM_API_KEY or DEEPSEEK_API_KEY environment variable. "
            "Without a valid API key, the pipeline cannot produce real outputs."
        )


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
            except Exception:
                pass
    else:
        try:
            setattr(obj, "_model", adapter)
        except Exception:
            pass

    # 2) bind to internal loop (common pattern)
    try:
        loop = getattr(obj, "_loop", None)
        if loop is not None:
            if hasattr(loop, "set_model"):
                try:
                    loop.set_model(adapter)  # type: ignore[attr-defined]
                except Exception:
                    pass
            elif hasattr(loop, "_model"):
                try:
                    setattr(loop, "_model", adapter)
                except Exception:
                    pass
    except Exception:
        pass


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

    # If current is openai but no api key, override to mock (prevents empty output).
    try:
        cur_provider = getattr(getattr(cur, "metadata", None), "provider", None)
        api_key = get_llm_api_key("openai") or ""
        if cur_provider == "openai" and not api_key:
            _bind_model(agent, adapter)
            return adapter
    except Exception:
        pass

    # Still ensure loop model matches agent model (root cause of flakiness)
    try:
        loop = getattr(agent, "_loop", None)
        loop_model = getattr(loop, "_model", None) if loop is not None else None
        if loop is not None and loop_model is None:
            _bind_model(agent, cur)
    except Exception:
        pass

    return cur


def ensure_skill_model(skill: Any, *, model_name: str, force: bool = False) -> Any:
    adapter = create_selected_adapter(model_name=model_name)
    cur = getattr(skill, "_model", None)
    if force or cur is None:
        _bind_model(skill, adapter)
        return adapter
    return cur


# ── Task-aware model selection (§model selection by purpose) ─────────────────

PURPOSE_PROFILE: dict = {
    "wiki_curation": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
    },
    "eval_code": {
        "prefer": ["chat", "reasoning"],
        "avoid": [],
    },
    "agent": {
        "prefer": ["reasoning", "chat"],
        "avoid": [],
    },
    "chat": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
    },
    "code_gen": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
    },
    "document": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
    },
    "agent_creation": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
    },
    "query_translation": {
        "prefer": ["chat"],
        "avoid": ["reasoning"],
        "prefer_local": True,  # Prefer local models (Ollama/LM Studio) — 0 cost
    },
}

_DEFAULT_PROFILE = {"prefer": ["chat"], "avoid": []}


def _select_from_infra(purpose: str) -> Optional[str]:
    """Select the best model for a purpose from infra ModelManager by capability matching."""
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        # Access pre-loaded models directly (they're populated in __init__ before
        # async scanning; sync access avoids coroutine issues)
        models = list(mgr._models.values()) if hasattr(mgr, "_models") else []
    except Exception:
        return None

    if not models:
        return None

    profile = PURPOSE_PROFILE.get(purpose, _DEFAULT_PROFILE)
    chat_models = [m for m in models if hasattr(m, 'type') and m.type.value == "chat" and m.enabled]

    scored: list = []
    for m in chat_models:
        caps = set(m.capabilities or ["chat"])

        # Must have at least one preferred capability
        if not any(c in caps for c in profile["prefer"]):
            continue

        # Must not have any avoided capability
        if any(c in caps for c in profile["avoid"]):
            continue

        score = 0
        if profile.get("prefer_local"):
            # Prefer local models for low-stakes tasks (e.g., NL→graph translation)
            if m.source.value in ("local", "external"):
                score += 120
            else:
                score += 40  # Remote still acceptable as fallback
        elif m.source.value == "config":
            score += 100  # Remote API > local for production tasks
        if "reasoning" in caps:
            if profile["prefer"][0] == "reasoning":
                score += 80  # Reasoning-required tasks: reasoning is a plus
            else:
                score -= 30  # Non-reasoning tasks: reasoning is unwanted overhead
        else:
            if profile["prefer"][0] != "reasoning":
                score += 50  # Non-reasoning for non-reasoning tasks: cheaper, faster
        if "function_call" in caps:
            score += 20
        if m.name == "deepseek-chat" and profile["prefer"][0] != "reasoning":
            score += 30  # Preferred default for non-reasoning tasks

        scored.append((score, m.name))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def best_model_for_purpose(purpose: str) -> str:
    """Select the best LLM model for a given task purpose.

    Resolution chain:
      1. infra ModelManager — match by task profile (capability, cost, source)
      2. get_default_model(purpose) — env var + system default (fallback)
    """
    selected = _select_from_infra(purpose)
    if selected:
        return selected
    return get_default_model(purpose=purpose) or "deepseek-chat"
