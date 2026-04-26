from core.management.skill_linter import lint_skill, propose_skill_fixes


def test_conflict_pair_fix_generated():
    skill = {
        "id": "skill_a",
        "name": "skill_a",
        "description": "用于审查代码",
        "type": "analysis",
        "status": "enabled",
        "input_schema": {"prompt": {"type": "string", "required": True}},
        "output_schema": {"markdown": {"type": "string", "required": True}},
        "metadata": {
            "tags": ["coding"],
            "category": "coding",
            "trigger_conditions": ["帮我看看代码", "代码审查", "review code"],
            "negative_triggers": [],
            "keywords": {"objects": ["代码"], "actions": ["审查"], "constraints": []},
            "_conflicts": [
                {
                    "scope": "workspace",
                    "skill_a": {"skill_id": "skill_a", "name": "skill_a"},
                    "skill_b": {"skill_id": "skill_b", "name": "skill_b"},
                    "jaccard": 0.5,
                    "overlap_tokens": ["帮我看看代码", "review code", "代码"],
                    "other_skill": {
                        "skill_id": "skill_b",
                        "name": "skill_b",
                        "trigger_conditions": ["性能优化", "代码优化", "review code"],
                        "negative_triggers": [],
                        "keywords": {"objects": ["性能"], "actions": ["优化"], "constraints": []},
                    },
                }
            ],
        },
    }
    rep = lint_skill(skill)
    assert any(w.get("code") == "conflict_pair_high_overlap" for w in (rep.get("warnings") or []))
    fx = propose_skill_fixes(skill=skill, lint=rep)
    fixes = fx.get("fixes") or []
    f = next((x for x in fixes if x.get("fix_id") == "fix_conflict_pair_disambiguate"), None)
    assert f is not None
    ops = (f.get("patch") or {}).get("ops") or []
    assert any(op.get("path") == ["negative_triggers"] for op in ops)
    assert any(op.get("path") == ["keywords"] for op in ops)
    # should contain opponent-only token hint
    neg_op = next((op for op in ops if op.get("path") == ["negative_triggers"]), {})
    v = neg_op.get("value") if isinstance(neg_op, dict) else None
    assert isinstance(v, list)
    assert any("性能优化" in str(x) for x in v)
