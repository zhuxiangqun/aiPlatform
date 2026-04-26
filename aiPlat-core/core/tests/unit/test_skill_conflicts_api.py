import pytest


@pytest.mark.asyncio
async def test_skill_conflicts_api_smoke(tmp_path, monkeypatch):
    # Isolate DB and workspace skill path
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    from core.server import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")  # init lifespan

        r1 = client.post(
            "/api/core/workspace/skills",
            json={
                "name": "skill_a",
                "category": "analysis",
                "description": "用于审查代码",
                "trigger_conditions": ["审查代码", "帮我看看代码", "review code", "代码审查", "代码优化", "排查bug"],
                "input_schema": {"prompt": {"type": "string", "required": True}},
                "output_schema": {"markdown": {"type": "string", "required": True}},
                "config": {},
                "template": "analysis",
                "sop": "test",
            },
        )
        assert r1.status_code == 200

        r2 = client.post(
            "/api/core/workspace/skills",
            json={
                "name": "skill_b",
                "category": "analysis",
                "description": "用于代码优化",
                "trigger_conditions": ["代码优化", "review code", "帮我看看代码", "性能优化", "排查bug", "代码审查"],
                "input_schema": {"prompt": {"type": "string", "required": True}},
                "output_schema": {"markdown": {"type": "string", "required": True}},
                "config": {},
                "template": "analysis",
                "sop": "test",
            },
        )
        assert r2.status_code == 200

        r = client.get("/api/core/workspace/skills/meta/lint-conflicts?threshold=0.1&min_overlap=2&limit=20")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert isinstance(data.get("items"), list)
        assert data.get("total", 0) >= 1
