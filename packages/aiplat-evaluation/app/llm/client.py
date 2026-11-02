"""Optional LLM client for Eval Worker (OpenAI-compatible HTTP or local stub).

Honesty:
- Default off — runners stay deterministic / fail-closed.
- Does **not** call Central HTTP; does **not** import ``core.harness``.
- Points at an independent provider URL (same stack as infra ModelManager).
- ``accuracy_claim`` remains false at caller; this module never asserts accuracy.

Env:
- ``AIPLAT_EVAL_LLM=0|1|stub|http`` (alias: true/yes → http if BASE_URL else stub)
- ``AIPLAT_EVAL_LLM_BASE_URL`` — e.g. http://127.0.0.1:11434/v1
- ``AIPLAT_EVAL_LLM_API_KEY`` — optional Bearer
- ``AIPLAT_EVAL_LLM_MODEL`` — model id (default ``local``)
- ``AIPLAT_EVAL_LLM_TIMEOUT`` — seconds (default 30)
- ``AIPLAT_EVAL_LLM_STUB_OUTPUT`` — stub mode fixed output
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Literal, Optional

LlmMode = Literal["off", "stub", "http"]


def llm_mode() -> LlmMode:
    raw = (os.environ.get("AIPLAT_EVAL_LLM") or "0").strip().lower()
    if raw in ("0", "false", "off", "no", ""):
        return "off"
    if raw in ("stub", "local_stub"):
        return "stub"
    if raw in ("1", "true", "yes", "http", "on"):
        if (os.environ.get("AIPLAT_EVAL_LLM_BASE_URL") or "").strip():
            return "http"
        # Enabled without URL → stub so local engineering does not hang on network.
        return "stub"
    return "off"


def llm_enabled() -> bool:
    return llm_mode() != "off"


def complete_text(
    prompt: str,
    *,
    job_id: str = "",
    tenant_id: str = "",
    runner_id: str = "prompt_eval",
    purpose: str = "prompt_eval",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Return ``{ok, text, audit}``. Never raises for provider miss — ok=False."""
    mode = llm_mode()
    if mode == "off":
        return {
            "ok": False,
            "text": "",
            "audit": _audit(
                mode=mode,
                purpose=purpose,
                model="",
                job_id=job_id,
                tenant_id=tenant_id,
                runner_id=runner_id,
                detail="llm_disabled",
            ),
        }
    if mode == "stub":
        text = (os.environ.get("AIPLAT_EVAL_LLM_STUB_OUTPUT") or "").strip()
        if not text:
            text = f"[stub]{prompt[:200]}"
        return {
            "ok": True,
            "text": text,
            "audit": _audit(
                mode=mode,
                purpose=purpose,
                model=model or "stub",
                job_id=job_id,
                tenant_id=tenant_id,
                runner_id=runner_id,
                latency_ms=0,
                detail="stub_no_network",
            ),
        }
    return _http_complete(
        prompt,
        job_id=job_id,
        tenant_id=tenant_id,
        runner_id=runner_id,
        purpose=purpose,
        model=model,
    )


def _http_complete(
    prompt: str,
    *,
    job_id: str,
    tenant_id: str,
    runner_id: str,
    purpose: str,
    model: Optional[str],
) -> Dict[str, Any]:
    base = (os.environ.get("AIPLAT_EVAL_LLM_BASE_URL") or "").rstrip("/")
    if not base:
        return {
            "ok": False,
            "text": "",
            "audit": _audit(
                mode="http",
                purpose=purpose,
                model="",
                job_id=job_id,
                tenant_id=tenant_id,
                runner_id=runner_id,
                detail="missing_AIPLAT_EVAL_LLM_BASE_URL",
            ),
        }
    model_id = (model or os.environ.get("AIPLAT_EVAL_LLM_MODEL") or "local").strip()
    timeout = float(os.environ.get("AIPLAT_EVAL_LLM_TIMEOUT") or "30")
    url = f"{base}/chat/completions"
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = (os.environ.get("AIPLAT_EVAL_LLM_API_KEY") or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    raw_req = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=raw_req, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": False,
            "text": "",
            "audit": _audit(
                mode="http",
                purpose=purpose,
                model=model_id,
                job_id=job_id,
                tenant_id=tenant_id,
                runner_id=runner_id,
                latency_ms=latency_ms,
                detail=f"provider_error:{type(exc).__name__}",
            ),
        }

    text = _extract_content(payload)
    usage = payload.get("usage") if isinstance(payload, dict) else None
    tokens_in = int((usage or {}).get("prompt_tokens") or 0) if isinstance(usage, dict) else 0
    tokens_out = int((usage or {}).get("completion_tokens") or 0) if isinstance(usage, dict) else 0
    ok = bool(str(text).strip())
    return {
        "ok": ok,
        "text": str(text),
        "audit": _audit(
            mode="http",
            purpose=purpose,
            model=model_id,
            job_id=job_id,
            tenant_id=tenant_id,
            runner_id=runner_id,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            detail="" if ok else "empty_completion",
        ),
    }


def _extract_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            return str(msg.get("content") or "")
        return str(choices[0].get("text") or "")
    return str(payload.get("response") or payload.get("text") or "")


def _audit(
    *,
    mode: str,
    purpose: str,
    model: str,
    job_id: str,
    tenant_id: str,
    runner_id: str,
    latency_ms: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    detail: str = "",
) -> Dict[str, Any]:
    return {
        "purpose": purpose,
        "model": model,
        "mode": mode,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "runner_id": runner_id,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_estimate": 0.0,
        "detail": detail,
        "central_http": False,
        "process_split_authorized": False,
    }


def _wire_llm() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = llm_enabled()
    return complete_text("ping", job_id="job_wire", purpose="prompt_eval")
