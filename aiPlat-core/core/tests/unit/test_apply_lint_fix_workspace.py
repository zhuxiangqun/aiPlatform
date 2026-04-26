import pytest


@pytest.mark.asyncio
async def test_apply_lint_fix_workspace_adds_markdown(tmp_path, monkeypatch):
    # Isolate DB and workspace skill path
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    from core.server import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")  # init lifespan

        # create a workspace skill without markdown field
        r = client.post(
            "/api/core/workspace/skills",
            json={
                "name": "s_markdown_fix",
                "category": "generation",
                "description": "desc desc",
                "input_schema": {"prompt": {"type": "string", "required": True}},
                "output_schema": {"text": {"type": "string", "required": True}},
                "config": {},
                "template": "generation",
                "sop": "test",
            },
        )
        assert r.status_code == 200
        sid = r.json()["id"]

        # apply fix
        r2 = client.post(f"/api/core/workspace/skills/{sid}/apply-lint-fix", json={})
        assert r2.status_code == 200
        assert r2.json().get("status") in ("applied", "noop")

        # get detail and confirm markdown exists
        d = client.get(f"/api/core/workspace/skills/{sid}").json()
        assert "markdown" in (d.get("output_schema") or {})

