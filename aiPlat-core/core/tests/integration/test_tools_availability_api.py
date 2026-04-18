import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tools_list_includes_availability(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server
    from core.apps.tools.base import get_tool_registry, BaseTool
    from core.harness.interfaces.tool import ToolConfig, ToolResult

    importlib.reload(server)

    class DummyUnavailable(BaseTool):
        def __init__(self):
            super().__init__(ToolConfig(name="dummy_unavailable", description="x", parameters={}))

        def check_available(self):
            return False, "missing_dependency"

        async def execute(self, params):
            return ToolResult(success=False, error="nope")

    reg = get_tool_registry()
    reg.register(DummyUnavailable())

    with TestClient(server.app) as client:
        r = client.get("/api/core/tools?limit=200&offset=0")
        assert r.status_code == 200
        tools = r.json()["tools"]
        dummy = [t for t in tools if t["name"] == "dummy_unavailable"][0]
        assert dummy["available"] is False
        assert dummy["unavailable_reason"] == "missing_dependency"

        r2 = client.get("/api/core/tools?limit=200&offset=0&available_only=true")
        names = [t["name"] for t in r2.json()["tools"]]
        assert "dummy_unavailable" not in names

