import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_apply_gate_blocks_on_trigger_eval_and_security_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    # allow gate jobs (skill_eval_trigger) to execute
    monkeypatch.setenv(
        "AIPLAT_EXEC_SKILL_PERMISSION_RULES",
        '{"skill_eval_trigger":"allow","skill_eval_quality":"allow","skill_apply_engine_skill_md_patch":"allow","*":"ask"}',
    )
    # bypass autosmoke/approval defaults for this test via query params
    monkeypatch.setenv("AIPLAT_ENGINE_SKILL_PATCH_APPLY_GATE", "autosmoke")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Create a suite that is guaranteed to fail Trigger Eval (target_skill_id doesn't exist)
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={
                "name": "gate_trigger_suite",
                "scope": "engine",
                "target_skill_id": "no_such_skill",
                "positive_queries": ["表格 表格 表格"],
                "negative_queries": ["总结一下"],
            },
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        # Seed a proposed change-control patch
        from core.governance.changeset import record_changeset
        from core.harness.kernel.runtime import get_kernel_runtime

        rt = get_kernel_runtime()
        assert rt and rt.execution_store
        change_id = "change_gate_demo"

        async def _seed():
            await record_changeset(
                store=rt.execution_store,
                name="skill_eval.engine_skill_md_patch_proposed",
                target_type="change",
                target_id=change_id,
                status="success",
                args={"suite_id": suite_id, "skill_id": "eng_dummy_skill", "targets": [{"type": "skill", "id": "eng_dummy_skill"}]},
                result={"path": "/tmp/ENG/SKILL.md", "updated_raw": "---\nname: eng_dummy_skill\ndescription: x\n---\n"},
                tenant_id="t_demo",
                user_id="admin",
            )

        anyio.run(_seed)

        # 1) Trigger eval gate should block
        r0 = client.post(
            f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch"
            f"?require_autosmoke=false&require_approval=false&eval_gate=trigger&trigger_suite_id={suite_id}&trigger_f1_min=0.9",
            headers=hdr,
        )
        assert r0.status_code == 409, r0.text
        body0 = r0.json().get("detail", {})
        assert body0.get("code") in {"eval_gate_failed", "apply_gate_failed"}
        actions0 = body0.get("next_actions") or []
        assert actions0

        # 2) Security scan gate should block on secrets
        async def _seed_secret():
            await record_changeset(
                store=rt.execution_store,
                name="skill_eval.engine_skill_md_patch_proposed",
                target_type="change",
                target_id="change_gate_secret",
                status="success",
                args={"suite_id": suite_id, "skill_id": "eng_dummy_skill2", "targets": [{"type": "skill", "id": "eng_dummy_skill2"}]},
                # include an OpenAI-like API key pattern
                result={"path": "/tmp/ENG2/SKILL.md", "updated_raw": "---\nname: eng_dummy_skill2\ndescription: sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n---\n"},
                tenant_id="t_demo",
                user_id="admin",
            )

        anyio.run(_seed_secret)

        r1 = client.post(
            "/api/core/change-control/changes/change_gate_secret/apply-engine-skill-md-patch"
            "?require_autosmoke=false&require_approval=false&security_gate=scan_block",
            headers=hdr,
        )
        assert r1.status_code == 409, r1.text
        body1 = r1.json().get("detail", {})
        assert body1.get("code") in {"security_gate_failed", "apply_gate_failed"}
        actions1 = body1.get("next_actions") or []
        assert actions1

        # 3) Apply gate should block when autosmoke is required but missing (productized via gate_policy_id)
        async def _seed_gate_policy():
            await rt.execution_store.upsert_global_setting(
                key="gate_policies",
                value={
                    "default_id": "prod",
                    "items": [{"policy_id": "prod", "name": "prod", "config": {"apply_gate": {"gate_policy": "autosmoke", "require_autosmoke": True}}}],
                },
            )

        anyio.run(_seed_gate_policy)
        r2 = client.post(
            f"/api/core/change-control/changes/{change_id}/apply-engine-skill-md-patch?gate_policy_id=prod",
            headers=hdr,
        )
        assert r2.status_code == 409, r2.text
        body2 = r2.json().get("detail", {})
        assert body2.get("code") == "apply_gate_failed"
        assert any(a.get("type") == "autosmoke" for a in (body2.get("next_actions") or []))
        # event should be persisted for later UI debugging
        cc = client.get(f"/api/core/change-control/changes/{change_id}", headers=hdr)
        assert cc.status_code == 200, cc.text
        ev = (cc.json().get("events") or {}).get("items") if isinstance(cc.json().get("events"), dict) else []
        names = [e.get("name") for e in (ev or []) if isinstance(e, dict)]
        assert "apply_gate.failed" in names
