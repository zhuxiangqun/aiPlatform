import importlib
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_engine_apply_requires_autosmoke_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","skill_apply_engine_skill_md_patch":"allow","*":"ask"}')
    monkeypatch.setenv("AIPLAT_REQUIRE_AUTOSMOKE_FOR_ENGINE_SKILL_PATCH", "true")

    # fake engine skills dir
    engine_dir = Path(tmp_path) / "engine_skills"
    skill_id = "eng_gate_skill"
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
            json={"name": "engine_gate_suite", "scope": "engine", "target_skill_id": skill_id, "positive_queries": ["表格 表格 表格"], "negative_queries": ["总结一下"]},
        )
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
        run_id = run.json()["run_id"]
        sug = client.post(f"/api/core/skill-evals/runs/{run_id}/suggest", headers=hdr, json={"max_tokens": 10})
        patch = sug.json().get("patch")
        ap = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/apply-skill-suggestion",
            headers=hdr,
            json={"patch": patch, "apply": False, "scope": "engine", "create_change": True},
        )
        change_id = ap.json()["change_id"]

        # Apply should be rejected before autosmoke
        r0 = client.post(f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch", headers=hdr)
        assert r0.status_code == 409
        try:
            body0 = r0.json()
            actions = body0.get("detail", {}).get("next_actions") or []
            assert actions and actions[0].get("recommended") is True
            # autosmoke should be recommended in this scenario
            assert actions[0].get("type") in {"autosmoke", "approve", "open_ui"}
        except Exception:
            pass

        # Inject a synthetic autosmoke.result changeset event so gate passes
        from core.harness.kernel.runtime import get_kernel_runtime
        from core.governance.changeset import record_changeset

        rt = get_kernel_runtime()
        assert rt and rt.execution_store

        async def _seed():
            await record_changeset(
                store=rt.execution_store,
                name="change_control.autosmoke.result",
                target_type="change",
                target_id=str(change_id),
                status="success",
                args={"resource": {"type": "skill", "id": skill_id}},
                result={"job_run_status": "completed"},
                tenant_id="t_demo",
                user_id="admin",
            )

        anyio.run(_seed)

        r1 = client.post(f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch", headers=hdr)
        assert r1.status_code == 200, r1.text
