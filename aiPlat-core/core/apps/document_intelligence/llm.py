from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url


def llm_enabled() -> bool:
    api_key = (os.getenv("AIPLAT_LLM_API_KEY") or get_llm_api_key("openai") or "").strip()
    model = (
        os.getenv("AIPLAT_DOC_LLM_MODEL")
        or os.getenv("AIPLAT_LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or ""
    ).strip()
    return bool(api_key and model)


def _chat_completions_url() -> str:
    base = (
        os.getenv("AIPLAT_LLM_BASE_URL")
        or get_llm_base_url("openai")
        or "https://api.openai.com/v1"
    ).strip()
    if base.endswith("/"):
        base = base[:-1]
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _default_model() -> str:
    return (
        os.getenv("AIPLAT_DOC_LLM_MODEL")
        or os.getenv("AIPLAT_LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    ).strip()


def chat_complete(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> Optional[str]:
    """
    轻量 OpenAI-compatible 调用。
    失败返回 None，调用方自行走 fallback。
    """
    api_key = (os.getenv("AIPLAT_LLM_API_KEY") or get_llm_api_key("openai") or "").strip()
    if not api_key:
        return None
    model = _default_model()
    url = _chat_completions_url()
    timeout = int(os.getenv("AIPLAT_DOC_LLM_TIMEOUT_SECONDS", "45"))
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="ignore"))
        choices = body.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "\n".join([p for p in parts if p]).strip() or None
    except Exception:
        return None
    return None


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM output. Delegates to the canonical facade."""
    from core.api.core_facade import parse_json
    return parse_json(text)

