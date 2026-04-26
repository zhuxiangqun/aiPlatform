import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_import_agency_agents_creates_prompt_templates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    # Create a fake agency-agents folder
    root = tmp_path / "agency-agents"
    (root / "engineering").mkdir(parents=True)
    md = """---
name: Frontend Developer
description: demo
---
# Frontend Developer
You are a frontend expert.
"""
    (root / "engineering" / "engineering-frontend-developer.md").write_text(md, encoding="utf-8")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        r = client.post("/api/core/personas/import/agency-agents", headers=hdr, json={"root": str(root), "categories": ["engineering"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        tid = body["items"][0]["template_id"]
        assert tid.startswith("persona:agency:engineering:")

        # Ensure prompt template exists
        g = client.get(f"/api/core/prompts/{tid}")
        assert g.status_code == 200, g.text
        tpl = g.json()
        assert tpl["template_id"] == tid
        assert "You are a frontend expert." in tpl["template"]

