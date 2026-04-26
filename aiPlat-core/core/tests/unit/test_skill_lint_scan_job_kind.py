import pytest


@pytest.mark.asyncio
async def test_harness_skill_lint_scan_runs(tmp_path, monkeypatch):
    # Isolate DB and workspace skill path
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))

    from core.server import app
    from core.server import get_harness
    from fastapi.testclient import TestClient
    from core.harness.kernel.types import ExecutionRequest

    with TestClient(app) as client:
        # trigger lifespan init
        client.get("/api/core/permissions/stats")

        harness = get_harness()
        res = await harness.execute(
            ExecutionRequest(
                kind="skill_lint_scan",  # type: ignore[arg-type]
                target_id="skill_lint_scan",
                payload={"scopes": ["workspace"], "include_full": False, "max_items": 20},
                user_id="system",
                session_id="ops",
            )
        )
        assert res.ok is True
        assert res.payload.get("status") == "completed"
        assert "top" in (res.payload or {})
