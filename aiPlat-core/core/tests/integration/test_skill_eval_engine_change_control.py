import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_engine_skill_suggestion_creates_change_control(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","*":"ask"}')

    # Create a fake engine skills dir and point env to it
    engine_dir = Path(tmp_path) / "engine_skills"
    skill_id = "eng_demo_skill"
    skill_md = engine_dir / skill_id / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        "---\n"
        f"name: {skill_id}\n"
        "description: 初始描述\n"
        "trigger_conditions:\n"
        "  - 初始\n"
        "---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_ENGINE_SKILLS_PATH", str(engine_dir))

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={
                "name": "engine_change_suite",
                "scope": "engine",
                "target_skill_id": skill_id,
                "positive_queries": ["表格 表格 表格"],
                "negative_queries": ["总结一下"],
            },
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        skills_override = [
            {"skill_id": skill_id, "name": "ENG Skill", "description": "无关描述", "scope": "engine", "trigger_conditions": ["初始"], "keywords": {}},
            {"skill_id": "other_skill", "name": "Other", "description": "表格 处理", "scope": "engine", "trigger_conditions": ["表格"], "keywords": {}},
        ]
        run = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/run",
            headers=hdr,
            json={"mode": "heuristic", "max_cases": 20, "skills_override": skills_override},
        )
        assert run.status_code == 200, run.text
        run_id = run.json()["run_id"]

        sug = client.post(f"/api/core/skill-evals/runs/{run_id}/suggest", headers=hdr, json={"max_tokens": 10})
        assert sug.status_code == 200, sug.text
        patch = (sug.json() or {}).get("patch")

        ap = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/apply-skill-suggestion",
            headers=hdr,
            json={"patch": patch, "apply": False, "scope": "engine", "create_change": True},
        )
        assert ap.status_code == 200, ap.text
        change_id = ap.json().get("change_id")
        assert isinstance(change_id, str) and change_id

        # Should be queryable via change-control endpoint (derived from changeset events)
        cc = client.get(f"/api/core/change-control/changes/{change_id}", headers=hdr)
        assert cc.status_code == 200, cc.text
        latest = (cc.json().get("latest") or {})
        assert latest.get("name") == "skill_eval.engine_skill_md_patch_proposed"

