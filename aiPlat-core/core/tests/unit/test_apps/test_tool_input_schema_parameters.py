"""ToolMetadata + input_schema must surface as ToolConfig.parameters for execute UI."""
from __future__ import annotations

from core.apps.tools.base import BaseTool, ToolMetadata
from core.apps.tools.routed_retrieve import RoutedRetrieveTool


def test_toolmetadata_input_schema_syncs_to_parameters():
    class _T(BaseTool):
        def __init__(self):
            super().__init__(ToolMetadata(name="t", description="d", category="x"))
            self.input_schema = {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, args):
            return {"ok": True}

    t = _T()
    assert t._config.parameters.get("required") == ["query"]
    assert "query" in (t._config.parameters.get("properties") or {})
    assert t.input_schema["required"] == ["query"]


def test_routed_retrieve_exposes_query_schema():
    tool = RoutedRetrieveTool()
    params = tool._config.parameters
    assert isinstance(params, dict)
    assert "query" in (params.get("properties") or {})
    assert "query" in (params.get("required") or [])


def test_tool_parameters_helper():
    from core.api.routers.tools import _tool_parameters

    tool = RoutedRetrieveTool()
    p = _tool_parameters(tool)
    assert p.get("required") == ["query"]
