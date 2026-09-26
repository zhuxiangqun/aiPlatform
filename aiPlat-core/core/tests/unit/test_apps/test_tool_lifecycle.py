"""Tool listing lifecycle store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_tool_lifecycle_default_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.apps.tools import lifecycle as lc

    assert lc.get_tool_status("file_operations") == "draft"
    assert lc.set_tool_status("file_operations", "ready") == "ready"
    assert lc.get_tool_status("file_operations") == "ready"
    assert lc.set_tool_status("file_operations", "listed") == "listed"

    store = json.loads((tmp_path / "data" / "tool_lifecycle.json").read_text(encoding="utf-8"))
    assert store["file_operations"] == "listed"


def test_tool_lifecycle_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.apps.tools import lifecycle as lc

    with pytest.raises(ValueError):
        lc.set_tool_status("x", "bogus")


def test_tool_lifecycle_mirrors_workspace_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setenv("AIPLAT_TOOLS_PATH", str(tools))
    py = tools / "square_calc.py"
    py.write_text("TOOL_DEF = {}\n", encoding="utf-8")
    from core.apps.tools import lifecycle as lc

    lc.set_tool_status("square_calc", "published", tool_path=str(py))
    manifest = Path(str(py).replace(".py", ".TOOL.manifest.json"))
    assert manifest.exists()
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "published"
