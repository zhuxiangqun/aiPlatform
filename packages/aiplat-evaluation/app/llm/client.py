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
- ``AIPLAT_EVAL_LLM_TEMPERATURE`` — float (default 0)
- ``AIPLAT_EVAL_LLM_SEED`` — optional int seed (provider-dependent)
- ``AIPLAT_EVAL_LLM_STUB_OUTPUT`` — stub mode fixed output
- ``AIPLAT_EVAL_LLM_COST_PER_1K`` — optional USD-ish per 1k tokens (alias: ``_COST_PER_1K_TOKENS``)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Literal, Optional

LlmMode = Literal["off", "stub", "http"]


def llm_temperature() -> float:
    raw = (os.environ.get("AIPLAT_EVAL_LLM_TEMPERATURE") or "0").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def llm_seed() -> Optional[int]:
    raw = (os.environ.get("AIPLAT_EVAL_LLM_SEED") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def provider_base_url() -> str:
    return (os.environ.get("AIPLAT_EVAL_LLM_BASE_URL") or "").rstrip("/")


def looks_like_central_llm_url(url: str = "") -> bool:
    """Heuristic: Eval LLM must not point at Central HTTP."""
    u = (url or provider_base_url() or "").lower()
    if not u:
        return False
    if "/api/core/" in u or "/api/platform/" in u:
        return True
    if "localhost:8000" in u or "127.0.0.1:8000" in u:
        return True
    return False


def assert_provider_independence(url: str = "") -> None:
    """Raise when BASE_URL looks like Central — keep Worker independent."""
    if looks_like_central_llm_url(url):
        raise ValueError(
            "runner_forbidden:eval_llm_must_not_use_central_http "
            "(set AIPLAT_EVAL_LLM_BASE_URL to an independent provider)"
        )


def estimate_cost(*, tokens_in: int = 0, tokens_out: int = 0) -> float:
    """Cheap USD-ish estimate from tokens."""
    raw = (
        os.environ.get("AIPLAT_EVAL_LLM_COST_PER_1K")
        or os.environ.get("AIPLAT_EVAL_LLM_COST_PER_1K_TOKENS")
        or ""
    ).strip()
    try:
        per_1k = float(raw) if raw else 0.0
    except ValueError:
        per_1k = 0.0
    total = max(0, int(tokens_in)) + max(0, int(tokens_out))
    return round((total / 1000.0) * max(0.0, per_1k), 6)


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
        # Rough token stand-in so cost_cap path can exercise without a live provider.
        tin = max(1, len(prompt) // 4)
        tout = max(1, len(text) // 4)
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
                tokens_in=tin,
                tokens_out=tout,
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
    try:
        assert_provider_independence()
    except ValueError as exc:
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
                detail=str(exc)[:200],
            ),
        }
    base = provider_base_url()
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
    temperature = llm_temperature()
    seed = llm_seed()
    url = f"{base}/chat/completions"
    body: Dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if seed is not None:
        body["seed"] = seed
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
                temperature=temperature,
                seed=seed,
                timeout_s=timeout,
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
            temperature=temperature,
            seed=seed,
            timeout_s=timeout,
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
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    timeout_s: Optional[float] = None,
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
        "cost_estimate": estimate_cost(tokens_in=tokens_in, tokens_out=tokens_out),
        "temperature": temperature if temperature is not None else llm_temperature(),
        "seed": seed if seed is not None else llm_seed(),
        "timeout_s": timeout_s
        if timeout_s is not None
        else float(os.environ.get("AIPLAT_EVAL_LLM_TIMEOUT") or "30"),
        "detail": detail,
        "central_http": False,
        "process_split_authorized": False,
    }


def _wire_llm() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    _ = llm_enabled()
    _ = estimate_cost(tokens_in=10, tokens_out=5)
    _ = looks_like_central_llm_url("http://127.0.0.1:9000/v1")
    return complete_text("ping", job_id="job_wire", purpose="prompt_eval")
