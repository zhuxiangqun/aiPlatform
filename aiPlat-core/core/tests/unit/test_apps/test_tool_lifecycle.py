"""Tool listing lifecycle store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_tool_lifecycle_default_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.apps.tools import lifecycle as lc

    # Unknown / local-only name (not in engine registry) → draft
    assert lc.get_tool_status("local_only_unregistered") == "draft"
    assert lc.set_tool_status("local_only_unregistered", "ready") == "ready"
    assert lc.get_tool_status("local_only_unregistered") == "ready"
    assert lc.set_tool_status("local_only_unregistered", "listed") == "listed"

    store = json.loads((tmp_path / "data" / "tool_lifecycle.json").read_text(encoding="utf-8"))
    assert store["local_only_unregistered"] == "listed"


def test_engine_tool_defaults_to_listed(tmp_path, monkeypatch):
    """Builtin engine tools are listed by default so app agents can bind them."""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    class _Cfg:
        metadata: dict = {}

    class _Tool:
        _config = _Cfg()

    class _Reg:
        def get(self, name: str):
            return _Tool() if name == "routed_retrieve" else None

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    from core.apps.tools import lifecycle as lc

    assert lc.get_tool_status("routed_retrieve") == "listed"
    # Explicit override still wins
    assert lc.set_tool_status("routed_retrieve", "deprecated") == "deprecated"
    assert lc.get_tool_status("routed_retrieve") == "deprecated"


def test_workspace_tool_not_auto_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    class _Cfg:
        metadata = {"provenance": {"scope": "workspace"}}

    class _Tool:
        _config = _Cfg()

    class _Reg:
        def get(self, name: str):
            return _Tool() if name == "square_calc" else None

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())
    from core.apps.tools import lifecycle as lc

    assert lc.get_tool_status("square_calc") == "draft"


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
    assert lc.get_tool_status("square_calc", tool_path=str(py)) == "published"
    mp = tools / "square_calc.TOOL.manifest.json"
    assert mp.exists()
    assert json.loads(mp.read_text(encoding="utf-8"))["status"] == "published"
