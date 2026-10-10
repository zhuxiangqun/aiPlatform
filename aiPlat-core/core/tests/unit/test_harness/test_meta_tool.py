"""Code meta-tool preference — deterministic escape hatch."""

from __future__ import annotations

import pytest

from core.harness.execution.meta_tool import (
    META_TOOL_ALIASES,
    build_meta_tool_hint,
    detect_meta_tool_intent,
    ensure_code_meta_tool,
    meta_tool_enabled,
    meta_tool_pin_names,
    resolve_meta_tool_name,
)


def test_detect_arithmetic_and_datetime():
    assert detect_meta_tool_intent("Please calculate the average of these numbers") == "arithmetic"
    assert detect_meta_tool_intent("转换时区到 UTC") == "datetime"
    assert detect_meta_tool_intent("parse json and extract ids") == "parse_transform"
    assert detect_meta_tool_intent("hello how are you") is None


def test_resolve_prefers_code():
    assert resolve_meta_tool_name(["grep", "code", "browser"]) == "code"
    assert resolve_meta_tool_name(["code_execution"]) == "code_execution"
    assert resolve_meta_tool_name(["grep"]) is None
    assert set(META_TOOL_ALIASES) >= {"code", "code_execution"}


def test_hint_when_bound(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "true")
    hint = build_meta_tool_hint(
        "calculate sum of 1..100",
        ["code", "file_read"],
    )
    assert hint and "`code`" in hint and "META TOOL" in hint


def test_hint_when_unbound(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "true")
    monkeypatch.setenv("AIPLAT_META_TOOL_AUTO_BIND", "false")
    hint = build_meta_tool_hint("计算平均值", ["file_read"])
    assert hint and "bind/use tool `code`" in hint


def test_disabled(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "false")
    assert meta_tool_enabled({}) is False
    assert build_meta_tool_hint("calculate 1+1", ["code"]) is None
    assert meta_tool_pin_names(["code"], task="calculate 1+1") == set()


def test_pin_names(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "true")
    assert meta_tool_pin_names(["code", "x"], task="calculate mean") == {"code"}
    assert meta_tool_pin_names(["code"], task="chitchat") == set()


def test_ensure_auto_bind(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "true")
    monkeypatch.setenv("AIPLAT_META_TOOL_AUTO_BIND", "true")
    ctx: dict = {}
    out = ensure_code_meta_tool([], task="calculate factorial of 10", context=ctx)
    assert len(out) == 1
    assert getattr(out[0], "name", None) == "code"
    assert ctx.get("_meta_tool_auto_bound") is True


def test_ensure_no_bind_when_disabled(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_AUTO_BIND", "false")
    out = ensure_code_meta_tool([], task="calculate 1+1", context={})
    assert out == []


def test_apply_meta_tool_config_flags():
    from core.harness.execution.meta_tool import apply_meta_tool_config

    ctx: dict = {}
    apply_meta_tool_config(ctx, {"enabled": True, "auto_bind": True, "force": True})
    assert ctx["_prefer_code_meta_tool"] is True
    assert ctx["_meta_tool_auto_bind"] is True
    assert ctx["_force_code_meta_tool"] is True


def test_force_pin_without_intent(monkeypatch):
    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "true")
    ctx = {"_force_code_meta_tool": True}
    assert meta_tool_pin_names(["code"], task="chitchat", context=ctx) == {"code"}
    hint = build_meta_tool_hint("chitchat", ["code"], context=ctx)
    assert hint and "META TOOL" in hint


def test_apply_then_auto_bind(monkeypatch):
    from core.harness.execution.meta_tool import apply_meta_tool_config

    monkeypatch.setenv("AIPLAT_META_TOOL_CODE", "false")  # env off — context overrides
    ctx: dict = {}
    apply_meta_tool_config(ctx, {"enabled": True, "auto_bind": True})
    assert meta_tool_enabled(ctx) is True
    out = ensure_code_meta_tool([], task="calculate sum", context=ctx)
    assert len(out) == 1 and getattr(out[0], "name", None) == "code"
