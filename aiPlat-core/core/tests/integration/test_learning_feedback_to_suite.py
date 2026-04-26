import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_learning_feedback_appends_to_trigger_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={"name": "fb_suite", "scope": "workspace", "target_skill_id": "s1", "positive_queries": [], "negative_queries": []},
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        fb = client.post(
            "/api/core/learning/feedback",
            headers=hdr,
            json={"suite_id": suite_id, "suite_kind": "trigger", "decision": "accept", "query": "帮我做个表格"},
        )
        assert fb.status_code == 200, fb.text
        out = fb.json()
        assert out.get("status") == "ok"
        assert out.get("suite", {}).get("config", {}).get("positive_queries") == ["帮我做个表格"]

