import asyncio

from core.apps.tools.base import BaseTool
from core.harness.interfaces import ToolConfig, ToolResult


class _DummyTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolConfig(
                name="dummy",
                description="dummy",
                parameters={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            )
        )

    async def execute(self, params):
        async def handler():
            return ToolResult(success=True, output=params["x"])

        return await self._call_with_tracking(params, handler, timeout=1)


def test_invalid_params_updates_stats():
    tool = _DummyTool()
    res = asyncio.run(tool.execute({}))
    assert res.success is False
    assert res.error == "Invalid params"
    stats = tool.get_stats()
    assert stats["call_count"] == 1
    assert stats["error_count"] == 1


def test_timeout_returns_timeout():
    tool = _DummyTool()

    async def slow_handler():
        await asyncio.sleep(0.2)
        return ToolResult(success=True, output="ok")

    res = asyncio.run(tool._call_with_tracking({"x": "1"}, slow_handler, timeout=0.01))
    assert res.success is False
    assert res.error == "Timeout"


def test_exception_caught():
    tool = _DummyTool()

    async def boom():
        raise RuntimeError("boom")

    res = asyncio.run(tool._call_with_tracking({"x": "1"}, boom, timeout=1))
    assert res.success is False
    assert "boom" in (res.error or "")

