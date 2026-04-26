import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_apply_suggestion_to_workspace_skill_md(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","*":"ask"}')

    # Create a workspace skill SKILL.md
    skill_id = "ws_demo_skill"
    skill_dir = Path(tmp_path) / ".aiplat" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        f"name: {skill_id}\n"
        "description: 初始描述\n"
        "trigger_conditions:\n"
        "  - 初始\n"
        "---\n"
        "\n"
        "SOP: placeholder\n",
        encoding="utf-8",
    )

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Create suite for trigger eval targeting the workspace skill
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={
                "name": "apply_skill_md_suite",
                "scope": "workspace",
                "target_skill_id": skill_id,
                "positive_queries": ["表格 表格 表格"],  # will become false negative
                "negative_queries": ["总结一下"],
            },
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        # Force false negative by overriding catalog so another skill wins
        skills_override = [
            {"skill_id": skill_id, "name": "WS Skill", "description": "无关描述", "scope": "workspace", "trigger_conditions": ["初始"], "keywords": {}},
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
        assert isinstance(patch, dict)

        ap = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/apply-skill-suggestion",
            headers=hdr,
            json={"patch": patch, "apply": True, "scope": "workspace"},
        )
        assert ap.status_code == 200, ap.text
        assert ap.json().get("applied") is True

    # Verify file updated
    updated = skill_md.read_text(encoding="utf-8")
    assert "trigger_conditions" in updated
    assert "表格" in updated

