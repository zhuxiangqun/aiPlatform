import anyio


def test_tool_search_tool_can_find_registered_tools():
    from core.apps.tools.base import CalculatorTool, ToolSearchTool, get_tool_registry

    reg = get_tool_registry()
    # ensure the tool is present for this test (idempotent)
    reg.register(CalculatorTool())

    t = ToolSearchTool()
    res = anyio.run(t.execute, {"query": "calculator", "limit": 5, "include_schema": True})
    assert res.success is True
    out = res.output
    assert isinstance(out, dict)
    items = out.get("items")
    assert isinstance(items, list)
    assert any(i.get("name") == "calculator" for i in items)

