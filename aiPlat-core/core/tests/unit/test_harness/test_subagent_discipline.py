"""Subagent return discipline — condense + isolate for parent loop."""

from __future__ import annotations

from core.harness.execution.subagent_discipline import (
    condense_return,
    discipline_status,
    filter_protocol_violations,
    max_return_chars,
    resolve_isolate_context,
    safe_truncate,
)


def _clear(monkeypatch):
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_SUBAGENT_FORCE_ISOLATE", raising=False)
    monkeypatch.delenv("AIPLAT_SUBAGENT_MAX_RETURN_CHARS", raising=False)


def test_dev_allows_non_isolate(monkeypatch):
    _clear(monkeypatch)
    isolate, meta = resolve_isolate_context(False)
    assert isolate is False
    assert meta["coerced"] is False


def test_production_coerces_isolate(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    isolate, meta = resolve_isolate_context(False)
    assert isolate is True
    assert meta["coerced"] is True
    assert discipline_status()["force_isolate_active"] is True


def test_force_on_coerces(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AIPLAT_SUBAGENT_FORCE_ISOLATE", "on")
    isolate, meta = resolve_isolate_context(False)
    assert isolate is True
    assert meta["coerced"] is True


def test_condense_strips_protocol_and_caps(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AIPLAT_SUBAGENT_MAX_RETURN_CHARS", "120")
    blob = (
        "Thought: I will call tools\n"
        "Action: sys_tool_call foo\n"
        "```python\nprint(1)\n```\n"
        + ("结论。" * 80)
    )
    out = condense_return(blob)
    assert "```" not in out
    assert "sys_tool_call" not in out.lower() or "[tool calls removed]" in out
    assert len(out) <= max_return_chars() + 40  # suffix allowance
    assert "condensed from" in out or len(out) <= 120


def test_condense_dict_answer():
    out = condense_return({"answer": "hello world", "sources": [1, 2], "errors": []})
    assert "hello world" in out
    assert "Sources: 2" in out


def test_safe_truncate_boundary():
    text = "aaa. " + ("bbbb " * 50)
    out = safe_truncate(text, 40)
    assert len(out) < len(text)
    assert "condensed from" in out


def test_filter_protocol_violations():
    text = "Thought: x\nAction: y\nreal answer"
    cleaned = filter_protocol_violations(text)
    assert "Thought" not in cleaned
    assert "real answer" in cleaned


def test_multi_agent_summarize_uses_discipline():
    from types import SimpleNamespace

    from core.apps.agents.multi_agent import MultiAgent

    long = "Thought: secret\n" + ("x" * 5000)
    result = SimpleNamespace(success=True, output=long, error=None)
    out = MultiAgent.summarize_subagent_result(result)
    assert "Thought" not in out
    assert len(out) <= max_return_chars() + 80


def test_discipline_status_shape(monkeypatch):
    _clear(monkeypatch)
    info = discipline_status()
    assert "force_isolate_mode" in info
    assert "max_return_chars" in info
    assert info["force_isolate_active"] is False
