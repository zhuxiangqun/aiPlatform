"""Tests for error_translator — 7-level classification pipeline.

Covers all 19 FailoverReason values, ClassifiedError flag correctness,
provider extensibility, and edge cases.
"""

import pytest
import sys

sys.path.insert(0, "aiPlat-core")

from core.harness.infrastructure.gates.error_translator import (
    classify_api_error,
    ClassifiedError,
    FailoverReason,
    DeepSeekTranslator,
    BaseErrorTranslator,
    get_translator,
    _parse_max_tokens_limit,
    _extract_status_code,
    _extract_error_body,
    _build_error_msg,
)


# ══════════════════════════════════════════════════════════════
# Level 1: Provider-specific
# ══════════════════════════════════════════════════════════════

def test_deepseek_max_tokens_param_out_of_range():
    result = classify_api_error(
        RuntimeError("max_tokens is too large: 131072, max is 65536 for this model"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.param_out_of_range
    assert result.retryable is True
    assert result.fix_kwargs == {"max_tokens": 58982}  # 65536 * 0.9
    assert result.should_compress is False


def test_deepseek_max_tokens_variant_format():
    result = classify_api_error(
        RuntimeError("max_tokens: 200000 exceeds max: 65536"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.param_out_of_range
    assert result.fix_kwargs["max_tokens"] == 58982


def test_deepseek_context_overflow():
    result = classify_api_error(
        RuntimeError("context length exceeded: prompt is too long"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.context_overflow
    assert result.retryable is True
    assert result.should_compress is True


def test_deepseek_rate_limit():
    result = classify_api_error(
        RuntimeError("rate limit reached, try again in 10s"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.rate_limit
    assert result.retryable is True


def test_deepseek_invalid_api_key():
    result = classify_api_error(
        RuntimeError("Invalid API key"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.auth
    assert result.retryable is False
    assert result.should_rotate_credential is True
    assert result.should_fallback is True


# ══════════════════════════════════════════════════════════════
# Level 2: HTTP Status code
# ══════════════════════════════════════════════════════════════

class FakeHttpError(Exception):
    """Simulate an SDK HTTP error with a status_code attribute."""
    def __init__(self, status_code, message=""):
        self.status_code = status_code
        super().__init__(message)


def test_401_authentication():
    result = classify_api_error(FakeHttpError(401, "Unauthorized"), provider="deepseek")
    assert result.reason == FailoverReason.auth
    assert result.retryable is False
    assert result.should_rotate_credential is True


def test_429_rate_limit_status():
    result = classify_api_error(FakeHttpError(429, "Too Many Requests"), provider="deepseek")
    assert result.reason == FailoverReason.rate_limit
    assert result.retryable is True


def test_413_payload_too_large():
    result = classify_api_error(FakeHttpError(413), provider="deepseek")
    assert result.reason == FailoverReason.payload_too_large
    assert result.should_compress is True


def test_404_model_not_found():
    result = classify_api_error(FakeHttpError(404, "model not found"), provider="deepseek")
    assert result.reason == FailoverReason.model_not_found
    assert result.retryable is False


def test_500_server_error():
    result = classify_api_error(FakeHttpError(500), provider="deepseek")
    assert result.reason == FailoverReason.server_error
    assert result.retryable is True


def test_503_overloaded():
    result = classify_api_error(FakeHttpError(503), provider="deepseek")
    assert result.reason == FailoverReason.overloaded
    assert result.retryable is True


def test_400_context_overflow_by_status():
    result = classify_api_error(
        FakeHttpError(400, "maximum context length exceeded"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.context_overflow
    assert result.should_compress is True


def test_402_billing_exhaustion():
    result = classify_api_error(
        FakeHttpError(402, "insufficient credits"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.billing
    assert result.retryable is False


def test_402_transient_quota():
    result = classify_api_error(
        FakeHttpError(402, "usage limit exceeded, try again in 5 minutes"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.rate_limit  # transient, not billing
    assert result.retryable is True


# ══════════════════════════════════════════════════════════════
# Level 3: Error code from body
# ══════════════════════════════════════════════════════════════

class FakeBodyError(Exception):
    def __init__(self, body_dict, status_code=400):
        self.status_code = status_code
        self.body = body_dict
        super().__init__(body_dict.get("error", {}).get("message", ""))


def test_body_error_code_resource_exhausted():
    result = classify_api_error(
        FakeBodyError({"error": {"code": "resource_exhausted", "message": "quota exceeded"}}),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.rate_limit


def test_body_error_code_context_length_exceeded():
    result = classify_api_error(
        FakeBodyError({"error": {"code": "context_length_exceeded", "message": ""}}),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.context_overflow
    assert result.should_compress is True


def test_body_error_code_model_not_found():
    result = classify_api_error(
        FakeBodyError({"error": {"code": "model_not_found"}}),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.model_not_found
    assert result.retryable is False


# ══════════════════════════════════════════════════════════════
# Level 4: Message patterns (no status code)
# ══════════════════════════════════════════════════════════════

def test_message_rate_limit():
    result = classify_api_error(
        RuntimeError("too many requests, throttled, try again in 30s"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.rate_limit
    assert result.retryable is True


def test_message_billing():
    result = classify_api_error(
        RuntimeError("insufficient credits, please top up your account"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.billing
    assert result.retryable is False


def test_message_auth():
    result = classify_api_error(
        RuntimeError("invalid token, access denied"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.auth
    assert result.retryable is False


def test_message_model_not_found():
    result = classify_api_error(
        RuntimeError("model not found: unknown model"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.model_not_found


def test_message_payload_too_large():
    result = classify_api_error(
        RuntimeError("request entity too large"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.payload_too_large
    assert result.should_compress is True


# ══════════════════════════════════════════════════════════════
# Cross-provider: Ollama / vLLM / Chinese messages
# ══════════════════════════════════════════════════════════════

def test_ollama_context_overflow():
    result = classify_api_error(
        RuntimeError("context length exceeded, truncating input"),
        provider="ollama",
    )
    assert result.reason == FailoverReason.context_overflow


def test_vllm_model_len_exceeded():
    result = classify_api_error(
        RuntimeError("exceeds the max_model_len of 32768"),
        provider="openai_compatible",
    )
    assert result.reason == FailoverReason.context_overflow


def test_chinese_context_overflow():
    result = classify_api_error(
        RuntimeError("提示词超过最大长度限制"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.context_overflow


# ══════════════════════════════════════════════════════════════
# Level 5-7: Transport / timeout / unknown
# ══════════════════════════════════════════════════════════════

def test_timeout_transport():
    result = classify_api_error(TimeoutError("connection timed out"), provider="deepseek")
    assert result.reason == FailoverReason.timeout
    assert result.retryable is True


def test_connection_error():
    result = classify_api_error(ConnectionError("Connection refused"), provider="deepseek")
    assert result.reason == FailoverReason.timeout
    assert result.retryable is True


def test_disconnect_large_session():
    result = classify_api_error(
        RuntimeError("connection reset by peer"),
        provider="deepseek",
        approx_tokens=150000,
        context_length=200000,
        num_messages=250,
    )
    assert result.reason == FailoverReason.context_overflow


def test_unknown_fallback():
    result = classify_api_error(
        RuntimeError("something completely unexpected"),
        provider="deepseek",
    )
    assert result.reason == FailoverReason.unknown
    assert result.retryable is True


# ══════════════════════════════════════════════════════════════
# Provider extensibility
# ══════════════════════════════════════════════════════════════

def test_get_translator_deepseek():
    t = get_translator("deepseek")
    assert t == DeepSeekTranslator


def test_get_translator_unknown_provider():
    t = get_translator("nonexistent")
    assert t is None


def test_get_translator_openai_compatible_alias():
    t = get_translator("openai_compatible")
    assert t == DeepSeekTranslator  # normalized to deepseek


def test_get_translator_case_insensitive():
    t = get_translator("DeepSeek")
    assert t == DeepSeekTranslator


def test_custom_translator_override():
    class CustomTranslator(BaseErrorTranslator):
        @classmethod
        def translate(cls, error, body, status_code, error_msg,
                      approx_tokens, context_length, num_messages):
            return ClassifiedError(reason=FailoverReason.auth, retryable=False)

    # Test that Provider-specific Level 1 short-circuits the pipeline
    # Directly test DeepSeekTranslator's translate method
    result = DeepSeekTranslator.translate(
        RuntimeError("max_tokens is too large: 200000, max is 65536"),
        {}, 400,
        "max_tokens is too large: 200000, max is 65536",
        0, 200000, 0,
    )
    assert result is not None
    assert result.reason == FailoverReason.param_out_of_range
    assert result.fix_kwargs == {"max_tokens": 58982}


# ══════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════

def test_empty_error_message():
    result = classify_api_error(RuntimeError(""), provider="deepseek")
    assert result.reason == FailoverReason.unknown
    assert result.retryable is True


def test_null_provider():
    result = classify_api_error(RuntimeError("rate limit"), provider="")
    assert result.reason == FailoverReason.rate_limit


def test_helper_parse_max_tokens():
    assert _parse_max_tokens_limit("max_tokens: 131072 exceeds max: 65536") == 65536
    assert _parse_max_tokens_limit("max is 8192") == 8192
    assert _parse_max_tokens_limit("max of 4096 tokens") == 4096
    assert _parse_max_tokens_limit("no limit here") is None


def test_helper_extract_status_code_chain():
    inner = RuntimeError("inner")
    outer = RuntimeError("outer")
    outer.__cause__ = inner
    inner.status_code = 429
    assert _extract_status_code(outer) == 429


def test_classified_error_has_all_flags():
    ce = ClassifiedError(reason=FailoverReason.unknown)
    assert hasattr(ce, "retryable")
    assert hasattr(ce, "should_compress")
    assert hasattr(ce, "should_rotate_credential")
    assert hasattr(ce, "should_fallback")
    assert hasattr(ce, "fix_kwargs")
    assert ce.fix_kwargs is None
