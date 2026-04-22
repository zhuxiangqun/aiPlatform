from dataclasses import dataclass


@dataclass
class _DummyTool:
    name: str
    description: str


def test_tools_desc_budget_always_includes_tool_search(monkeypatch):
    # Force truncation so only the first tool fits.
    monkeypatch.setenv("AIPLAT_TOOL_DESC_PER_TOOL_MAX_CHARS", "200")

    # Make total budget small but still enough to include one line + newline.
    # The loop sorts with tool_search first.
    monkeypatch.setenv("AIPLAT_TOOLS_DESC_MAX_CHARS", "80")

    from core.harness.execution.loop import ReActLoop

    tools = [
        _DummyTool(name="z_big_tool", description="x" * 200),
        _DummyTool(name="tool_search", description="search tools"),
        _DummyTool(name="a_other", description="y" * 200),
    ]
    loop = ReActLoop(tools=tools)

    text, stats = loop._build_tools_desc()  # type: ignore[attr-defined]
    assert "- tool_search:" in text
    assert "tools hidden" in text
    assert stats["tools_hidden"] > 0


def test_tools_desc_per_tool_truncation(monkeypatch):
    monkeypatch.setenv("AIPLAT_TOOL_DESC_PER_TOOL_MAX_CHARS", "30")
    monkeypatch.setenv("AIPLAT_TOOLS_DESC_MAX_CHARS", "4000")

    from core.harness.execution.loop import ReActLoop

    tools = [
        _DummyTool(name="tool_search", description="search tools"),
        _DummyTool(name="big", description="0123456789" * 20),
    ]
    loop = ReActLoop(tools=tools)
    text, stats = loop._build_tools_desc()  # type: ignore[attr-defined]
    assert "…(truncated)" in text
    assert stats["tools_truncated"] >= 1

