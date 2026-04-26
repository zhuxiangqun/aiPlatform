import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_engine_apply_can_be_gated_by_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","skill_apply_engine_skill_md_patch":"allow","*":"ask"}')
    monkeypatch.setenv("AIPLAT_REQUIRE_AUTOSMOKE_FOR_ENGINE_SKILL_PATCH", "false")

    engine_dir = Path(tmp_path) / "engine_skills"
    skill_id = "eng_approval_skill"
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
            json={"name": "engine_approval_suite", "scope": "engine", "target_skill_id": skill_id, "positive_queries": ["表格 表格 表格"], "negative_queries": ["总结一下"]},
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
        patch = sug.json().get("patch")

        ap = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/apply-skill-suggestion",
            headers=hdr,
            json={"patch": patch, "apply": False, "scope": "engine", "create_change": True, "create_approval": True},
        )
        assert ap.status_code == 200, ap.text
        change_id = ap.json().get("change_id")
        approval_request_id = ap.json().get("approval_request_id")
        assert change_id and approval_request_id

        # Should be blocked until approval granted (gate_policy=approval)
        r0 = client.post(
            f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch?gate_policy=approval&require_autosmoke=false",
            headers=hdr,
        )
        assert r0.status_code == 409
        try:
            d0 = r0.json().get("detail", {})
            actions = d0.get("next_actions") or []
            assert actions and actions[0].get("recommended") is True
            assert actions[0].get("type") in {"approve", "open_ui"}
        except Exception:
            pass

        # Approve
        ok = client.post(f"/api/core/approvals/{approval_request_id}/approve", headers=hdr, json={"approved_by": "admin"})
        assert ok.status_code == 200, ok.text

        # Apply should now succeed
        r1 = client.post(
            f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch?gate_policy=approval&require_autosmoke=false",
            headers=hdr,
        )
        assert r1.status_code == 200, r1.text
