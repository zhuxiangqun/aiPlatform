"""
Shared constants for content limits, timeouts, and common defaults.

All magic numbers for truncation, preview lengths, and common thresholds
should be defined here rather than hardcoded inline.

Usage:
  from core.utils.constants import CONTENT_PREVIEW, TOOL_OUTPUT_PREVIEW
  text = result[:CONTENT_PREVIEW]
"""

from __future__ import annotations

# ── Content truncation ──

CONTENT_PREVIEW = 2000       # Default chunk/retrieval preview length
LONG_CONTENT_PREVIEW = 4000  # Extended preview (long-form answers, wiki pages)
SHORT_PREVIEW = 500          # Short preview (tool output, error messages)
TRUNCATION_LIMIT = 8000      # Safety cap for LLM context insertion
TITLE_PREVIEW = 300          # Very short preview (titles, summaries)
MICRO_PREVIEW = 120          # Minimal preview (log lines, breadcrumbs)


# ── Token / LLM defaults ──

DEFAULT_MAX_TOKENS = 2000    # Default max_tokens for LLM calls
SHORT_MAX_TOKENS = 500       # Short answer / classification
LONG_MAX_TOKENS = 4000       # Long-form generation
EXTRACTION_MAX_TOKENS = 300  # JSON extraction / field parsing


# ── Timeout defaults (seconds) ──

DEFAULT_TIMEOUT = 30         # Default HTTP/API timeout
LONG_TIMEOUT = 300           # OCR / heavy processing timeout
FAST_TIMEOUT = 5             # Health check / ping timeout


# ── Common IDs ──

DEFAULT_TENANT = "default"
DEFAULT_COLLECTION = "default"
DEFAULT_SESSION = "default"


# ── Domain / GraphIndex identifiers ──

DOMAIN_FDE = "fde-delivery"
DOMAIN_AI_KNOWLEDGE = "ai-knowledge"


__all__ = [
    "CONTENT_PREVIEW", "LONG_CONTENT_PREVIEW", "SHORT_PREVIEW",
    "TRUNCATION_LIMIT", "TITLE_PREVIEW", "MICRO_PREVIEW",
    "DEFAULT_MAX_TOKENS", "SHORT_MAX_TOKENS", "LONG_MAX_TOKENS",
    "EXTRACTION_MAX_TOKENS",
    "DEFAULT_TIMEOUT", "LONG_TIMEOUT", "FAST_TIMEOUT",
    "DEFAULT_TENANT", "DEFAULT_COLLECTION", "DEFAULT_SESSION",
    "DOMAIN_FDE", "DOMAIN_AI_KNOWLEDGE",
]
