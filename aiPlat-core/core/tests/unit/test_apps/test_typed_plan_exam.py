"""Typed Plan exams for workflow / model / dataset (§0.8 P1–P2)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.exam_runtime_tier import (
    annotate_dataset_plan_runtime,
    annotate_model_plan_runtime,
    annotate_workflow_plan_runtime,
)
from core.apps.eval.service.typed_plan_exam import (
    load_typed_set_json,
    run_typed_plan_exam,
    score_dataset_task,
    score_lexical_output,
)


def test_load_workflow_and_model_sets():
    wf = load_typed_set_json("workflow/basic", object_type="workflow")
    assert wf.get("set_id") == "workflow/basic"
    assert wf.get("tasks")
    md = load_typed_set_json("model/basic", object_type="model")
    assert md.get("set_id") == "model/basic"
    assert md.get("tasks")


def test_score_model_basic_number():
    assert score_lexical_output("8", {"must_contain": ["8"]})["status"] == "pass"


def test_annotate_workflow_model_runtime():
    w = annotate_workflow_plan_runtime(live=False)
    assert w["runtime_tier"] == "fixture"
    assert w["target_runtime"] == "workspace_execute"
    assert w["execution_mode"] == "workflow_plan_dry"
    m = annotate_model_plan_runtime(live=True)
    assert m["target_runtime"] == "model_generate"
    assert m["execution_mode"] == "model_plan_llm"
    assert m["runtime_claim"] is False


@pytest.mark.asyncio
async def test_run_workflow_plan_exam_dry():
    out = await run_typed_plan_exam(
        object_type="workflow",
        object_id="wf_demo",
        set_ids=["workflow/basic"],
        live=False,
        source_refs=["workflow_plan_ops"],
    )
    assert out.get("ok") is True
    assert out.get("object_type") == "workflow"
    assert out.get("runtime_tier") == "fixture"
    assert out.get("execution_mode") == "workflow_plan_dry"
    assert out.get("accuracy_claim") is False
    assert "workflow/basic" in (out.get("selected_set_ids") or [])
    assert out.get("counts", {}).get("tasks", 0) >= 1
    assert any(p.get("status") == "done" for p in (out.get("papers") or []))
    assert isinstance(out.get("evaluation_plan"), dict)


@pytest.mark.asyncio
async def test_run_model_plan_exam_dry():
    out = await run_typed_plan_exam(
        object_type="model",
        object_id="mdl_demo",
        set_ids=["model/basic"],
        live=False,
        source_refs=["model_plan_ops"],
    )
    assert out.get("ok") is True
    assert out.get("object_type") == "model"
    assert out.get("execution_mode") == "model_plan_dry"
    assert "model/basic" in (out.get("selected_set_ids") or [])
    assert out.get("counts", {}).get("tasks", 0) >= 1


def test_score_dataset_assert_and_expect_fail():
    ok_task = {
        "fixture_table": {
            "columns": ["id", "text"],
            "rows": [["1", "a"], ["2", "b"]],
        },
        "success_criteria": {
            "dataset_assert": {"required_columns": ["id", "text"], "min_rows": 2}
        },
    }
    assert score_dataset_task(ok_task)["status"] == "pass"
    neg = {
        "fixture_table": {"columns": ["id"], "rows": [["1"]]},
        "success_criteria": {
            "dataset_assert": {
                "required_columns": ["id", "text"],
                "min_rows": 1,
                "expect_fail": True,
            }
        },
    }
    assert score_dataset_task(neg)["status"] == "pass"


def test_annotate_dataset_plan_runtime():
    ann = annotate_dataset_plan_runtime()
    assert ann["runtime_tier"] == "fixture"
    assert ann["execution_mode"] == "dataset_plan_assert"
    assert "KB" in ann["runtime_claim_reason"] or "kb" in ann["runtime_claim_reason"].lower()


@pytest.mark.asyncio
async def test_run_dataset_plan_exam():
    out = await run_typed_plan_exam(
        object_type="dataset",
        object_id="ds_demo",
        set_ids=["dataset/basic"],
        live=False,
        source_refs=["dataset_plan_ops"],
    )
    assert out.get("ok") is True
    assert out.get("object_type") == "dataset"
    assert out.get("execution_mode") == "dataset_plan_assert"
    assert out.get("accuracy_claim") is False
    assert "dataset/basic" in (out.get("selected_set_ids") or [])
    assert out.get("counts", {}).get("tasks", 0) >= 3
    assert out.get("counts", {}).get("pass", 0) >= 3
    assert "KB" in (out.get("msg") or "") or "kb" in (out.get("msg") or "").lower()
