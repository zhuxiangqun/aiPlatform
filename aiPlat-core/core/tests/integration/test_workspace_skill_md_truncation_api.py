import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_workspace_skill_md_truncates_large_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/workspace/skills",
            json={"id": "ws_big_md", "name": "WS Big MD", "description": "d", "type": "general"},
        )
        assert r.status_code == 200, r.text
        # Get current SKILL.md path from preview endpoint (authoritative).
        r0 = client.get("/api/core/workspace/skills/ws_big_md/skill-md")
        assert r0.status_code == 200, r0.text
        md_path = r0.json().get("path")
        assert md_path, "workspace SKILL.md path missing"

        # Overwrite SKILL.md with a very large payload.
        big = "A" * 250_000
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(big)

        r2 = client.get("/api/core/workspace/skills/ws_big_md/skill-md")
        assert r2.status_code == 200, r2.text
        data = r2.json()
        content = data["content"]
        assert len(content) <= 200_000 + 20
        assert content.endswith("[TRUNCATED]")
