"""Eval Protocol v0 adapter — shape + schema sample alignment."""
from __future__ import annotations

import json
from pathlib import Path

from core.harness.evaluation.eval_protocol import (
    SCHEMA_VERSION,
    from_run_evaluation,
    from_skill_eval_run,
    to_eval_protocol_v0,
    to_evaluation_healthz,
)


def test_evaluation_healthz_shape():
    hz = to_evaluation_healthz(status="ok")
    assert hz["product_id"] == "evaluation"
    assert hz["protocol"] == SCHEMA_VERSION
    assert hz["deploy_unit"] == "central"
    assert hz["status"] == "ok"


def test_to_eval_protocol_v0_required_fields():
    p = to_eval_protocol_v0(
        task_id="t1",
        target_kind="skill",
        target_ref="demo",
        status="ok",
        metrics={"pass_rate": 1.0},
        report={"summary": "x", "score": 1.0, "pass": True},
    )
    assert p["schema_version"] == SCHEMA_VERSION
    assert p["task"]["target_kind"] == "skill"
    assert p["status"] == "passed"
    assert p["report"]["gate"] == "pass"


def test_from_run_evaluation_maps_pass():
    p = from_run_evaluation(
        run_id="run-1",
        evaluator="auto-llm",
        report={"pass": True, "score": 0.9, "summary": "good"},
    )
    assert p["task"]["target_ref"] == "run-1"
    assert p["status"] == "passed"
    assert p["report"]["gate"] == "pass"


def test_from_skill_eval_run():
    p = from_skill_eval_run(
        run_id="evalrun-1",
        suite_id="suite-a",
        run_row={"status": "passed", "metrics": {"total": 3}},
        result={"pass_rate": 1.0},
    )
    assert p["task"]["target_kind"] == "skill"
    assert p["metrics"]["pass_rate"] == 1.0


def test_matches_repo_schema_sample_keys():
    """Cross-check required keys against frozen A1 schema file."""
    # core/tests/unit → repo root = parents[4]
    repo = Path(__file__).resolve().parents[4]
    schema_path = (
        repo
        / "reports/five-products/modules/evaluation/contracts/schemas/eval_protocol.schema.json"
    )
    assert schema_path.is_file(), schema_path
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = to_eval_protocol_v0(
        task_id="eval-sample-001",
        target_kind="skill",
        target_ref="fixture-skill",
        status="passed",
        suite="smoke",
        metrics={"pass_rate": 1.0},
        report={"summary": "sample", "score": 1.0, "gate": "pass"},
    )
    for k in schema.get("required") or []:
        assert k in sample
    assert sample["schema_version"] == schema["properties"]["schema_version"]["const"]
