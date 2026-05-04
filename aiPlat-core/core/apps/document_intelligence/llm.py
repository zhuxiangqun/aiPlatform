from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional


def llm_enabled() -> bool:
    api_key = (os.getenv("AIPLAT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
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
        or os.getenv("OPENAI_BASE_URL")
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
    api_key = (os.getenv("AIPLAT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
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
    """
    从 LLM 输出里尽量提取 JSON 对象。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # 直接 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # ```json ... ```
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None

