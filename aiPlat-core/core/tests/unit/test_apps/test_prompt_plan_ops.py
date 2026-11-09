"""Prompt Plan-chain exam runner (Object Contract §0.8 P0)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.exam_runtime_tier import annotate_prompt_plan_runtime
from core.apps.eval.service.prompt_plan_ops import (
    load_prompt_set_json,
    run_prompt_plan_exam,
    score_prompt_output,
)


def test_load_prompt_basic_set():
    data = load_prompt_set_json("prompt/basic")
    assert data.get("set_id") == "prompt/basic"
    assert isinstance(data.get("tasks"), list) and data["tasks"]


def test_score_must_contain_and_paths():
    ok = score_prompt_output("hello 智能门锁 world", {"must_contain": ["智能门锁"]})
    assert ok["status"] == "pass"
    bad = score_prompt_output("nothing", {"must_contain": ["智能门锁"]})
    assert bad["status"] == "fail"
    path_ok = score_prompt_output(
        "缺少变量 customer",
        {
            "paths": [
                {"id": "any_hit", "must_contain_any": ["缺少", "请提供", "customer"]},
            ]
        },
    )
    assert path_ok["status"] == "pass"


def test_annotate_prompt_plan_runtime_fixture():
    dry = annotate_prompt_plan_runtime(live=False)
    assert dry["runtime_tier"] == "fixture"
    assert dry["target_runtime"] == "prompt_execute"
    assert dry["runtime_claim"] is False
    assert dry["execution_mode"] == "prompt_plan_dry"
    live = annotate_prompt_plan_runtime(live=True)
    assert live["execution_mode"] == "prompt_plan_llm"
    assert live["runtime_claim"] is False


@pytest.mark.asyncio
async def test_run_prompt_plan_exam_dry_basic():
    out = await run_prompt_plan_exam(
        object_id="tpl_demo",
        set_ids=["prompt/basic", "prompt/missing_vars"],
        include_special=False,
        live=False,
    )
    assert out.get("ok") is True
    assert out.get("accuracy_claim") is False
    assert out.get("runtime_tier") == "fixture"
    assert out.get("execution_mode") == "prompt_plan_dry"
    assert out.get("evaluation_plan") or out.get("plan_id") or (
        (out.get("evaluation_plan") or {}).get("plan_id")
        if isinstance(out.get("evaluation_plan"), dict)
        else True
    )
    plan = out.get("evaluation_plan") or {}
    assert isinstance(plan, dict)
    assert plan.get("schema") in (
        "eval.evaluation_plan.v1",
        "eval.evaluation_plan.v2",
    ) or "selected_cases" in plan or out.get(
        "selected_set_ids"
    )
    assert "prompt/basic" in (out.get("selected_set_ids") or [])
    assert out.get("counts", {}).get("tasks", 0) >= 1
    assert any(p.get("status") == "done" for p in (out.get("papers") or []))
