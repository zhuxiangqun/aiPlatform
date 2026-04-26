"""
Model injection helpers.

统一处理 “给 agent/skill 注入 LLM adapter” 的逻辑，避免：
- agent._model 被更新，但 agent._loop._model 仍旧为空（导致偶发失败）
- skill 注入仍强制 openai 且无 key（导致执行链路不稳定）
"""

from __future__ import annotations

import os
from typing import Any, Optional
import json
import sqlite3


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
    from core.adapters.llm import create_adapter

    # Highest priority: explicit env overrides
    provider_env = os.getenv("AIPLAT_LLM_PROVIDER", "").strip()
    model_env = os.getenv("AIPLAT_LLM_MODEL", "").strip()
    base_url_env = os.getenv("AIPLAT_LLM_BASE_URL", "").strip()
    api_key_env = (os.getenv("AIPLAT_LLM_API_KEY") or "").strip()

    # Next priority: global default routing stored in ExecutionStore (set by Onboarding)
    default_llm = None if provider_env else _load_default_llm_from_store()
    selected_model = model_env or (default_llm.get("model") if default_llm else "") or model_name

    # Provider resolution
    provider = _norm_provider(provider_env or "openai")

    # Provider-specific defaults (OpenAI-compatible).
    if provider == "deepseek":
        # DeepSeek官方文档：可用 base_url=https://api.deepseek.com 或 https://api.deepseek.com/v1
        # 为兼容 OpenAI SDK 的默认 /v1 路径，这里默认使用 /v1。
        base_url = (
            os.getenv("AIPLAT_LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        api_key = os.getenv("AIPLAT_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
        # If user kept default model_name (gpt-4), map to deepseek-chat by default.
        if selected_model in ("gpt-4", "gpt-4o", "gpt-3.5-turbo"):
            selected_model = "deepseek-chat"
        # DeepSeek is OpenAI-compatible → use openai adapter.
        return create_adapter(provider="openai", api_key=api_key or None, model=selected_model, base_url=base_url)

    # Generic providers
    # If no explicit env provider set, try default_llm adapter config.
    if default_llm and default_llm.get("adapter_id"):
        ad = _load_adapter_from_store(str(default_llm.get("adapter_id")))
        if ad:
            provider = _norm_provider(str(ad.get("provider") or provider))
            base_url = str(ad.get("api_base_url") or base_url_env or os.getenv("OPENAI_BASE_URL") or "")
            api_key = str(ad.get("api_key") or api_key_env or os.getenv("OPENAI_API_KEY") or "")
            # For OpenAI-compatible adapters, use openai provider
            if provider in {"openai", "deepseek"}:
                provider = "openai"
            return create_adapter(provider=provider, api_key=api_key or None, model=selected_model, base_url=base_url or None)

    base_url = base_url_env or os.getenv("OPENAI_BASE_URL")
    api_key = (os.getenv("OPENAI_API_KEY") or api_key_env or "")
    if provider == "openai" and not api_key:
        provider = "mock"
    return create_adapter(provider=provider, api_key=api_key or None, model=selected_model, base_url=base_url)


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
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIPLAT_LLM_API_KEY") or ""
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
