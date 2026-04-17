import pytest


def test_mcp_manager_merges_paths_and_repo_overrides(tmp_path, monkeypatch):
    global_dir = tmp_path / "global_mcps"
    repo_dir = tmp_path / "repo_mcps"
    (global_dir / "x").mkdir(parents=True)
    (repo_dir / "x").mkdir(parents=True)

    (global_dir / "x" / "server.yaml").write_text(
        "name: x\nenabled: true\ntransport: sse\nurl: http://global\n",
        encoding="utf-8",
    )
    (repo_dir / "x" / "server.yaml").write_text(
        "name: x\nenabled: false\ntransport: sse\nurl: http://repo\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AIPLAT_ENGINE_MCPS_PATHS", f"{global_dir}:{repo_dir}")

    from core.management.mcp_manager import MCPManager

    mgr = MCPManager(scope="engine")
    s = mgr.get_server("x")
    assert s is not None
    assert s.url == "http://repo"
    assert s.enabled is False
