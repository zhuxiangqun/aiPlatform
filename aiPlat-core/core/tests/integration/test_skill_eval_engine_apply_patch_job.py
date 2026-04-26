import importlib
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_engine_patch_apply_job_updates_file_and_change_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","skill_apply_engine_skill_md_patch":"allow","*":"ask"}')

    # Create a fake engine skills dir and point env to it
    engine_dir = Path(tmp_path) / "engine_skills"
    skill_id = "eng_apply_skill"
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
            json={"name": "engine_apply_suite", "scope": "engine", "target_skill_id": skill_id, "positive_queries": ["表格 表格 表格"], "negative_queries": ["总结一下"]},
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

        # Create a gate policy and apply by gate_policy_id (productization path)
        from core.harness.kernel.runtime import get_kernel_runtime

        rt = get_kernel_runtime()
        assert rt and rt.execution_store

        async def _seed_gate_policy():
            await rt.execution_store.upsert_global_setting(
                key="gate_policies",
                value={
                    "default_id": "test",
                    "items": [
                        {
                            "policy_id": "test",
                            "name": "test",
                            "config": {"apply_gate": {"gate_policy": "autosmoke", "require_autosmoke": False}},
                        }
                    ],
                },
            )

        anyio.run(_seed_gate_policy)

        # Apply via change-control job endpoint
        jobres = client.post(f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch?gate_policy_id=test", headers=hdr)
        assert jobres.status_code == 200, jobres.text

        # File updated (trigger_conditions now contains 表格 bigram)
        content = skill_md.read_text(encoding="utf-8")
        assert "表格" in content

        # Change-control latest should now be "applied"
        cc = client.get(f"/api/core/change-control/changes/{change_id}", headers=hdr)
        assert cc.status_code == 200, cc.text
        body = cc.json()
        latest = (body.get("latest") or {})
        assert latest.get("name") in {"skill_eval.engine_skill_md_patch_applied", "skill_eval.engine_skill_md_patch_proposed"}
        events = (body.get("events") or {}).get("items") if isinstance(body.get("events"), dict) else []
        names = [e.get("name") for e in (events or []) if isinstance(e, dict)]
        assert "gate_policy.resolved" in names
        assert "code_intel.report" in names
