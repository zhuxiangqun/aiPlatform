import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_personas_list_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        tid = "persona:agency:engineering:engineering-frontend-developer"
        up = client.post(
            "/api/core/prompts",
            headers=hdr,
            json={
                "template_id": tid,
                "name": "Frontend Developer",
                "template": "You are Frontend Developer.",
                "metadata": {"type": "persona", "source": "agency-agents", "category": "engineering", "display": {"name": "Frontend Developer", "vibe": "fast"}, "sections": {"success_metrics": "Lighthouse > 90"}},
                "require_approval": False,
            },
        )
        assert up.status_code == 200, up.text

        ls = client.get("/api/core/personas", params={"limit": 10, "offset": 0, "category": "engineering"})
        assert ls.status_code == 200, ls.text
        items = ls.json().get("items") or []
        assert any(x.get("template_id") == tid for x in items)

        g = client.get(f"/api/core/personas/{tid}")
        assert g.status_code == 200, g.text
        body = g.json()
        assert body.get("template_id") == tid
        assert body.get("sections", {}).get("success_metrics") == "Lighthouse > 90"

