"""Document Intelligence LLM client — unified LLM calls for summarization/query.

All LLM calls go through sys_llm_generate → Gate → Guard → Trace (no raw HTTP).

callers: aiPlat-platform/kb/intelligence/llm.py (re-export stub),
         summarizer.py, query.py via platform proxy
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url


def llm_enabled() -> bool:
    api_key = (os.getenv("AIPLAT_LLM_API_KEY") or get_llm_api_key("openai") or "").strip()
    model_name = _default_model_name()
    return bool(api_key and model_name)


def _default_model_name() -> str:
    from core.harness.utils.model_injection import get_default_model
    return get_default_model(purpose="document") or best_model_for_purpose("document")


async def chat_complete(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> Optional[str]:
    """Call LLM via Harness syscall."""
    from core.harness.syscalls.llm import sys_llm_generate
    from core.harness.utils.model_injection import create_selected_adapter

    model_name = _default_model_name()
    try:
        model = create_selected_adapter(model_name=model_name)
    except Exception:
        return None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = await sys_llm_generate(
            model, messages,
            trace_context={"source": "document_intelligence", "model": model_name},
            model_name=model_name,
        )
        content = getattr(response, "content", None) or ""
        return content.strip() if content else None
    except Exception:
        return None


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM output via CoreFacade."""
    from core.utils.json_utils import parse_json
    return parse_json(text)
