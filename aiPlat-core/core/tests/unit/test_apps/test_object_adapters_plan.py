"""P3 object adapters + unified Evaluation Plan."""
from __future__ import annotations

from core.apps.eval.service.case_match import clear_applicability_draft_cache
from core.apps.eval.service.eval_plan import (
    PLAN_SCHEMA,
    compile_plan_for_object,
)
from core.apps.eval.service.object_adapters import (
    advisory_runtime_tier,
    build_contract_for_object_type,
    default_set_ids_for_type,
)


def setup_function():
    clear_applicability_draft_cache()


def test_adapters_build_distinct_target_runtimes():
    skill = build_contract_for_object_type(object_type="skill", object_id="demo.skill")
    api = build_contract_for_object_type(object_type="api", object_id="bot1")
    app = build_contract_for_object_type(object_type="generated_app", object_id="app1")
    assert skill["object_type"] == "skill"
    assert skill["target_runtime"] == ["core_skill_execute"]
    assert api["object_id"].startswith("ext:")
    assert api["target_runtime"] == ["external_pull"]
    assert app["target_runtime"] == ["pi"]


def test_skill_plan_selects_trigger_and_quality():
    plan = compile_plan_for_object(object_type="skill", object_id="s1", live=True)
    assert plan["schema"] == PLAN_SCHEMA
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert "skill/trigger" in selected
    assert "skill/quality" in selected
    assert plan["target_runtime"] == "core_skill_execute"
    assert plan["runtime_tier"] == "core_skill_execute"
    # Agent papers must not sneak in
    assert not any(s.startswith("default/") for s in selected)


def test_api_plan_selects_chat_pull():
    plan = compile_plan_for_object(object_type="api", object_id="ext:t1", live=True)
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert selected == {"api/chat_pull"}
    assert plan["runtime_tier"] == "external_pull"


def test_generated_app_plan_and_offline_tier():
    plan = compile_plan_for_object(
        object_type="generated_app", object_id="proj", live=False
    )
    selected = {x["set_id"] for x in plan["selected_cases"]}
    assert "generated_app/pi_smoke" in selected
    assert plan["target_runtime"] == "pi"
    assert plan["runtime_tier"] == "fixture"


def test_agent_papers_not_applicable_to_skill():
    plan = compile_plan_for_object(
        object_type="skill",
        object_id="s1",
        set_ids=["default/normal", "skill/trigger"],
    )
    excluded = {x["set_id"]: x for x in plan["excluded_cases"]}
    assert excluded["default/normal"]["status"] == "not_applicable"
    assert "skill/trigger" in {x["set_id"] for x in plan["selected_cases"]}


def test_default_set_ids_and_advisory_tier():
    assert "skill/quality" in default_set_ids_for_type("skill")
    assert (
        advisory_runtime_tier(
            object_type="generated_app", live=True, target_runtime=["pi"]
        )
        == "pi"
    )
