from core.management.skill_linter import lint_skill, propose_skill_fixes


def test_lint_proposes_routing_disambiguate_fix():
    skill = {
        "id": "demo_skill",
        "name": "demo_skill",
        "description": "用于处理代码问题",
        "type": "analysis",
        "status": "enabled",
        "config": {},
        "input_schema": {"prompt": {"type": "string", "required": True}},
        "output_schema": {"markdown": {"type": "string", "required": True}},
        "metadata": {
            "skill_kind": "rule",
            "trigger_conditions": ["帮我看看代码"],
            "keywords": {"objects": ["代码"], "actions": ["审查"], "constraints": [], "synonyms": []},
            "_observability": {
                "selected": 20,
                "selected_not_top1": 8,
                "selected_not_in_candidates": 1,
                "selected_rank_avg": 2.5,
                "selected_rank_ge3": 6,
            },
        },
    }
    lint = lint_skill(skill)
    assert any(x.get("code") == "routing_needs_disambiguation" for x in (lint.get("warnings") or []))
    fx = propose_skill_fixes(skill=skill, lint=lint)
    fixes = fx.get("fixes") or []
    assert any(f.get("fix_id") == "fix_routing_disambiguate" for f in fixes)

