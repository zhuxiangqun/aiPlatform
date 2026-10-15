"""build_llm_response_format — skill/pipeline → provider response_format."""

from __future__ import annotations

import os

import pytest

from core.utils.json_utils import build_llm_response_format


def test_json_schema_from_properties():
    fmt = build_llm_response_format(
        {"type": "object", "properties": {"title": {"type": "string"}}},
        name="arch",
    )
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "arch"
    assert fmt["json_schema"]["schema"]["properties"]["title"]["type"] == "string"


def test_legacy_key_dict_wrapped():
    fmt = build_llm_response_format({"foo": None, "bar": "hint", "x-display-profile": "ui"})
    assert fmt["type"] == "json_schema"
    props = fmt["json_schema"]["schema"]["properties"]
    assert "foo" in props and "bar" in props
    assert "x-display-profile" not in props


def test_empty_and_kill_switch(monkeypatch):
    assert build_llm_response_format(None) is None
    assert build_llm_response_format({}) is None
    monkeypatch.setenv("AIPLAT_LLM_RESPONSE_FORMAT", "0")
    assert build_llm_response_format({"type": "object", "properties": {"a": {}}}) is None
    monkeypatch.delenv("AIPLAT_LLM_RESPONSE_FORMAT", raising=False)


def test_force_json_object():
    fmt = build_llm_response_format({"type": "object"}, force_json_object=True)
    assert fmt == {"type": "json_object"}
