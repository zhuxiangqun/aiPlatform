"""Repetition guard — detect and truncate degenerate LLM output loops.

Some small local models (e.g. qwen2.5:3b) degenerate into a repeated-phrase
loop when given complex injected context and a request they cannot fulfil.
Instead of answering, the model emits the same sentence dozens/hundreds of
times (observed 2026-08-29: 7943 chars, one phrase repeated 230× in the PM
dialogue).

This module provides a cheap, deterministic post-processing guard: detect a
long n-gram that repeats more than a conservative threshold, then truncate the
response before the loop begins so the frontend receives a usable (partial)
answer instead of an infinite repetition.

Design notes:
  - Operates on raw text; Chinese LLM output has no inter-token spaces, so
    n-gram boundaries are stable.
  - Truncates at the SECOND occurrence of the repeated n-gram — the first
    occurrence is part of the legitimate answer.
  - Trivial grams (very low unique-char count, e.g. "。。。。") are skipped.
"""
from __future__ import annotations

from typing import Optional, Tuple

_log = None


def _logger():
    global _log
    if _log is None:
        import logging

        _log = logging.getLogger("aiplat.repetition_guard")
    return _log


def _detect_repetition(
    text: str,
    *,
    min_phrase_len: int = 10,
    min_repeats: int = 8,
    min_text_len: int = 150,
) -> Optional[int]:
    """Return the char offset where a degenerate loop begins, or None.

    A loop is detected when a single n-gram (``min_phrase_len`` chars) appears
    ``min_repeats`` or more times. The returned offset is the start of the
    *second* occurrence of that n-gram (i.e. where the answer stops being new
    information and starts repeating).
    """
    if not text or not isinstance(text, str):
        return None
    n = len(text)
    if n < min_text_len or n < min_phrase_len:
        return None

    counts: dict = {}
    for i in range(n - min_phrase_len + 1):
        gram = text[i:i + min_phrase_len]
        counts[gram] = counts.get(gram, 0) + 1

    best_gram: Optional[str] = None
    for i in range(n - min_phrase_len + 1):
        gram = text[i:i + min_phrase_len]
        if counts[gram] < min_repeats:
            continue
        # Skip trivially repetitive grams (e.g. punctuation runs).
        if len(set(gram)) <= 2:
            continue
        best_gram = gram
        break

    if best_gram is None:
        return None

    first = text.find(best_gram)
    if first < 0:
        return None
    second = text.find(best_gram, first + 1)
    if second <= 0:
        return None
    return second


def truncate_repetition(
    text: str,
    *,
    min_phrase_len: int = 10,
    min_repeats: int = 8,
    min_text_len: int = 150,
) -> Tuple[str, bool]:
    """Truncate a degenerate repetition loop, keeping the non-repeating prefix.

    Returns ``(text, truncated)``. If no loop is detected, ``text`` is returned
    unchanged and ``truncated`` is ``False``.
    """
    offset = _detect_repetition(
        text,
        min_phrase_len=min_phrase_len,
        min_repeats=min_repeats,
        min_text_len=min_text_len,
    )
    if offset is None:
        return text, False

    truncated = text[:offset].rstrip()
    _logger().warning(
        "repetition loop truncated: %d → %d chars", len(text), len(truncated)
    )
    return truncated, True
