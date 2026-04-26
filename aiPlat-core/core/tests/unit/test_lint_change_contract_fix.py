from core.management.skill_linter import lint_skill, propose_skill_fixes


def test_lint_change_contract_fix_for_coding_skill():
    skill = {
        "id": "code_skill_1",
        "name": "code_skill_1",
        "description": "用于代码修改与修复",
        "type": "coding",
        "status": "enabled",
        "input_schema": {"prompt": {"type": "string", "required": True}},
        "output_schema": {"markdown": {"type": "string", "required": True}},
        "metadata": {"tags": ["coding"], "skill_kind": "rule"},
    }
    rep = lint_skill(skill)
    assert any(w.get("code") == "missing_change_contract" for w in (rep.get("warnings") or []))
    fx = propose_skill_fixes(skill=skill, lint=rep)
    fixes = fx.get("fixes") or []
    f = next((x for x in fixes if x.get("fix_id") == "fix_add_change_contract"), None)
    assert f is not None
    ops = (f.get("patch") or {}).get("ops") or []
    assert any(op.get("path") == ["output_schema", "change_plan"] for op in ops)

