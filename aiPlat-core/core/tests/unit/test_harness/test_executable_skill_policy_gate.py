import anyio


class _DummySkill:
    def __init__(self, name="danger-skill"):
        self.name = name

        class _Cfg:
            metadata = {"permissions": ["filesystem_write"], "skill_kind": "executable"}

        self._config = _Cfg()

    async def execute(self, ctx, params):
        from core.harness.interfaces import SkillResult

        return SkillResult(success=True, output={"ok": True}, error=None)


def test_executable_skill_denied_by_rules(monkeypatch):
    monkeypatch.setenv("AIPLAT_ENFORCE_EXECUTABLE_SKILL_POLICY", "true")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"*":"deny"}')

    from core.harness.syscalls.skill import sys_skill_call

    skill = _DummySkill()
    res = anyio.run(
        lambda: sys_skill_call(
            skill,
            {"x": 1},
            user_id="u",
            session_id="s",
            trace_context={"run_id": "r1", "trace_id": "t1", "tenant_id": "ten"},
        )
    )
    assert getattr(res, "success", None) is False
    assert getattr(res, "error", None) == "policy_denied"
