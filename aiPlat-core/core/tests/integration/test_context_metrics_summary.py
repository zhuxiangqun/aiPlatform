import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_context_metrics_recorded_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")

        r = client.post(
            "/api/core/diagnostics/prompt/assemble",
            json={"messages": [{"role": "user", "content": "hello"}], "user_id": "admin", "session_id": "s1", "enable_project_context": False},
        )
        assert r.status_code == 200, r.text

        s = client.get("/api/core/diagnostics/context/metrics/summary?window_hours=24&top_n=5")
        assert s.status_code == 200, s.text
        data = s.json()
        assert int(data.get("total") or 0) >= 1

