import pytest


@pytest.mark.asyncio
async def test_coding_profile_requires_change_contract(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"*":"allow"}')
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_REQUIRE_PERMISSIONS", "false")
    monkeypatch.setenv("AIPLAT_CODING_POLICY_REQUIRE_CONTRACT", "true")

    import core.server as srv
    from fastapi.testclient import TestClient
    from core.harness.syscalls.skill import sys_skill_call
    from core.harness.interfaces import SkillConfig, SkillContext, SkillResult

    class DummyCodingSkill:
        def __init__(self):
            self._config = SkillConfig(
                name="dummy_coding_skill",
                description="coding skill",
                metadata={"category": "coding", "tags": ["coding"]},
                input_schema={"prompt": {"type": "string", "required": True}},
                # missing contract fields on purpose
                output_schema={"markdown": {"type": "string", "required": True}},
            )

        async def execute(self, context: SkillContext, params):
            return SkillResult(success=True, output={"markdown": "ok"}, error=None)

        async def validate(self, params):
            return True

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")

        res = await sys_skill_call(
            DummyCodingSkill(),
            {"prompt": "hello"},
            user_id="u1",
            session_id="s1",
            trace_context={"tenant_id": "default", "run_id": "r1", "routing_decision_id": "rtd_x", "coding_policy_profile": "karpathy_v1"},
        )
        # approval manager may not exist in unit runtime; still should fail closed as approval_required
        assert res.success is False
        assert res.error in ("approval_required", "policy_denied")

