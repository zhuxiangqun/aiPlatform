"""
RedactingFormatter — global logging.Formatter that auto-scrubs API keys,
tokens, and sensitive values from log messages.

Aligned with hermes-agent redact.py (181 lines).
Applied once at logging config level — no per-call manual redaction needed.

Architecture: core/harness/utils/ — harness cross-cutting concern.
"""

from __future__ import annotations
import logging
import os
import re

# ── Snapshot-on-import — prevents runtime disable ──
_REDACT_ENABLED = os.getenv("AIPLAT_REDACT_SECRETS", "1") not in ("0", "false", "no")

# ── Pattern categories ──

# API key prefixes (DeepSeek, OpenAI, Anthropic, Plus common OSS keys)
_KEY_PREFIXES = r"(sk-[A-Za-z0-9]+|sk-ant-[A-Za-z0-9]+|DEEPSEEK_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY)"

# env var assignments: export DEEPSEEK_API_KEY=sk-xxx
_ENV_ASSIGN_RE = re.compile(
    r'(?:export\s+)?(?:[A-Z_]+API[_-]?KEY[A-Z_]*)\s*=\s*["\']?([^"\'\s]{8,})["\']?',
    re.IGNORECASE
)

# JSON field values: "api_key": "sk-xxx"
_JSON_FIELD_RE = re.compile(
    r'"(?:api[_-]?key|secret|token|password)"\s*:\s*"([^"]{8,})"',
    re.IGNORECASE
)

# Bearer tokens in HTTP headers
_AUTH_HEADER_RE = re.compile(
    r'(?:Authorization|X-API-?Key)\s*:\s*(?:Bearer\s+)?([^\s]{20,})',
    re.IGNORECASE
)


def _mask_secret(value: str) -> str:
    """Short value → '***', long value → 'sk-fir...last'."""
    if not value:
        return "***"
    if len(value) <= 6:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def redact_text(text: str) -> str:
    """Redact secrets from a text string. No-op if AIPLAT_REDACT_SECRETS=0."""
    if not _REDACT_ENABLED or not text:
        return text

    result = text
    for pattern in (_ENV_ASSIGN_RE, _JSON_FIELD_RE, _AUTH_HEADER_RE):
        result = pattern.sub(lambda m: m.group(0).replace(m.group(1), _mask_secret(m.group(1))), result)

    return result


class RedactingFormatter(logging.Formatter):
    """logging.Formatter subclass that auto-applies redact_text().

    Usage (in logging config):
        handler.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s"))
    """

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_text(original)


def get_redaction_status() -> dict:
    """Return redaction status for diagnostic display."""
    return {"enabled": _REDACT_ENABLED, "note": "snapshot-on-import — restart to change"}
