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
    """Resolve LLM API key for the given provider.

    Checks in order:
    1. AIPLAT_LLM_API_KEY (generic, provider-agnostic)
    2. {PROVIDER}_API_KEY (e.g., OPENAI_API_KEY)
    3. Environment variable named by provider (e.g., DEEPSEEK_API_KEY)
    """
    generic = os.getenv("AIPLAT_LLM_API_KEY", "")
    if generic:
        return generic
    if provider:
        key = os.getenv(f"{provider.upper()}_API_KEY", "")
        if key:
            return key
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
