"""test_repetition_guard.py — degenerate LLM repetition loop truncation.

Covers the 2026-08-29 PM dialogue bug: qwen2.5:3b repeated one phrase 230×
(7943 chars) instead of answering. The repetition guard must truncate the
loop while keeping the legitimate non-repeating prefix.
"""
from __future__ import annotations

from core.harness.utils.repetition_guard import (
    _detect_repetition,
    truncate_repetition,
)

_LOOP_PHRASE = "我将尝试使用现有的技能和工具来解决用户的问题。"


def _degenerate_reply(repeats: int = 200) -> str:
    prefix = (
        "根据历史信息和当前提供的技能列表，用户需要分析视频内容。"
        "然而，当前可用的技能和工具列表中没有与视频分析相关的技能。"
    )
    return prefix + _LOOP_PHRASE * repeats


def test_truncates_degenerate_loop():
    """A phrase repeated hundreds of times is truncated to the non-repeating prefix."""
    text = _degenerate_reply()
    out, truncated = truncate_repetition(text)

    assert truncated is True
    assert len(out) < len(text) // 10  # 200× loop collapsed
    # The legitimate prefix is preserved.
    assert "根据历史信息和当前提供的技能列表" in out
    # The loop phrase must not appear many times after truncation.
    assert out.count(_LOOP_PHRASE) <= 1


def test_detect_returns_second_occurrence_offset():
    text = _degenerate_reply()
    offset = _detect_repetition(text)
    assert offset is not None
    # Everything before the offset is the non-repeating prefix (≤1 loop phrase).
    assert text[:offset].count(_LOOP_PHRASE) <= 1
    # Everything after the offset is dominated by the repeated phrase.
    assert text[offset:].count(_LOOP_PHRASE) >= 100


def test_short_text_untouched():
    text = "这是一句正常的简短回复。"
    out, truncated = truncate_repetition(text)
    assert truncated is False
    assert out == text


def test_normal_long_text_untouched():
    """A long but non-repeating answer must not be truncated."""
    text = "功能A用于上传视频。功能B用于分析视频。功能C用于展示结果。功能D用于历史记录。" * 5
    out, truncated = truncate_repetition(text)
    assert truncated is False
    assert out == text


def test_punctuation_only_grams_skipped():
    """Trivial grams (e.g. long punctuation runs) must not trigger truncation."""
    text = "。\n" * 400
    out, truncated = truncate_repetition(text)
    assert truncated is False
