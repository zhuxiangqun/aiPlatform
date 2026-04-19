"""
Model injection helpers.

统一处理 “给 agent/skill 注入 LLM adapter” 的逻辑，避免：
- agent._model 被更新，但 agent._loop._model 仍旧为空（导致偶发失败）
- skill 注入仍强制 openai 且无 key（导致执行链路不稳定）
"""

from __future__ import annotations

import os
from typing import Any, Optional


def create_selected_adapter(*, model_name: str) -> Any:
    """Create adapter based on env vars, with dev-friendly fallback to mock."""
    from core.adapters.llm import create_adapter

    provider = os.getenv("AIPLAT_LLM_PROVIDER", "openai").strip().lower() or "openai"
    base_url = os.getenv("AIPLAT_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIPLAT_LLM_API_KEY") or ""
    if provider == "openai" and not api_key:
        provider = "mock"
    return create_adapter(provider=provider, api_key=api_key or None, model=model_name, base_url=base_url)


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

