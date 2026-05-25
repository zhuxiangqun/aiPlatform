"""
PostprocessCorrector — rule-based minor output fixups that avoid costly LLM re-prompt.

Design principle (harness/CLAUDE.md §5.17, control theory Rule #3):
  When output is 95%+ correct, fix the 5% via deterministic post-processing
  instead of re-prompting the LLM (which wastes tokens and risks regressing).

Usage:
  corrector = PostprocessCorrector()
  fixed = corrector.apply(output_text, corrections=["json_fix", "strip_markers"])
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

_log = logging.getLogger("pipeline_engine.postprocess")


class PostprocessCorrector:
    _FIX_JSON_GARBAGE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
    _FIX_MARKDOWN_JSON = re.compile(r'```(?:json)?\s*([\s\S]*?)\s*```', re.IGNORECASE)
    _FIX_TRAILING_COMMA = re.compile(r',\s*([]}])')
    _FIX_SINGLE_QUOTES = re.compile(r"'([^']*)'(\s*):")

    @classmethod
    def apply(cls, text: str, corrections: Optional[List[str]] = None) -> str:
        if not text:
            return text
        corrections = corrections or []
        result = text
        for name in corrections:
            fn = getattr(cls, f"_fix_{name}", None)
            if fn:
                try:
                    result = fn(result)
                except Exception:
                    _log.debug("corrector %s failed, keeping original", name)
        return result

    @classmethod
    def auto_fix_json(cls, text: str) -> str:
        extracted = cls._extract_json_from_markdown(text)
        if extracted:
            return extracted
        cleaned = cls._quick_json_fixes(text)
        if cls._is_valid_json(cleaned):
            return cleaned
        return text

    # ── internal fixers ──

    @staticmethod
    def _fix_strip_markers(text: str) -> str:
        return text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')

    @staticmethod
    def _fix_trailing_commas(text: str) -> str:
        return PostprocessCorrector._FIX_TRAILING_COMMA.sub(r'\1', text)

    @staticmethod
    def _fix_single_quotes(text: str) -> str:
        return PostprocessCorrector._FIX_SINGLE_QUOTES.sub(r'"\1":', text)

    @staticmethod
    def _fix_json_control_chars(text: str) -> str:
        return PostprocessCorrector._FIX_JSON_GARBAGE.sub('', text)

    @staticmethod
    def _fix_triple_backtick_in_json(text: str) -> str:
        if '```' in text:
            return text.replace('```', '\\`\\`\\`')
        return text

    # ── helpers ──

    @classmethod
    def _quick_json_fixes(cls, text: str) -> str:
        t = cls._fix_trailing_commas(text)
        t = cls._fix_single_quotes(t)
        t = cls._fix_json_control_chars(t)
        t = cls._fix_triple_backtick_in_json(t)
        return t

    @classmethod
    def _extract_json_from_markdown(cls, text: str) -> str:
        m = cls._FIX_MARKDOWN_JSON.search(text)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _is_valid_json(text: str) -> bool:
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
