import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_eval_quality_suite_and_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_quality":"allow","demo_readonly_summarize":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={
                "name": "demo_summarize_quality",
                "scope": "engine",
                "target_skill_id": "demo_readonly_summarize",
                "quality_cases": [
                    {
                        "name": "case_1",
                            "input": {"text": "第一句。\n第二句。\n第三句。", "max_bullets": 3},
                        "expected": {"success": True, "require_keys": ["title", "bullets", "short_summary"], "bullets_min": 3},
                    }
                ],
            },
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        run = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/run",
            headers=hdr,
            json={"eval_kind": "quality", "max_cases": 10},
        )
        assert run.status_code == 200, run.text
        run_id = run.json()["run_id"]

        run_row = client.get(f"/api/core/skill-evals/runs/{run_id}", headers=hdr)
        assert run_row.status_code == 200, run_row.text
        metrics = (run_row.json().get("metrics") or {})
        assert metrics.get("counts", {}).get("total") == 1
        assert metrics.get("counts", {}).get("passed") == 1

        results = client.get(f"/api/core/skill-evals/runs/{run_id}/results", headers=hdr)
        assert results.status_code == 200, results.text
        items = results.json().get("items") or []
        assert len(items) == 1
        payload = (items[0].get("candidates") or {})
        assert "grade" in payload
