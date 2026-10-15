"""parse_json — extract_json_safe + deterministic LLM JSON fixes."""

from __future__ import annotations

from core.utils.json_utils import parse_json


def test_fence_and_trailing_prose():
    raw = 'Here is the result:\n```json\n{"a": 1}\n```\nThanks!'
    assert parse_json(raw) == {"a": 1}


def test_trailing_comma_and_python_bools():
    raw = '{"ok": True, "n": None,}'
    assert parse_json(raw) == {"ok": True, "n": None}


def test_single_quoted_string_value():
    assert parse_json('{"msg": \'hi\'}') == {"msg": "hi"}


def test_unparseable_returns_none():
    assert parse_json("not json at all") is None
