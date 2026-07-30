"""

ErrorTranslator — multi-provider LLM error classification pipeline.



Aligns with hermes-agent's error_classifier.py architecture:

  7-level priority pipeline → ClassifiedError with 4 recovery flags.



Provider extensibility: subclass BaseErrorTranslator + register in _PROVIDER_REGISTRY.

Adding Qwen/Claude requires ONLY a new Translator class — no pipeline changes.

"""



from __future__ import annotations

import enum

import json

import logging

import re

from dataclasses import dataclass, field

from typing import Any, Dict, Optional



logger = logging.getLogger(__name__)





# ══════════════════════════════════════════════════════════════

# 1. FailoverReason — 19 种错误根因

# ══════════════════════════════════════════════════════════════



class FailoverReason(enum.Enum):

    """Error root cause — determines recovery strategy."""



    auth = "auth"                          # 401/403 — rotate credential

    auth_permanent = "auth_permanent"      # Auth failed after refresh

    billing = "billing"                    # 402 credit exhausted

    rate_limit = "rate_limit"              # 429 or transient quota

    overloaded = "overloaded"              # 503/529 provider overloaded

    server_error = "server_error"          # 500/502 internal server error

    timeout = "timeout"                    # Connection/read timeout

    context_overflow = "context_overflow"   # Prompt exceeds context window

    payload_too_large = "payload_too_large" # 413

    model_not_found = "model_not_found"    # 404 invalid model

    format_error = "format_error"          # 400 generic bad request

    param_out_of_range = "param_out_of_range"  # max_tokens/temperature exceeded

    thinking_signature = "thinking_signature"  # Anthropic thinking block sig

    long_context_tier = "long_context_tier"    # Anthropic tier gate

    unknown = "unknown"                    # Unclassifiable





# ══════════════════════════════════════════════════════════════

# 2. ClassifiedError — recovery hints (consumer reads flags only)

# ══════════════════════════════════════════════════════════════



@dataclass

class ClassifiedError(Exception):

    """Structured error classification with recovery hints.



    Consumers (llm.py _call(), ResilienceGate) read the 4 flags:

      - retryable: can we retry?

      - should_compress: compress context and retry?

      - should_rotate_credential: try different API key?

      - should_fallback: try different provider?



    All 4 flags are set at classification time. Provider registry,

    credential rotation, and fallback chains are P2+ — but the data

    model supports them from day one.

    """



    reason: FailoverReason

    status_code: Optional[int] = None

    provider: str = ""

    model: str = ""

    message: str = ""



    # ── Recovery flags ──

    retryable: bool = True

    should_compress: bool = False

    should_rotate_credential: bool = False

    should_fallback: bool = False



    # ── Smart retry params ──

    fix_kwargs: Optional[Dict[str, Any]] = field(default=None)

    retry_after_seconds: float = 0.0



    def __post_init__(self):

        super().__init__(self.message)





# ══════════════════════════════════════════════════════════════

# 3. Pattern tables (hermes-aligned, 6 groups)

# ══════════════════════════════════════════════════════════════



_CONTEXT_OVERFLOW_PATTERNS = [

    # Standard API patterns

    "context length", "context size", "maximum context",

    "token limit", "too many tokens", "reduce the length",

    "exceeds the limit", "context window", "prompt is too long",

    "prompt exceeds max length", "maximum number of tokens",

    # vLLM / local inference

    "exceeds the max_model_len", "max_model_len", "prompt length",

    "input is too long", "maximum model length",

    # Ollama

    "context length exceeded", "truncating input",

    # llama.cpp / llama-server

    "slot context", "n_ctx_slot",

    # Chinese error messages

    "超过最大长度", "上下文长度",

]



_RATE_LIMIT_PATTERNS = [

    "rate limit", "rate_limit", "too many requests", "throttled",

    "requests per minute", "tokens per minute", "requests per day",

    "try again in", "please retry after", "resource_exhausted",

    "rate increased too quickly",  # Alibaba/DashScope

]



_BILLING_PATTERNS = [

    "insufficient credits", "insufficient_quota", "credit balance",

    "credits have been exhausted", "top up your credits",

    "payment required", "billing hard limit", "exceeded your current quota",

    "account is deactivated", "plan does not include",

]



_USAGE_LIMIT_PATTERNS = [

    "usage limit", "quota", "limit exceeded", "key limit exceeded",

]



_USAGE_LIMIT_TRANSIENT_SIGNALS = [

    "try again", "retry", "resets at", "reset in", "wait",

    "requests remaining", "periodic", "window",

]



_AUTH_PATTERNS = [

    "invalid api key", "invalid_api_key", "authentication",

    "unauthorized", "forbidden", "invalid token",

    "token expired", "token revoked", "access denied",

]



_MODEL_NOT_FOUND_PATTERNS = [

    "is not a valid model", "invalid model", "model not found",

    "model_not_found", "does not exist", "no such model",

    "unknown model", "unsupported model",

]



_PAYLOAD_TOO_LARGE_PATTERNS = [

    "request entity too large", "payload too large", "error code: 413",

]



_SERVER_DISCONNECT_PATTERNS = [

    "server disconnected", "peer closed connection",

    "connection reset by peer", "connection was closed",

    "network connection lost", "unexpected eof",

    "incomplete chunked read",

]



_TRANSPORT_ERROR_TYPES = frozenset({

    "ReadTimeout", "ConnectTimeout", "PoolTimeout",

    "ConnectError", "RemoteProtocolError",

    "ConnectionError", "ConnectionResetError",

    "ConnectionAbortedError", "BrokenPipeError",

    "TimeoutError", "ReadError", "ServerDisconnectedError",

    "APIConnectionError", "APITimeoutError",

})





# ══════════════════════════════════════════════════════════════

# 4. Provider-specific translators (Level 1 — highest priority)

# ══════════════════════════════════════════════════════════════



class BaseErrorTranslator:

    """Provider 子类覆盖 translate() 实现 Level 1 自定义分类。

    

    返回 ClassifiedError → 短路后续流水线。

    返回 None → 走通用 2-7 级流水线。

    """



    ERROR_CODE_MAP: Dict[str, FailoverReason] = {}



    @classmethod

    def translate(cls, error: Exception, body: dict, status_code: int,

                 error_msg: str, approx_tokens: int, context_length: int,

                 num_messages: int) -> Optional[ClassifiedError]:

        return None





class DeepSeekTranslator(BaseErrorTranslator):

    """DeepSeek API — OpenAI-compatible format with custom error messages."""



    ERROR_CODE_MAP = {

        "context_length_exceeded": FailoverReason.context_overflow,

        "max_tokens_exceeded":       FailoverReason.param_out_of_range,

        "invalid_api_key":            FailoverReason.auth,

        "rate_limit_exceeded":        FailoverReason.rate_limit,

        "resource_exhausted":         FailoverReason.rate_limit,

        "insufficient_quota":         FailoverReason.billing,

        "model_not_found":            FailoverReason.model_not_found,

        "throttled":                  FailoverReason.rate_limit,

    }



    @classmethod

    def translate(cls, error, body, status_code, error_msg,

                  approx_tokens, context_length, num_messages):

        # DeepSeek max_tokens 超限 — extract exact limit for smart retry

        # Format: "max_tokens is too large: 131072, max is 65536" or "max_tokens: 131072 exceeds max: 65536"

        m = re.search(

            r"max\s*(?:is\s+|of\s+|[:=]\s*)(\d{4,7})",

            error_msg, re.IGNORECASE

        )

        if m and status_code in (400, 0, None):

            upper = int(m.group(1))

            return ClassifiedError(

                reason=FailoverReason.param_out_of_range,

                status_code=status_code,

                fix_kwargs={"max_tokens": int(upper * 0.9)},

                retryable=True,

                message=f"max_tokens exceeded, auto-corrected to {int(upper*0.9)}",

            )



        # DeepSeek generic 400 param error

        if status_code == 400 and any(

            k in error_msg for k in ("range", "invalid", "parameter", "invalid value")

        ):

            return ClassifiedError(

                reason=FailoverReason.format_error,

                status_code=400,

                retryable=False,

            )



        return None  # fall through to generic pipeline





# ══════════════════════════════════════════════════════════════

# 5. Provider Registry

# ══════════════════════════════════════════════════════════════



_PROVIDER_REGISTRY: Dict[str, type] = {

    "deepseek": DeepSeekTranslator,

    # P2+: "openai": OpenAITranslator,

    # P2+: "anthropic": AnthropicTranslator,

    # P2+: "qwen": QwenTranslator,

}





def get_translator(provider: str) -> Optional[type]:

    """Get translator class for a provider. Normalizes aliases."""

    key = (provider or "").strip().lower()

    # Normalize OpenAI-compatible → deepseek (same error format)

    if key in ("openai_compatible",):

        key = "deepseek"

    return _PROVIDER_REGISTRY.get(key)





# ══════════════════════════════════════════════════════════════

# 6. Helpers — extract status code / error body / error code

# ══════════════════════════════════════════════════════════════



def _extract_status_code(error: Exception) -> Optional[int]:

    """Walk the exception chain to find an HTTP status code."""

    current = error

    for _ in range(5):

        for attr in ("status_code", "status", "http_status"):

            code = getattr(current, attr, None)

            if isinstance(code, int) and 100 <= code < 600:

                return code

        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)

        if cause is None or cause is current:

            break

        current = cause

    return None





def _extract_error_body(error: Exception) -> dict:

    """Extract structured error body from SDK exception."""

    body = getattr(error, "body", None)

    if isinstance(body, dict):

        return body

    response = getattr(error, "response", None)

    if response is not None:

        try:

            jb = response.json()

            if isinstance(jb, dict):

                return jb

        except Exception:

            logging.getLogger(__name__).debug('_extract_error_body failed', exc_info=True)
    return {}





def _extract_error_code(body: dict) -> str:

    """Extract error code string from response body."""

    if not body:

        return ""

    err = body.get("error", {})

    if isinstance(err, dict):

        code = err.get("code") or err.get("type") or ""

        if isinstance(code, str) and code.strip():

            return code.strip()

    code = body.get("code") or body.get("error_code") or ""

    return str(code).strip() if isinstance(code, (str, int)) else ""





def _build_error_msg(error: Exception, body: dict) -> str:

    """Build comprehensive error message from all sources."""

    raw = str(error).lower()

    parts = [raw]



    if isinstance(body, dict):

        err_obj = body.get("error", {})

        if isinstance(err_obj, dict):

            bm = (err_obj.get("message") or "").lower()

            if bm and bm not in raw:

                parts.append(bm)

            # Parse metadata.raw for wrapped provider errors

            meta = err_obj.get("metadata", {})

            if isinstance(meta, dict):

                raw_json = meta.get("raw") or ""

                if isinstance(raw_json, str) and raw_json.strip():

                    try:

                        inner = json.loads(raw_json)

                        if isinstance(inner, dict):

                            inner_err = inner.get("error", {})

                            if isinstance(inner_err, dict):

                                im = (inner_err.get("message") or "").lower()

                                if im and im not in raw:

                                    parts.append(im)

                    except (json.JSONDecodeError, TypeError):

                        pass  # noqa: cleanup-best-effort

        if not bm:

            bm = (body.get("message") or "").lower()

            if bm and bm not in raw:

                parts.append(bm)



    return " ".join(parts)





def _parse_max_tokens_limit(error_msg: str) -> Optional[int]:

    """Extract the max_tokens upper limit from an error message like 'max is 65536'."""

    m = re.search(r"max\s*(?:is\s+|of\s+|[:=]\s*)(\d{4,7})", error_msg, re.IGNORECASE)

    if m:

        return int(m.group(1))

    return None





def _parse_retry_after(error_msg: str) -> float:

    """Extract the suggested wait time from a rate limit error.



    Handles relative times ("try again in 10s"), absolute times

    ("try again after Tue, 07 Jul 2026 10:00:00 GMT"), and bare numbers.

    Clamps result to [0.5, 60] to prevent CPU spin and UI hangs.

    """

    msg = error_msg.lower()



    # Relative time: "try again in 10s", "retry after 30 seconds", "wait 5 min"

    m = re.search(r"(?:try\s+again|retry|wait).*?(\d+(?:\.\d+)?)\s*(?:s(?:ec(?:ond)?)?|m(?:in(?:ute)?)?)", msg)

    if m:

        val = float(m.group(1))

        if "min" in msg or "minute" in msg:

            val *= 60

        return max(0.5, min(60.0, val))



    # Absolute time: "try again after Tue, 07 Jul 2026 10:00:00 GMT"

    m = re.search(r"after\s+(.{20,40})\s*(?:GMT|UTC)?", msg)

    if m:

        try:

            import email.utils as _eutils

            t = _eutils.parsedate_to_datetime(m.group(1).strip())

            now = __import__("datetime").datetime.now(t.tzinfo if t.tzinfo else None)

            return max(0.5, min(60.0, (t - now).total_seconds()))

        except Exception:

            logging.getLogger(__name__).debug('_parse_retry_after failed', exc_info=True)


    # Bare number: "429", "retry after 10"

    m = re.search(r"(?:after|in)\s+(\d+(?:\.\d+)?)", msg)

    if m:

        return max(0.5, min(60.0, float(m.group(1))))



    return 5.0  # default fallback





# ══════════════════════════════════════════════════════════════

# 7. Classification pipeline (7 levels, priority-ordered)

# ══════════════════════════════════════════════════════════════



def classify_api_error(

    error: Exception,

    *,

    provider: str = "",

    model: str = "",

    approx_tokens: int = 0,

    context_length: int = 200000,

    num_messages: int = 0,

) -> ClassifiedError:

    """Classify an API error with 7-level priority pipeline.



    Returns ClassifiedError with 4 recovery flags.

    Consumer reads flags — never re-classifies.

    """

    status_code = _extract_status_code(error)

    error_type = type(error).__name__

    body = _extract_error_body(error)

    error_code = _extract_error_code(body)

    error_msg = _build_error_msg(error, body)

    provider_lower = (provider or "").strip().lower()



    def _mk(**kw) -> ClassifiedError:

        defaults = {

            "reason": FailoverReason.unknown,

            "status_code": status_code,

            "provider": provider,

            "model": model,

            "message": str(error)[:500],

        }

        defaults.update(kw)

        # Auto-extract retry_after_seconds for rate limit results

        if defaults.get("reason") == FailoverReason.rate_limit and not defaults.get("retry_after_seconds"):

            defaults["retry_after_seconds"] = _parse_retry_after(error_msg)

        return ClassifiedError(**defaults)



    # ── Level 1: Provider-specific (via subclass) ──

    translator_cls = get_translator(provider)

    if translator_cls:

        try:

            result = translator_cls.translate(

                error, body, status_code, error_msg,

                approx_tokens, context_length, num_messages,

            )

            if result is not None:

                result.provider = provider

                result.model = model

                result.status_code = result.status_code or status_code

                return result

        except Exception:

            logging.getLogger(__name__).debug('_mk failed', exc_info=True)


    # ── Level 1b: Provider error_code map ──

    if error_code and translator_cls:

        code_map = getattr(translator_cls, "ERROR_CODE_MAP", {})

        if error_code in code_map:

            reason = code_map[error_code]

            retryable = reason not in (FailoverReason.auth, FailoverReason.auth_permanent,

                                         FailoverReason.billing, FailoverReason.format_error,

                                         FailoverReason.model_not_found)

            compress = reason in (FailoverReason.context_overflow, FailoverReason.payload_too_large)

            rotate = reason in (FailoverReason.auth, FailoverReason.rate_limit, FailoverReason.billing)

            fallback = reason not in (FailoverReason.param_out_of_range, FailoverReason.format_error,

                                        FailoverReason.timeout)

            return _mk(reason=reason, retryable=retryable, should_compress=compress,

                       should_rotate_credential=rotate, should_fallback=fallback)



    # ── Level 2: HTTP status code ──

    if status_code is not None:

        classified = _classify_by_status(status_code, error_msg, error_code,

                                         approx_tokens, context_length, num_messages, _mk)

        if classified is not None:

            return classified



    # ── Level 3: Error code from body ──

    if error_code:

        classified = _classify_by_error_code(error_code, _mk)

        if classified is not None:

            return classified



    # ── Level 4: Message pattern matching ──

    classified = _classify_by_message(error_msg, error_type,

                                      approx_tokens, context_length, num_messages, _mk)

    if classified is not None:

        return classified



    # ── Level 5: Server disconnect + large session → context overflow ──

    is_disconnect = any(p in error_msg for p in _SERVER_DISCONNECT_PATTERNS)

    if is_disconnect and not status_code:

        is_large = approx_tokens > context_length * 0.6 or approx_tokens > 120000 or num_messages > 200

        if is_large:

            return _mk(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)

        return _mk(reason=FailoverReason.timeout, retryable=True)



    # ── Level 6: Transport / timeout ──

    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(error, (TimeoutError, ConnectionError, OSError)):

        return _mk(reason=FailoverReason.timeout, retryable=True)



    # ── Level 7: Unknown (retryable fallback) ──

    return _mk(reason=FailoverReason.unknown, retryable=True)





# ══════════════════════════════════════════════════════════════

# 8. Status code classification (Level 2)

# ══════════════════════════════════════════════════════════════



def _classify_by_status(

    status_code: int, error_msg: str, error_code: str,

    approx_tokens: int, context_length: int, num_messages: int, _mk,

) -> Optional[ClassifiedError]:



    if status_code == 401:

        return _mk(reason=FailoverReason.auth, retryable=False,

                   should_rotate_credential=True, should_fallback=True)



    if status_code == 403:

        if "key limit exceeded" in error_msg or "spending limit" in error_msg:

            return _mk(reason=FailoverReason.billing, retryable=False,

                       should_rotate_credential=True, should_fallback=True)

        return _mk(reason=FailoverReason.auth, retryable=False, should_fallback=True)



    if status_code == 402:

        has_limit = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS)

        has_transient = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)

        if has_limit and has_transient:

            return _mk(reason=FailoverReason.rate_limit, retryable=True,

                       should_rotate_credential=True, should_fallback=True)

        return _mk(reason=FailoverReason.billing, retryable=False,

                   should_rotate_credential=True, should_fallback=True)



    if status_code == 404:

        return _mk(reason=FailoverReason.model_not_found, retryable=False, should_fallback=True)



    if status_code == 413:

        return _mk(reason=FailoverReason.payload_too_large, retryable=True, should_compress=True)



    if status_code == 429:

        return _mk(reason=FailoverReason.rate_limit, retryable=True,

                   should_rotate_credential=True, should_fallback=True)



    if status_code == 400:

        return _classify_400(error_msg, approx_tokens, context_length, num_messages, _mk)



    if status_code in (500, 502):

        return _mk(reason=FailoverReason.server_error, retryable=True)



    if status_code in (503, 529):

        return _mk(reason=FailoverReason.overloaded, retryable=True)



    if 400 <= status_code < 500:

        return _mk(reason=FailoverReason.format_error, retryable=False, should_fallback=True)



    if 500 <= status_code < 600:

        return _mk(reason=FailoverReason.server_error, retryable=True)



    return None





def _classify_400(error_msg, approx_tokens, context_length, num_messages, _mk) -> ClassifiedError:

    """Classify 400: context overflow → param error → model → rate/billing → generic."""

    # Context overflow

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):

        return _mk(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)



    # Param out of range (max_tokens, temperature)

    if "max_tokens" in error_msg:

        fix = _parse_max_tokens_limit(error_msg)

        return _mk(reason=FailoverReason.param_out_of_range, retryable=True,

                   fix_kwargs={"max_tokens": int(fix * 0.9)} if fix else None)



    # Model not found returned as 400

    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):

        return _mk(reason=FailoverReason.model_not_found, retryable=False, should_fallback=True)



    # Rate limit / billing returned as 400

    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):

        return _mk(reason=FailoverReason.rate_limit, retryable=True,

                   should_rotate_credential=True, should_fallback=True)

    if any(p in error_msg for p in _BILLING_PATTERNS):

        return _mk(reason=FailoverReason.billing, retryable=False,

                   should_rotate_credential=True, should_fallback=True)



    # Generic 400 + large session → probable overflow

    is_large = approx_tokens > context_length * 0.4 or num_messages > 80

    if is_large:

        return _mk(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)



    return _mk(reason=FailoverReason.format_error, retryable=False, should_fallback=True)





# ══════════════════════════════════════════════════════════════

# 9. Error code classification (Level 3)

# ══════════════════════════════════════════════════════════════



def _classify_by_error_code(error_code: str, _mk) -> Optional[ClassifiedError]:

    code = error_code.lower()

    if code in ("resource_exhausted", "throttled", "rate_limit_exceeded"):

        return _mk(reason=FailoverReason.rate_limit, retryable=True,

                   should_rotate_credential=True, should_fallback=True)

    if code in ("insufficient_quota", "billing_not_active", "payment_required"):

        return _mk(reason=FailoverReason.billing, retryable=False,

                   should_rotate_credential=True, should_fallback=True)

    if code in ("model_not_found", "model_not_available", "invalid_model"):

        return _mk(reason=FailoverReason.model_not_found, retryable=False, should_fallback=True)

    if code in ("context_length_exceeded", "max_tokens_exceeded"):

        return _mk(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)

    return None





# ══════════════════════════════════════════════════════════════

# 10. Message pattern classification (Level 4)

# ══════════════════════════════════════════════════════════════



def _classify_by_message(

    error_msg, error_type,

    approx_tokens, context_length, num_messages, _mk,

) -> Optional[ClassifiedError]:

    # Billing patterns

    if any(p in error_msg for p in _BILLING_PATTERNS):

        return _mk(reason=FailoverReason.billing, retryable=False,

                   should_rotate_credential=True, should_fallback=True)



    # Rate limit patterns

    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):

        return _mk(reason=FailoverReason.rate_limit, retryable=True,

                   should_rotate_credential=True, should_fallback=True)



    # Context overflow

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):

        return _mk(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)



    # Auth patterns

    if any(p in error_msg for p in _AUTH_PATTERNS):

        return _mk(reason=FailoverReason.auth, retryable=False,

                   should_rotate_credential=True, should_fallback=True)



    # Model not found

    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):

        return _mk(reason=FailoverReason.model_not_found, retryable=False, should_fallback=True)



    # Payload too large

    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):

        return _mk(reason=FailoverReason.payload_too_large, retryable=True, should_compress=True)



    return None





# ══════════════════════════════════════════════════════════════

# TrendDetector recorder hook (P3-1: entropy trend awareness)

# ══════════════════════════════════════════════════════════════



_TREND_RECORDER = None  # type: ignore





def set_trend_recorder(fn):

    """Inject recorder for TrendDetector (called at TrendDetector.start())."""

    global _TREND_RECORDER

    _TREND_RECORDER = fn





async def _record_classification(key: str) -> None:

    """Record a classification event for TrendDetector. Non-blocking, no-op if unset."""

    fn = _TREND_RECORDER

    if fn is not None:

        try:

            await fn(key)

        except Exception:

            logging.getLogger(__name__).debug('_record_classification failed', exc_info=True)




# ══════════════════════════════════════════════════════════════

# Recovery hints — machine-classification → actionable Agent guidance

# ══════════════════════════════════════════════════════════════



_RECOVERY_HINTS: Dict[FailoverReason, str] = {

    FailoverReason.auth: "认证失败(401/403)：检查凭证/权限，或改用有权限的工具后重试。",

    FailoverReason.auth_permanent: "认证永久失败：凭证无效，需人工更换密钥，勿盲目重试。",

    FailoverReason.billing: "额度耗尽(402)：切换账号/密钥或联系管理员充值。",

    FailoverReason.rate_limit: "触发限流(429)：稍后退避重试，或切换到备用密钥/模型。",

    FailoverReason.overloaded: "服务过载(503/529)：指数退避后重试，或切换到备用提供商。",

    FailoverReason.server_error: "服务端错误(500/502)：退避重试；持续失败则切换提供商。",

    FailoverReason.timeout: "超时：缩小请求规模或增大超时时间后重试。",

    FailoverReason.context_overflow: "上下文超限：压缩上下文/裁剪输入后重试。",

    FailoverReason.payload_too_large: "负载过大(413)：拆分输入或压缩后重试。",

    FailoverReason.model_not_found: "模型不存在(404)：更换有效模型名，勿重试原模型。",

    FailoverReason.format_error: "请求格式错误(400)：修正参数结构后重试。",

    FailoverReason.param_out_of_range: "参数越界：调整 max_tokens/temperature 等到合法范围。",

    FailoverReason.thinking_signature: "thinking 签名错误：移除/修正 thinking 块后重试。",

    FailoverReason.long_context_tier: "长上下文等级限制：缩短上下文或申请更高等级。",

    FailoverReason.unknown: "未知错误：检查 stderr/exit_code 定位根因，修正参数或换用替代工具后重试。",

}





def recovery_hint_for(reason: FailoverReason) -> str:

    """Map a classified FailoverReason to an actionable, LLM-readable recovery hint.



    Consumed by sys_tool_call to populate ToolResult.recovery_hint, giving the

    Agent structured guidance instead of an opaque error string.

    """

    return _RECOVERY_HINTS.get(reason, _RECOVERY_HINTS[FailoverReason.unknown])




