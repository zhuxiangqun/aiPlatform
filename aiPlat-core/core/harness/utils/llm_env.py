"""
Centralized LLM API key resolution — infra CredentialPool ONLY.

Single source of truth: infra ModelManager → CredentialPool.
No env var fallbacks — if a model isn't registered in infra, it doesn't exist.
"""
import os
from typing import Optional


def get_llm_api_key(provider: str = "") -> Optional[str]:
    """Resolve LLM API key — infra ModelManager credential pool ONLY."""
    import os as _os
    try:
        from core.harness.infrastructure.infra_bridge import get_infra_bridge
        bridge = get_infra_bridge()
        mgr = bridge.get_model_manager()
        if mgr and hasattr(mgr, "get_credentials"):
            for p in (provider, "deepseek"):
                if not p:
                    continue
                creds = mgr.get_credentials(p)
                if creds and creds.get("api_key"):
                    return creds["api_key"]
    except Exception:
        import logging
        logging.getLogger(__name__).debug("infra credential lookup failed")
    return None


def get_llm_base_url(provider: str = "") -> Optional[str]:
    """Resolve LLM base URL — infra ModelManager ONLY."""
    try:
        from core.harness.infrastructure.infra_bridge import get_infra_bridge
        bridge = get_infra_bridge()
        mgr = bridge.get_model_manager()
        if mgr and hasattr(mgr, "select"):
            info = mgr.select(provider) if provider else None
            if info and info.get("base_url"):
                return info["base_url"]
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return None
