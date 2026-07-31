"""
Centralized LLM API key and base URL resolution.

Replaces scattered os.getenv("OPENAI_API_KEY") / os.getenv("ANTHROPIC_API_KEY")
hardcoding across the codebase with a single resolver that checks generic
env vars first, then falls back to provider-specific ones.

Priority: AIPLAT_LLM_API_KEY > {PROVIDER}_API_KEY > None
"""

import os
from typing import Optional


def get_llm_api_key(provider: str = "") -> Optional[str]:
    """Resolve LLM API key — infra ModelManager PRIMARY, env FALLBACK.

    Checks in order:
    1. infra ModelManager credential pool (primary, architecture-aligned)
    2. AIPLAT_LLM_API_KEY (generic env)
    3. {PROVIDER}_API_KEY (e.g., DEEPSEEK_API_KEY)
    4. DEEPSEEK_API_KEY (broad fallback, many providers use DeepSeek-compatible API)
    """
    import os as _os
    # PRIMARY: infra ModelManager
    try:
        from core.harness.infrastructure.infra_bridge import get_infra_bridge
        bridge = get_infra_bridge()
        mgr = bridge.get_model_manager()
        if mgr and hasattr(mgr, "get_credentials"):
            # Try specific provider first, then deepseek as universal fallback
            for p in (provider, "deepseek"):
                if not p:
                    continue
                creds = mgr.get_credentials(p)
                if creds and creds.get("api_key"):
                    return creds["api_key"]
    except Exception:
        import logging
        logging.getLogger(__name__).debug("infra credential lookup failed, falling back to env vars")

    # FALLBACK: env vars
    generic = _os.getenv("AIPLAT_LLM_API_KEY", "")
    if generic:
        return generic
    if provider:
        key = _os.getenv(f"{provider.upper()}_API_KEY", "")
        if key:
            return key
    # Broad fallback: DEEPSEEK_API_KEY works for any OpenAI-compatible provider
    deepseek_key = _os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        return deepseek_key
    return None


def get_llm_base_url(provider: str = "") -> Optional[str]:
    """Resolve LLM base URL for the given provider.

    Checks in order:
    1. AIPLAT_LLM_BASE_URL (generic)
    2. {PROVIDER}_BASE_URL (e.g., OPENAI_BASE_URL)
    """
    generic = os.getenv("AIPLAT_LLM_BASE_URL", "")
    if generic:
        return generic
    if provider:
        url = os.getenv(f"{provider.upper()}_BASE_URL", "")
        if url:
            return url
    return None
