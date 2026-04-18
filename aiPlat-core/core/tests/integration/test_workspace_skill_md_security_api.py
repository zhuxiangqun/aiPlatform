import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_workspace_skill_md_rejects_outside_workspace_scope(tmp_path, monkeypatch):
    """
    The /workspace/skills/{id}/skill-md endpoint must refuse reading files
    outside the workspace skills roots (403).
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    # Create a real workspace skill so the skill exists.
    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/workspace/skills",
            json={"id": "ws_skill_1", "name": "WS Skill 1", "description": "d", "type": "general"},
        )
        assert r.status_code == 200, r.text

        # Create an "evil" file outside the workspace skills directory roots.
        evil = tmp_path / "evil.md"
        evil.write_text("# EVIL", encoding="utf-8")

        # Monkeypatch the internal md resolver to return an out-of-scope path.
        assert server._workspace_skill_manager is not None
        monkeypatch.setattr(server._workspace_skill_manager, "_find_skill_md", lambda _sid: str(evil), raising=True)

        r2 = client.get("/api/core/workspace/skills/ws_skill_1/skill-md")
        assert r2.status_code == 403, r2.text


@pytest.mark.integration
def test_workspace_skill_md_returns_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Skill does not exist
        r = client.get("/api/core/workspace/skills/not_exists/skill-md")
        assert r.status_code == 404, r.text

