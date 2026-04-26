import time
import pytest


@pytest.mark.asyncio
async def test_sys_skill_call_injects_coding_policy_profile(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))
    # allow executable skill without approval in this unit test
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"*":"allow"}')
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_REQUIRE_PERMISSIONS", "false")

    import core.server as srv
    from fastapi.testclient import TestClient
    from core.harness.syscalls.skill import sys_skill_call
    from core.harness.interfaces import SkillResult

    seen = {}

    class DummySkill:
        name = "dummy_coding_skill"

        async def execute(self, context, params):
            seen["params"] = params
            return SkillResult(success=True, output={"ok": True}, error=None)

        async def validate(self, params):
            return True

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")  # init lifespan/runtime

        await sys_skill_call(
            DummySkill(),
            {"prompt": "hello"},
            user_id="u1",
            session_id="s1",
            trace_context={"tenant_id": "default", "run_id": "r1", "routing_decision_id": "rtd_x", "coding_policy_profile": "karpathy_v1"},
        )

        assert isinstance(seen.get("params"), dict)
        assert seen["params"].get("_coding_policy_profile") == "karpathy_v1"

        # routing event should carry coding_policy_profile
        res = await srv._execution_store.list_syscall_events(limit=50, offset=0, tenant_id=None, kind="routing", name="skill_route")
        items = res.get("items") or []
        assert any((it.get("args") or {}).get("coding_policy_profile") == "karpathy_v1" for it in items)
