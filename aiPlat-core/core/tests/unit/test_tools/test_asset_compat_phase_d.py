"""Phase D: ToolDiscovery hot-load gate + production listing gate."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.apps.tools.discovery import ToolDiscovery
from core.apps.tools.lifecycle import set_tool_status
from core.harness.maintenance.asset_compat import (
    TIER_MAPPED,
    TIER_NEEDS_IMPL,
    finalize_tool_compat,
    write_tool_impl_draft,
)


def _live_tool(tmp_path: Path, name: str = "echo_d") -> Path:
    py = tmp_path / f"{name}.py"
    py.write_text(
        "TOOL_DEF={'name':'%s','description':'d','parameters':{},"
        "'execute':lambda p:{'ok':True}}\n" % name,
        encoding="utf-8",
    )
    return py


def test_discovery_registers_mapped(tmp_path: Path, monkeypatch):
    py = _live_tool(tmp_path, "mapped_hot")
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "workspace_create"})
    assert finalize_tool_compat(py)["tier"] == TIER_MAPPED

    from core.apps.tools.base import get_tool_registry

    reg = get_tool_registry()
    # isolate: clear prior name if any
    try:
        reg.unregister("mapped_hot")
    except Exception:
        pass

    report = ToolDiscovery(tmp_path).register_with_report()
    assert report["registered"] >= 1
    assert not any(s.get("id") == "mapped_hot" for s in report["skipped"])
    assert reg.get("mapped_hot") is not None


def test_discovery_skips_needs_impl(tmp_path: Path):
    # Live .py + import_draft pattern → needs_impl COMPAT (not schedulable)
    live = tmp_path / "needs_hot.py"
    live.write_text(
        "TOOL_DEF={'name':'needs_hot','description':'','parameters':{},'execute':lambda p:{}}\n",
        encoding="utf-8",
    )
    c = finalize_tool_compat(live, adapt_summary={"adapted": True, "pattern": "import_draft"})
    assert c["tier"] == TIER_NEEDS_IMPL
    assert c["schedulable"] is False

    from core.apps.tools.base import get_tool_registry

    reg = get_tool_registry()
    try:
        reg.unregister("needs_hot")
    except Exception:
        pass

    report = ToolDiscovery(tmp_path).register_with_report()
    skipped_ids = {s.get("id") for s in report["skipped"]}
    assert "needs_hot" in skipped_ids
    assert reg.get("needs_hot") is None


def test_discovery_fail_open_no_compat(tmp_path: Path):
    _live_tool(tmp_path, "legacy_hot")
    # no COMPAT file
    from core.apps.tools.base import get_tool_registry

    reg = get_tool_registry()
    try:
        reg.unregister("legacy_hot")
    except Exception:
        pass

    report = ToolDiscovery(tmp_path).register_with_report()
    assert report["registered"] >= 1
    assert reg.get("legacy_hot") is not None


def test_listing_gate_blocks_needs_impl(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "data").mkdir(parents=True)
    py = _live_tool(tmp_path, "list_block")
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "import_draft"})
    with pytest.raises(ValueError, match="tool_not_schedulable_for_listing"):
        set_tool_status("list_block", "listed", tool_path=str(py))


def test_listing_gate_allows_mapped(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "data").mkdir(parents=True)
    py = _live_tool(tmp_path, "list_ok")
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "workspace_create"})
    st = set_tool_status("list_ok", "listed", tool_path=str(py))
    assert st == "listed"


def test_facade_wraps_discovery_report(tmp_path: Path):
    """CoreFacade.tool_discovery_register_with_report is a thin wrap (avoid full facade import)."""
    import inspect

    from core.apps.tools import discovery as disc_mod

    src = Path(disc_mod.__file__).read_text(encoding="utf-8")
    assert "def register_with_report" in src
    # Symbol present on facade source without importing the heavy module
    facade_path = Path(__file__).resolve().parents[3] / "api" / "core_facade.py"
    facade_src = facade_path.read_text(encoding="utf-8")
    assert "def tool_discovery_register_with_report" in facade_src
    assert "def tool_discovery_last_report" in facade_src
    assert "register_with_report(" in facade_src
    assert inspect.isfunction(ToolDiscovery.register_with_report)


def test_discovery_report_cache_and_refresh(tmp_path: Path):
    from core.apps.tools.discovery import (
        get_last_discovery_report,
        last_report_or_refresh,
        register_with_report,
    )

    py = _live_tool(tmp_path, "cache_hot")
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "workspace_create"})
    assert get_last_discovery_report() is None or isinstance(get_last_discovery_report(), dict)
    report = register_with_report(tmp_path)
    assert "skipped" in report and "registered" in report
    cached = get_last_discovery_report()
    assert cached is not None
    assert cached.get("registered") == report.get("registered")
    again = last_report_or_refresh(tmp_path)
    assert again.get("registered") == cached.get("registered")


def test_check_asset_compat_gates_ci():
    import subprocess
    import sys

    # .../aiPlat-core/core/tests/unit/test_tools → workspace = parents[5]
    root = Path(__file__).resolve().parents[5]
    script = root / "scripts" / "check_asset_compat_gates.py"
    assert script.is_file(), f"missing {script}"
    proc = subprocess.run(
        [sys.executable, str(script), "--ci"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
